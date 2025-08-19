# scripts/llm_worker.py
"""
NG行が追記されるたびに要約ジョブを投入するバックグラウンドワーカー。
- 監視対象: logs/YYYY-MM-DD.txt （今日のファイルを主対象）
- NG判定: 行文字列に "[NG:" を含む  もしくは keywords.txt によるフォールバック
"""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List

from src.llm.queue import LLMJobRunner, Job
from src.llm.client_gemini import LLMConfig
from src.llm.windowing import parse_line

LOG_DIR = Path("logs")
CONF_DIR = Path("config")

def load_keywords() -> List[str]:
    p = CONF_DIR / "keywords.txt"
    if not p.exists():
        return ["土下座", "無能", "死ね"]
    return [s.strip() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]

def find_ng_indices(lines: List[str], keywords: List[str]) -> List[int]:
    res: List[int] = []
    for i, line in enumerate(lines):
        if "[NG:" in line:
            res.append(i)
            continue
        # フォールバック：キーワードを含むか（ひらがな化まではここでは行わない）
        _, _, txt = parse_line(line)
        if any(k in txt for k in keywords):
            res.append(i)
    return sorted(set(res))

async def watch_today():
    LOG_DIR.mkdir(exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"{date}.txt"
    out_root = LOG_DIR / "summaries"
    out_root.mkdir(parents=True, exist_ok=True)

    cfg = LLMConfig()
    runner = LLMJobRunner(out_root=out_root, cfg=cfg)
    worker = asyncio.create_task(runner.worker())

    keywords = load_keywords()
    seen_count = 0

    print(f"[LLM] watching {log_path} (model={cfg.model})")

    while True:
        lines: List[str] = []
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").splitlines()

        # 新規行のうち NG 該当を抽出
        ng_idxs = [i for i in find_ng_indices(lines, keywords) if i >= seen_count]
        for idx in ng_idxs:
            # NG語推定（最初に見つかったものを採用）
            _, _, txt = parse_line(lines[idx])
            ng_word = next((k for k in keywords if k in txt), "NG")
            await runner.put(Job(date=date, lines=lines, ng_index=idx, ng_word=ng_word, out_dir=out_root))

        seen_count = len(lines)
        await asyncio.sleep(1.0)

    await runner.q.join()
    worker.cancel()

if __name__ == "__main__":
    asyncio.run(watch_today())
