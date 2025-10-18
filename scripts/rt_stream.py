"""
scripts/rt_stream.py

リアルタイム監視（VAD → ASR → KWS → ログ追記 → 警告音）。

- 設定はコード内オブジェクトで集中管理（.envは使用しない）
- 入力デバイスは名称部分一致の運用も想定し、ホットプラグを踏まえた再起動制御を実装

安定化対応（HDMI抜去・端末切断対策 / ランタイム例外耐性）:
- SIGHUP を無視してヘッドレス運用時の強制終了を防止
- 音声入力の生存監視（コールバック無応答/非アクティブ）で自動再起動
"""

from __future__ import annotations

import contextlib
import re
import signal  # SIGHUP 無視による強制終了対策
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.action_manager import ActionManager
from src.audio.sd_input import SDInput
from src.config.asr import ASRConfig
from src.config.filter import BANNED_HALLUCINATIONS, is_banned
from src.kws.fuzzy import FuzzyKWS
from src.kws.keywords import load_keywords_with_severity
from src.asr.single_engine import SingleASREngine
from src.vad.webrtc import WebRTCVADSegmenter


LOG_DIR = Path("logs")
ASR_STAGE_LABEL = "ASR"


class RTStreamConfig:
    """リアルタイム音声監視の設定。

    どんなクラスか:
    - RTストリーム固有の運用パラメータを一箇所に集約する設定コンテナです。

    主な項目:
    - INPUT_DEVICE: None / デバイスindex / 名称の部分一致文字列（例: "USB", "HDMI"）
    - HOTPLUG_LIVENESS_TIMEOUT_S: コールバック無応答と見なす秒数（超過で再起動）
    - RESTART_BACKOFF_S: 再起動時の待機秒数
    - FALLBACK_TO_DEFAULT: 明示デバイス起動失敗時に既定デバイスへフォールバックするか
    """

    INPUT_DEVICE: Optional[int | str] = None
    HOTPLUG_LIVENESS_TIMEOUT_S: float = 2.0
    RESTART_BACKOFF_S: float = 1.0
    FALLBACK_TO_DEFAULT: bool = True


def _append_log_line(role: str, stage: str, entry_id: str, text: str, hits: List[str]) -> None:
    """文字起こし結果を1行追記する補助関数。"""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    who = "店員" if role == "clerk" else "客"
    ng = f" [NG: {', '.join(hits)}]" if hits else ""
    line = f"[{ts}] {who}: [{stage}] [ID:{entry_id}] {text}{ng}\n"
    (LOG_DIR / f"{date}.txt").open("a", encoding="utf-8").write(line)


_ID_COUNTER = 0


def _next_entry_id() -> str:
    """ログ行の ID（ゼロパディング 6桁）を循環採番する。"""

    global _ID_COUNTER
    _ID_COUNTER = (_ID_COUNTER + 1) % 1000000
    return f"{_ID_COUNTER:06d}"


def load_keywords(path: Path) -> List[str]:
    """キーワード一覧（KWS用）を取得。"""

    keywords, _sev_map = load_keywords_with_severity(path)
    return keywords


