# src/llm/queue.py
from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .client_gemini import GeminiSummarizer, LLMConfig
from .windowing import build_window  # parse_line/Turn は未使用のためインポートしない


@dataclass
class Job:
    """LLM要約ワーカーに投入される単位仕事。

    - date: 対象ログ日付（YYYY-MM-DD）
    - lines: ログ全行
    - ng_index: NGトリガとなった行のインデックス
    - ng_word: トリガ語
    - out_dir: 出力ディレクトリ（logs/summaries）
    - severity: 既定深刻度（keywords.txt による上書きを想定）
    """
    date: str
    lines: List[str]
    ng_index: int
    ng_word: str
    out_dir: Path
    # 2段階制（1..2）に合わせた既定深刻度
    severity: int = 2


@dataclass
class WindowConfig:
    """要約用の窓取り設定（コード内設定）。.env は使用しない。"""
    min_sec: int = 12
    max_sec: int = 30
    max_tokens: int = 512


class LLMJobRunner:
    """LLM要約ジョブの実行と結果保存を担当するクラス。"""

    def __init__(self, out_root: Path, cfg: LLMConfig, win: WindowConfig | None = None):
        self.q: asyncio.Queue[Job] = asyncio.Queue()
        self.out_root = out_root
        self.summarizer = GeminiSummarizer(cfg)
        self.win = win or WindowConfig()

    async def put(self, job: Job) -> None:
        """処理キューに投入（観測用ログを出力）。"""
        await self.q.put(job)
        print(
            f"[LLM][queue] date={job.date} idx={job.ng_index} "
            f"word={job.ng_word} lines={len(job.lines)}",
            flush=True,
        )

    async def worker(self) -> None:
        """ジョブを取り出して逐次処理。"""
        while True:
            job = await self.q.get()
            try:
                t0 = time.perf_counter()
                await self._process(job)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[LLM][save] {job.date}.jsonl idx={job.ng_index} ({dt_ms:.0f}ms)", flush=True)
            except Exception as exc:
                self._write_error(job, exc)
                print(f"[LLM][error] idx={job.ng_index} → {exc.__class__.__name__}: {exc}", flush=True)
            finally:
                self.q.task_done()

    async def _process(self, job: Job) -> None:
        """1ジョブ分の要約実行と保存。"""
        job.out_dir.mkdir(parents=True, exist_ok=True)

        # 窓取り（コード内設定）
        snip = build_window(
            lines=job.lines,
            ng_index=job.ng_index,
            ng_word=job.ng_word,
            min_sec=self.win.min_sec,
            max_sec=self.win.max_sec,
            max_tokens=self.win.max_tokens,
        )

        # LLM 入力（ターンを素直に JSON へ）
        turns_payload = [
            {
                "role": t.role,
                "text": t.text,
                "time": t.time.strftime("%H:%M:%S") if t.time else None,
            }
            for t in snip.turns
        ]
        payload = {"ng_word": snip.ng_word, "turns": turns_payload}

        # 要約
        res = await self.summarizer.summarize(payload)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 保存（JSON Lines）
        out_path = job.out_dir / f"{job.date}.jsonl"
        line_idx = list(range(snip.lo_index, snip.hi_index + 1))
        # 深刻度は LLM 出力ではなく、既定マッピング（Job.severity）を採用する
        record: Dict[str, Any] = {
            "date": job.date,
            "anchor_time": snip.anchor_time,
            # ng_word は LLM 返却ではなくトリガ（抽出）側の値を優先
            "ng_word": job.ng_word or res.ng_word,
            "turns": [t.model_dump() for t in res.turns],
            "summary": res.summary,
            # 未設定時も 2 を既定として保存
            "severity": int(job.severity) if job.severity else 2,
            "action": res.action,
            "comfort": res.comfort,
            "meta": {
                "model": self.summarizer.model,
                "created_at": now,
                "line_range": [snip.lo_index, snip.hi_index],
                "line_indices": line_idx,
            },
        }
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_error(self, job: Job, exc: Exception) -> None:
        """失敗時に per-job と per-day の両方にスタックトレースを残す。"""
        # per-job
        err_dir = job.out_dir / "errors"
        err_dir.mkdir(parents=True, exist_ok=True)
        per_job = err_dir / f"{job.date}-{job.ng_index}.log"
        with per_job.open("w", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

        # per-day（集約）
        per_day = job.out_dir / f"{job.date}.errors.log"
        with per_day.open("a", encoding="utf-8") as ef:
            ts = datetime.now().strftime("%H:%M:%S")
            ef.write(f"[{ts}] idx={job.ng_index}\n")
            ef.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            ef.write("\n")
