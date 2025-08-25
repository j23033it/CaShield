# scripts/llm_worker.py
"""
NG行が追記されるたびに要約ジョブを投入するバックグラウンドワーカー。
- 監視対象: logs/YYYY-MM-DD.txt （今日のファイルを主対象）
- NG判定: 行文字列に "[NG:" を含む  もしくは keywords.txt によるフォールバック
- 終了: Ctrl+C（KeyboardInterrupt）で優雅に停止
"""
from __future__ import annotations
import asyncio
import contextlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from src.llm.queue import LLMJobRunner, Job
from src.llm.client_gemini import LLMConfig
from src.llm.windowing import parse_line
from src.kws.keywords import load_keywords_with_severity

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
CONF_DIR = ROOT / "config"


def load_keywords_and_severity() -> Tuple[List[str], Dict[str, int]]:
    """keywords.txt を解析し、(keywords, severity_map) を返す。

    - keywords: KWS/抽出用の語彙リスト
    - severity_map: 語 → 既定深刻度
    """
    p = CONF_DIR / "keywords.txt"
    return load_keywords_with_severity(p)


def find_ng_indices(lines: List[str], keywords: List[str]) -> List[int]:
    res: List[int] = []
    for i, line in enumerate(lines):
        if "[NG:" in line:
            res.append(i)
            continue
        # フォールバック：簡易包含
        _, _, txt = parse_line(line)
        if any(k in txt for k in keywords):
            res.append(i)
    return sorted(set(res))


async def watch_today(stop: asyncio.Event) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"{date}.txt"
    out_root = LOG_DIR / "summaries"
    out_root.mkdir(parents=True, exist_ok=True)

    cfg = LLMConfig()
    runner = LLMJobRunner(out_root=out_root, cfg=cfg)
    worker_task = asyncio.create_task(runner.worker(), name="llm-worker")

    keywords, severity_map = load_keywords_and_severity()
    seen_count = 0

    # モデル名は runner インスタンスから取得するように変更
    print(f"[LLM] watching {log_path} (model={runner.summarizer.model})")

    try:
        while not stop.is_set():
            lines: List[str] = []
            if log_path.exists():
                # 読み込みエラーが出ても空扱いで継続
                with contextlib.suppress(Exception):
                    lines = log_path.read_text(encoding="utf-8").splitlines()

            # 新規行のうち NG 該当を抽出
            ng_idxs = [i for i in find_ng_indices(lines, keywords) if i >= seen_count]
            for idx in ng_idxs:
                _, _, txt = parse_line(lines[idx])
                ng_word = next((k for k in keywords if k in txt), "NG")
                sev = severity_map.get(ng_word, 3)
                await runner.put(Job(date=date, lines=lines, ng_index=idx, ng_word=ng_word, out_dir=out_root, severity=sev))

            seen_count = len(lines)
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        # Ctrl+C などでキャンセルされたら静かに抜ける
        pass
    finally:
        # バックグラウンドワーカーを確実に停止
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        print("[LLM] bye")


async def amain() -> None:
    stop = asyncio.Event()
    try:
        await watch_today(stop)
    except asyncio.CancelledError:
        # 念のため
        pass


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        # ここで綺麗にメッセージだけ出して終了
        print("[LLM] Stopped by user")