def main() -> None:
    """リアルタイム音声監視のエントリーポイント。"""

    # --- ヘッドレス運用時の強制終了対策（SIGHUP 無視） ---
    # HDMI 抜去 / SSH 切断等で端末セッションが落ちた場合に SIGHUP が来ても無視する。
    with contextlib.suppress(Exception):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)  # type: ignore[attr-defined]

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

    asr = SingleASREngine()
    keywords = load_keywords(Path("config/keywords.txt"))
    # 類似度ベース（partial_ratio）。短すぎる語は無視して誤検知を抑制
    kws = FuzzyKWS(keywords, threshold=ASRConfig.KWS_FUZZY_THRESHOLD, min_hira_len=ASRConfig.KWS_MIN_HIRA_LEN)
    action_mgr = ActionManager("assets/alert.wav")

    print("=" * 50)
    print("CaShield RT stream - start")
    print(
        f"ASR={ASRConfig.MODEL_NAME}({ASRConfig.COMPUTE_TYPE}, beam={ASRConfig.BEAM_SIZE}) "
        f"Device={ASRConfig.DEVICE}"
    )
    print(f"Keywords: {', '.join(keywords)}")
    print("Ctrl+C to stop\n")

    # 入力ストリームの安全な開始/再起動関数（ホットプラグ耐性あり）
    def _ensure_input_started() -> None:
        """音声入力ストリームを安全に再起動する。"""

        try:
            sd_in.stop()
        except Exception:
            pass
        try:
            sd_in.start(device=RTStreamConfig.INPUT_DEVICE)
        except Exception as e:
            print(f"[audio] start failed: {e}. retry in {RTStreamConfig.RESTART_BACKOFF_S}s")
            time.sleep(RTStreamConfig.RESTART_BACKOFF_S)
            try:
                sd_in.start(device=RTStreamConfig.INPUT_DEVICE)
            except Exception as e2:
                if RTStreamConfig.FALLBACK_TO_DEFAULT:
                    print(
                        f"[audio] retry failed: {e2}. using default device after {RTStreamConfig.RESTART_BACKOFF_S * 2}s"
                    )
                    time.sleep(RTStreamConfig.RESTART_BACKOFF_S * 2)
                    sd_in.start(device=None)
                else:
                    raise

    _ensure_input_started()

    try:
        while True:
            # 60ms 毎に取り出し
            time.sleep(0.06)

            # ホットプラグ検知: 一定時間コールバック無し/非アクティブなら再起動
            if (not sd_in.is_active()) or (
                sd_in.time_since_last_callback() > RTStreamConfig.HOTPLUG_LIVENESS_TIMEOUT_S
            ):
                print(
                    f"[audio] inactive or silent > {RTStreamConfig.HOTPLUG_LIVENESS_TIMEOUT_S}s. restarting...",
                    flush=True,
                )
                _ensure_input_started()
                continue

            chunk = sd_in.pop_all()
            if not chunk:
                continue
            # VADに投入
            utterances = vad.feed(chunk)
            for utt in utterances:
                try:
                    eos_t = time.perf_counter()  # 発話終了 time stamp
                    utt_ms = len(utt) / (sample_rate * 2) * 1000.0

                    # 単一段の ASR（同期実行）
                    asr_t0 = time.perf_counter()
                    text = asr.transcribe(utt, channels=1)

                    # ▼▼▼ ハルシネーションフィルタ ▼▼▼
                    if is_banned(text):
                        print(f"[フィルタ] 幻覚(ASR)を検出、無視します: {text}")
                        continue  # これ以降の処理をスキップして次のutteranceへ
                    # ▲▲▲ フィルタここまで ▲▲▲

                    asr_t1 = time.perf_counter()

                    # キーワード検出
                    hits = kws.detect(text)
                    e2e_ms = (time.perf_counter() - eos_t) * 1000.0
                    asr_ms = (asr_t1 - asr_t0) * 1000.0

                    entry_id = _next_entry_id()
                    print(
                        f"[utt {utt_ms:.0f}ms] ASR={asr_ms:.0f}ms e2e={e2e_ms:.0f}ms id={entry_id} text={text}",
                        flush=True,
                    )
                    # 原文ログ: ASR を追記
                    _append_log_line(role="customer", stage=ASR_STAGE_LABEL, entry_id=entry_id, text=text, hits=hits)

                    if hits:
                        print(f"!! hit (ASR): {hits}", flush=True)
                        action_mgr.play_warning()
                        action_mgr.log_detection(hits, text, role="customer")
                    else:
                        action_mgr.log_detection([], text, role="customer")
                except Exception as exc:  # noqa: BLE001
                    # 想定外例外でも監視を継続する（HDMI/デバイス周りの一過性障害を含む）
                    print(f"[エラー] 発話処理中に例外: {exc}", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        sd_in.stop()
        asr.close()
        print("bye")


if __name__ == "__main__":
    main()
