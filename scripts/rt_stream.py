"""
scripts/rt_stream.py

リアルタイム監視（VAD → ASR(FAST/FINAL) → KWS → ログ追記 → 警告音）。

- 設定はコード内オブジェクトで集中管理（.envは使用しない）
- 入力デバイスは名称部分一致の運用も想定し、ホットプラグを踏まえた再起動制御を実装

安定化対応（HDMI抜去・端末切断対策 / ランタイム例外耐性）:
- SIGHUP を無視してヘッドレス運用時の強制終了を防止
- 音声入力の生存監視（コールバック無応答/非アクティブ）で自動再起動
"""

import re
import contextlib
import signal  # SIGHUP 無視による強制終了対策
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

# --- コード内設定オブジェクト（集中管理） ---
class RTStreamConfig:
    """リアルタイム音声監視の設定

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

    asr = DualASREngine()
    keywords = load_keywords(Path("config/keywords.txt"))
    # 類似度ベース（partial_ratio）。短すぎる語は無視して誤検知を抑制
    kws = FuzzyKWS(keywords, threshold=ASRConfig.KWS_FUZZY_THRESHOLD, min_hira_len=ASRConfig.KWS_MIN_HIRA_LEN)
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

    # 入力ストリームの安全な開始/再起動関数（ホットプラグ耐性あり）
    def _ensure_input_started():
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
                        f"[audio] retry failed: {e2}. using default device after {RTStreamConfig.RESTART_BACKOFF_S*2}s"
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
                        # FASTでは警告音を鳴らさず、FINAL確定時に鳴らす（誤検知抑制）
                        print(f"!! hit (FAST tentative): {hits}", flush=True)

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
                            if final_hits:
                                print(f"!! hit (FINAL confirmed): {final_hits}", flush=True)
                                action_mgr.play_warning()
                            print(f"[id {eid}] FINAL {status}: {final_text}", flush=True)

                        fut.add_done_callback(_on_done)
                except Exception as exc:
                    # 想定外例外でも監視を継続する（HDMI/デバイス周りの一過性障害を含む）
                    print(f"[エラー] 発話処理中に例外: {exc}", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        sd_in.stop()
        print("bye")


if __name__ == "__main__":
    main()
