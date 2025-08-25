import os
import re
import time
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict

from src.audio.sd_input import SDInput
from src.vad.webrtc import WebRTCVADSegmenter
from src.asr.dual_engine import DualASREngine
from src.config.asr import ASRConfig
from src.kws.fuzzy import FuzzyKWS
from src.kws.keywords import load_keywords_with_severity
from src.action_manager import ActionManager
from src.config.filter import is_banned, BANNED_HALLUCINATIONS

LOG_DIR = Path("logs")

# ▼▼▼ 幻覚（ハルシネーション）定型文のフィルタ（集中管理: src/config/filter.py） ▼▼▼

def _append_log_line(role: str, stage: str, entry_id: str, text: str, hits: List[str]) -> None:
    """Append one line to logs/YYYY-MM-DD.txt with stage + [ID:xxxx]."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    line = f"[{ts}] {who}: [{stage}] [ID:{entry_id}] {text}{ng}\n"
    (LOG_DIR / f"{date}.txt").open("a", encoding="utf-8").write(line)


_ID_COUNTER = 0


def _next_entry_id() -> str:
    global _ID_COUNTER
    _ID_COUNTER = (_ID_COUNTER + 1) % 1000000
    return f"{_ID_COUNTER:06d}"


def _replace_log_line(entry_id: str, role: str, new_stage: str, text: str, hits: List[str]) -> bool:
    """Replace the first line containing [ID:entry_id] with the FINAL result.

    Keeps original timestamp; overwrites content after the role marker.
    Returns True if replaced.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    p = LOG_DIR / f"{date}.txt"
    if not p.exists():
        return False
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    pat = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+%s:\s+.*\[ID:%s\].*$" % (re.escape(who), re.escape(entry_id)))
    lines = p.read_text(encoding="utf-8").splitlines(True)
    replaced = False
    for i, line in enumerate(lines):
        m = pat.match(line)
        if not m:
            continue
        ts = m.group("ts")
        lines[i] = f"[{ts}] {who}: [{new_stage}] [ID:{entry_id}] {text}{ng}\n"
        replaced = True
        break
    if replaced:
        p.write_text("".join(lines), encoding="utf-8")
    return replaced

def load_keywords(path: Path) -> List[str]:
    """キーワード一覧（KWS用）を取得。

    仕様:
    - config/keywords.txt は level 形式/1行1語形式のどちらにも対応
    - ここでは KWS に必要な語彙配列のみ返す（深刻度は llm_worker で利用）
    """
    keywords, _sev_map = load_keywords_with_severity(path)
    return keywords

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def main() -> None:
    # Code-based configuration (no .env/YAML for ASR)
    sample_rate = ASRConfig.SAMPLE_RATE
    block_ms = ASRConfig.BLOCK_MS
    vad_aggr = ASRConfig.VAD_AGGRESSIVENESS
    prev_ms = ASRConfig.PAD_PREV_MS
    post_ms = ASRConfig.PAD_POST_MS

    sd_in = SDInput(sample_rate=sample_rate, block_ms=block_ms)
    vad = WebRTCVADSegmenter(
        sample_rate=sample_rate,
        frame_ms=block_ms,
        aggressiveness=vad_aggr,
        prev_ms=prev_ms,
        post_ms=post_ms,
    )

    asr = DualASREngine()
    keywords = load_keywords(Path("config/keywords.txt"))
    kws = FuzzyKWS(keywords, threshold=ASRConfig.KWS_FUZZY_THRESHOLD)
    action_mgr = ActionManager("assets/alert.wav")

    print("=" * 50)
    print("CaShield RT stream - start")
    print(
        f"FAST={ASRConfig.FAST_MODEL}({ASRConfig.FAST_COMPUTE}, beam={ASRConfig.FAST_BEAM}) "
        f"FINAL={ASRConfig.FINAL_MODEL}({ASRConfig.FINAL_COMPUTE}, beam={ASRConfig.FINAL_BEAM}) "
        f"Device={ASRConfig.DEVICE}"
    )
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

                # FAST ASR (synchronous)
                asr_t0 = time.perf_counter()
                fast_text = asr.transcribe_fast(utt, channels=1)
                
                # ▼▼▼ ハルシネーションフィルタ（FAST）▼▼▼
                if is_banned(fast_text):
                    print(f"[フィルタ] 幻覚(FAST)を検出、無視します: {fast_text}")
                    continue  # これ以降の処理をスキップして次のutteranceへ
                # ▲▲▲ フィルタここまで ▲▲▲

                asr_t1 = time.perf_counter()

                # KWS
                hits = kws.detect(fast_text)
                e2e_ms = (time.perf_counter() - eos_t) * 1000.0
                asr_ms = (asr_t1 - asr_t0) * 1000.0

                entry_id = _next_entry_id()
                print(
                    f"[utt {utt_ms:.0f}ms] FAST asr={asr_ms:.0f}ms e2e={e2e_ms:.0f}ms id={entry_id} text={fast_text}",
                    flush=True,
                )
                # 原文ログ: FAST を追記
                _append_log_line(role="customer", stage="FAST", entry_id=entry_id, text=fast_text, hits=hits)
                if hits:
                    print(f"!! hit: {hits}", flush=True)
                    action_mgr.play_warning()

                # FINAL を非同期で実行し、完了時に同一ID行を置換
                if (not ASRConfig.FINAL_ON_HIT_ONLY) or hits:
                    fut: Future[str] = asr.submit_final(utt, channels=1)

                    def _on_done(f: Future[str], eid: str = entry_id) -> None:
                        try:
                            final_text: str = f.result()
                        except Exception as e:  # noqa: BLE001
                            final_text = f"<FINAL_ERROR: {e}>"
                        # ▼▼▼ ハルシネーションフィルタ（FINAL）▼▼▼
                        if is_banned(final_text):
                            print(f"[フィルタ] 幻覚(FINAL)を検出、無視します: {final_text}")
                            return
                        final_hits = kws.detect(final_text)
                        replaced = _replace_log_line(eid, role="customer", new_stage="FINAL", text=final_text, hits=final_hits)
                        status = "replaced" if replaced else "append-fallback"
                        if not replaced:
                            _append_log_line(role="customer", stage="FINAL", entry_id=eid, text=final_text, hits=final_hits)
                        print(f"[id {eid}] FINAL {status}: {final_text}", flush=True)

                    fut.add_done_callback(_on_done)

    except KeyboardInterrupt:
        pass
    finally:
        sd_in.stop()
        print("bye")


if __name__ == "__main__":
    main()
