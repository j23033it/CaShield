import os
import time
from datetime import datetime
from pathlib import Path
from typing import List

from src.audio.sd_input import SDInput
from src.vad.webrtc import WebRTCVADSegmenter
from src.asr.engine import FasterWhisperEngine
from src.kws.simple import SimpleKWS
from src.action_manager import ActionManager
import yaml


def load_keywords(path: Path) -> List[str]:
    if not path.exists():
        return ["土下座", "無能", "死ね"]
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> None:
    # Load config YAML if exists
    cfg_path = Path("config/config.yaml")
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}

    # Params with env override
    sample_rate = int(cfg.get("sample_rate", 16000))
    block_ms = int(cfg.get("block_ms", 30))
    vcfg = cfg.get("vad", {}) or {}
    vad_aggr = int(vcfg.get("aggressiveness", 2))
    prev_ms = int(vcfg.get("pad_prev_ms", 200))
    post_ms = int(vcfg.get("pad_post_ms", 300))

    acfg = cfg.get("asr", {}) or {}
    model_name = os.environ.get("CASHIELD_MODEL", acfg.get("model", "tiny"))
    device = os.environ.get("CASHIELD_DEVICE", acfg.get("device", "cpu"))
    compute_type = os.environ.get("CASHIELD_COMPUTE", acfg.get("compute_type", "int8"))

    # Components
    sd_in = SDInput(sample_rate=sample_rate, block_ms=block_ms)
    vad = WebRTCVADSegmenter(
        sample_rate=sample_rate,
        frame_ms=block_ms,
        aggressiveness=vad_aggr,
        prev_ms=prev_ms,
        post_ms=post_ms,
    )
    # Optional: initial prompt
    initial_prompt = None
    pcfg = acfg.get("initial_prompt_path") if acfg else None
    if pcfg:
        p = Path(pcfg)
        if p.exists():
            try:
                initial_prompt = p.read_text(encoding="utf-8")
            except Exception:
                initial_prompt = None

    asr = FasterWhisperEngine(
        model_name=model_name,
        device=device,
        compute_type=compute_type,
        language="ja",
        beam_size=int(acfg.get("beam_size", 3)),
        condition_on_previous_text=False,
        vad_filter=True,
        initial_prompt=initial_prompt or "",
    )
    keywords = load_keywords(Path("config/keywords.txt"))
    kws = SimpleKWS(keywords)
    action_mgr = ActionManager("assets/alert.wav")

    print("=" * 50)
    print("CaShield RT stream - start")
    print(f"Model={model_name} Device={device} Compute={compute_type}")
    print(f"Keywords: {', '.join(keywords)}")
    print("Ctrl+C to stop\n")

    # Optional input device (index or name)
    dev_env = os.environ.get("CASHIELD_INPUT_DEVICE")
    dev_arg = None
    if dev_env:
        try:
            dev_arg = int(dev_env)
        except Exception:
            dev_arg = dev_env
    sd_in.start(device=dev_arg)

    try:
        while True:
            # 60ms 毎に取り出し
            time.sleep(0.06)
            chunk = sd_in.pop_all()
            if not chunk:
                continue
            # VADに投入
            utterances = vad.feed(chunk)
            for utt in utterances:
                # 発話終了時刻
                eos_t = time.perf_counter()
                utt_ms = len(utt) / (sample_rate * 2) * 1000.0

                # ASR
                asr_t0 = time.perf_counter()
                texts = []
                for out in asr.transcribe_stream([utt], channels=1):
                    if out.get("type") == "final":
                        texts.append(out.get("text", ""))
                text = "".join(texts).strip()
                asr_t1 = time.perf_counter()

                # KWS
                hits = kws.detect(text)
                e2e_ms = (time.perf_counter() - eos_t) * 1000.0
                asr_ms = (asr_t1 - asr_t0) * 1000.0

                print(f"[utt {utt_ms:.0f}ms] asr={asr_ms:.0f}ms e2e={e2e_ms:.0f}ms text={text}", flush=True)
                if hits:
                    print(f"!! hit: {hits}", flush=True)
                    action_mgr.play_warning()

    except KeyboardInterrupt:
        pass
    finally:
        sd_in.stop()
        print("bye")


if __name__ == "__main__":
    main()



