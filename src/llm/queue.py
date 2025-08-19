# src/llm/queue.py
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from .client_gemini import GeminiSummarizer, LLMConfig
from .windowing import build_window, parse_line, Turn

@dataclass
class Job:
    date: str
    lines: List[str]   # ログ全行
    ng_index: int      # 基点インデックス
    ng_word: str
    out_dir: Path      # 保存先: logs/summaries

class LLMJobRunner:
    def __init__(self, out_root: Path, cfg: LLMConfig):
        self.q: asyncio.Queue[Job] = asyncio.Queue()
        self.out_root = out_root
        self.summarizer = GeminiSummarizer(cfg)

    async def put(self, job: Job):
        await self.q.put(job)

    async def worker(self):
        while True:
            job = await self.q.get()
            try:
                await self._process(job)
            except Exception as e:
                self._write_error(job, str(e))
            finally:
                self.q.task_done()

    async def _process(self, job: Job):
        job.out_dir.mkdir(parents=True, exist_ok=True)
        min_sec = int(_env("CASHIELD_MIN_SEC", "12"))
        max_sec = int(_env("CASHIELD_MAX_SEC", "30"))
        max_tokens = int(_env("CASHIELD_MAX_TOKENS", "512"))

        snip = build_window(
            lines=job.lines, ng_index=job.ng_index, ng_word=job.ng_word,
            min_sec=min_sec, max_sec=max_sec, max_tokens=max_tokens
        )

        # Gemini へ
        turns_payload = [
            {
                "role": t.role,
                "text": t.text,
                "time": t.time.strftime("%H:%M:%S") if t.time else None
            } for t in snip.turns
        ]
        payload = {"ng_word": snip.ng_word, "turns": turns_payload}

        res = await self.summarizer.summarize(payload)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        out_path = job.out_dir / f"{job.date}.jsonl"
        record: Dict[str, Any] = {
            "date": job.date,
            "anchor_time": snip.anchor_time,
            "ng_word": res.ng_word,
            "turns": [t.model_dump() for t in res.turns],
            "summary": res.summary,
            "severity": res.severity,
            "action": res.action,
            "meta": {
                "model": self.summarizer.cfg.model,
                "created_at": now,
            }
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_error(self, job: Job, message: str):
        err_dir = job.out_dir / "errors"
        err_dir.mkdir(parents=True, exist_ok=True)
        p = err_dir / f"{job.date}-{job.ng_index}.log"
        with p.open("w", encoding="utf-8") as f:
            f.write(message)

def _env(k: str, default: str) -> str:
    import os
    return os.environ.get(k, default)
