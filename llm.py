#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LLM関連処理を統合したモノリシックファイル。

- 生ログを監視し、NGワードを検知するとジョブキューに投入
- バックグラウンドでジョブを処理し、Gemini APIに要約をリクエスト
- 結果をJSONL形式で保存

実行方法:
    リポジトリのルートから `python llm.py` を実行してください。
"""

# --- 標準ライブラリのインポート ---
from __future__ import annotations
import asyncio
import contextlib
import json
import os
import random
import re
import time
import traceback
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- 外部ライブラリのインポート ---
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("エラー: google-generativeai がインストールされていません。", file=sys.stderr)
    print("pip install google-generativeai を実行してください。", file=sys.stderr)
    sys.exit(1)

# =============================================================================
# --- グローバル定数定義 ---
# =============================================================================

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
CONFIG_DIR = ROOT_DIR / "config"


# =============================================================================
# --- 元 `src/llm/windowing.py` の内容 ---
# LLMに渡す会話ログを切り出すためのロジック
# =============================================================================

LINE_RE = re.compile(r"..\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+(客|店員):\s*(.*)")

@dataclass
class Turn:
    """1発話のデータクラス"""
    time: Optional[datetime]
    role: str  # "customer" or "clerk"
    text: str
    line_index: int

@dataclass
class Snippet:
    """LLMに渡す会話の断片"""
    ng_word: str
    turns: List[Turn]
    lo_index: int
    hi_index: int
    anchor_time: str  # "HH:MM:SS"

def parse_line(line: str) -> Tuple[Optional[datetime], str, str]:
    """ログ行をパースして (時刻, 役割, テキスト) を返す"""
    m = LINE_RE.match(line)
    if not m:
        return None, "customer", line.strip()
    dt_str, role_jp, text = m.groups()
    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        dt = None
    role = "customer" if role_jp == "客" else "clerk"
    return dt, role, text.strip()

def build_window(
    lines: List[str],
    ng_index: int,
    ng_word: str,
    min_sec: int = 12,
    max_sec: int = 30,
    max_tokens: int = 512,
) -> Snippet:
    """NG行を基点に、指定された時間・トークン数の範囲で会話の窓を切り出す"""
    all_turns: List[Turn] = []
    for i, line in enumerate(lines):
        dt, role, text = parse_line(line)
        if text:
            all_turns.append(Turn(time=dt, role=role, text=text, line_index=i))

    anchor_turn_idx = next((i for i, turn in enumerate(all_turns) if turn.line_index == ng_index), -1)

    if anchor_turn_idx == -1:
        dt, role, text = parse_line(lines[ng_index])
        turn = Turn(time=dt, role=role, text=text, line_index=ng_index)
        return Snippet(ng_word=ng_word, turns=[turn], lo_index=ng_index, hi_index=ng_index, anchor_time=dt.strftime("%H:%M:%S") if dt else "00:00:00")

    anchor_turn = all_turns[anchor_turn_idx]
    anchor_time = anchor_turn.time
    if not anchor_time:
        return Snippet(ng_word=ng_word, turns=[anchor_turn], lo_index=ng_index, hi_index=ng_index, anchor_time="00:00:00")

    lo_idx = anchor_turn_idx
    for i in range(anchor_turn_idx - 1, -1, -1):
        turn = all_turns[i]
        if not turn.time or (anchor_time - turn.time).total_seconds() > min_sec:
            break
        lo_idx = i

    hi_idx = anchor_turn_idx
    current_tokens = 0
    for i in range(lo_idx, len(all_turns)):
        turn = all_turns[i]
        if not turn.time or (turn.time - anchor_time).total_seconds() > max_sec:
            break
        current_tokens += len(turn.text)
        if current_tokens > max_tokens:
            break
        hi_idx = i

    selected_turns = all_turns[lo_idx : hi_idx + 1]
    return Snippet(
        ng_word=ng_word,
        turns=selected_turns,
        lo_index=selected_turns[0].line_index,
        hi_index=selected_turns[-1].line_index,
        anchor_time=anchor_time.strftime("%H:%M:%S"),
    )

# =============================================================================
# --- 元 `src/llm/client_gemini.py` の内容 ---
# Gemini APIとの通信を行うクライアント
# =============================================================================

@dataclass
class LLMConfig:
    """補助的な設定（トークン数やリトライ）を管理"""
    max_output_tokens: int = 1024
    max_retries: int = 5
    base_backoff_s: float = 1.0
    backoff_jitter_s: float = 0.2

class GeminiSummarizer:
    """Google AI (Gemini) で要約を取得するラッパ"""
    def __init__(self, cfg: Optional[LLMConfig] = None) -> None:
        self.api_key: str = "AIzaSyCHNEkRoY0t_mI-hbgD7vD-C0wIDBTLspU" # ★★★ APIキーをここに設定 ★★★
        self.model: str = "gemini-2.5-flash-lite"
        self.temperature: float = 0.1

        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            raise ValueError("APIキーが設定されていません。llm.pyのself.api_keyを編集してください。")

        self.cfg = cfg or LLMConfig()
        self.client = genai.Client(api_key=self.api_key)

        self._schema = genai_types.Schema(
            type=genai_types.Type.OBJECT,
            properties={
                "ng_word": genai_types.Schema(type=genai_types.Type.STRING),
                "turns": genai_types.Schema(type=genai_types.Type.ARRAY, items=genai_types.Schema(type=genai_types.Type.OBJECT, properties={"role": genai_types.Schema(type=genai_types.Type.STRING), "text": genai_types.Schema(type=genai_types.Type.STRING), "time": genai_types.Schema(type=genai_types.Type.STRING, nullable=True)}, required=["role", "text"])),
                "summary": genai_types.Schema(type=genai_types.Type.STRING),
                "severity": genai_types.Schema(type=genai_types.Type.INTEGER),
                "action": genai_types.Schema(type=genai_types.Type.STRING),
            },
            required=["ng_word", "turns", "summary", "severity", "action"],
        )
        self._gen_config = genai_types.GenerateContentConfig(temperature=self.temperature, max_output_tokens=self.cfg.max_output_tokens, response_mime_type="application/json", response_schema=self._schema)

    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        ng, turns, lines = payload.get("ng_word", ""), payload.get("turns", []), []
        lines.extend(["あなたはカスタマーハラスメント対策の監視AIです。", "与えられた数発話（日本語）のやり取りを読み、次をJSONで出力してください。", "1) ng_word（検知トリガ） 2) turns（そのままエコー）", "3) summary（簡潔な要約） 4) severity（1=軽微〜5=重大） 5) action（店員への推奨対応）", "出力は日本語。誇張せず、事実ベースで。", f"\n[トリガ語候補] {ng}\n", "[会話ログ]"])
        for t in turns:
            lines.append(f"- {'客' if t.get('role') == 'customer' else '店員'}{f' {t.get("time")}' if t.get('time') else ''}: {t.get('text','')}")
        return "\n".join(lines)

    async def summarize(self, payload: Dict[str, Any]) -> "_ResultAdapter":
        prompt = self._build_prompt(payload)
        content = genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)])
        for attempt in range(self.cfg.max_retries + 1):
            try:
                resp = await asyncio.to_thread(self.client.models.generate_content, model=self.model, contents=[content], config=self._gen_config)
                text = getattr(resp, "text", None)
                if not text:
                    cand = (getattr(resp, "candidates", []) or [None])[0]
                    if cand and getattr(cand, "content", None):
                        parts = getattr(cand.content, "parts", []) or []
                        text = getattr(parts[0], "text", None) if parts else None
                if not text:
                    raise RuntimeError("No text in Gemini response.")
                data = json.loads(text)
                return _ResultAdapter(data)
            except Exception as e:
                if attempt == self.cfg.max_retries:
                    raise RuntimeError(f"Gemini summarization failed after {attempt} retries: {e}") from e
                sleep_s = self.cfg.base_backoff_s * (2**attempt) + random.uniform(0, self.cfg.backoff_jitter_s)
                await asyncio.sleep(sleep_s)
        raise RuntimeError("Summarization failed")

@dataclass
class _ResultAdapter:
    """LLMからの結果を格納するデータクラス"""
    ng_word: str
    summary: str
    severity: int
    action: str
    turns: List[Dict[str, Any]]
    def __init__(self, data: Dict[str, Any]) -> None:
        self.ng_word = data.get("ng_word", "")
        self.summary = data.get("summary", "")
        self.severity = min(5, max(1, int(data.get("severity", 3))))
        self.action = data.get("action", "")
        self.turns = data.get("turns", [])

# =============================================================================
# --- 元 `src/llm/queue.py` の内容 ---
# LLMへのリクエストを管理する非同期ジョブキュー
# =============================================================================

@dataclass
class Job:
    date: str
    lines: List[str]
    ng_index: int
    ng_word: str
    out_dir: Path

class LLMJobRunner:
    def __init__(self, out_root: Path, cfg: LLMConfig):
        self.q: asyncio.Queue[Job] = asyncio.Queue()
        self.out_root = out_root
        self.summarizer = GeminiSummarizer(cfg)

    async def put(self, job: Job) -> None:
        await self.q.put(job)
        print(f"[LLMキュー] 新規ジョブ投入: date={job.date} idx={job.ng_index} word={job.ng_word}")

    async def worker(self) -> None:
        while True:
            job = await self.q.get()
            try:
                t0 = time.perf_counter()
                await self._process(job)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                print(f"[LLMキュー] ジョブ完了: idx={job.ng_index} ({dt_ms:.0f}ms)")
            except Exception as exc:
                self._write_error(job, exc)
                print(f"[LLMキュー] ジョブ失敗: idx={job.ng_index} → {exc.__class__.__name__}: {exc}", file=sys.stderr)
            finally:
                self.q.task_done()

    async def _process(self, job: Job) -> None:
        job.out_dir.mkdir(parents=True, exist_ok=True)
        snip = build_window(lines=job.lines, ng_index=job.ng_index, ng_word=job.ng_word)
        payload = {"ng_word": snip.ng_word, "turns": [{"role": t.role, "text": t.text, "time": t.time.strftime("%H:%M:%S") if t.time else None} for t in snip.turns]}
        res = await self.summarizer.summarize(payload)
        record = {"date": job.date, "anchor_time": snip.anchor_time, "ng_word": res.ng_word, "turns": res.turns, "summary": res.summary, "severity": res.severity, "action": res.action, "meta": {"model": self.summarizer.model, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "line_range": [snip.lo_index, snip.hi_index]}}
        with (job.out_dir / f"{job.date}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_error(self, job: Job, exc: Exception) -> None:
        err_dir = job.out_dir / "errors"
        err_dir.mkdir(parents=True, exist_ok=True)
        per_job_path = err_dir / f"{job.date}-{job.ng_index}.log"
        # スタックトレースをファイルに書き込む
        per_job_path.write_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), encoding="utf-8")
        
        # 日次エラーログにも追記
        per_day_path = job.out_dir / f"{job.date}.errors.log"
        with per_day_path.open("a", encoding="utf-8") as ef:
            ts = datetime.now().strftime('%H:%M:%S')
            summary = f"[{ts}] idx={job.ng_index} -> {exc.__class__.__name__}\n"
            ef.write(summary)

# =============================================================================
# --- 元 `scripts/llm_worker.py` の内容 ---
# メインの実行ロジック
# =============================================================================

def load_keywords() -> List[str]:
    p = CONFIG_DIR / "keywords.txt"
    if not p.exists():
        return ["土下座", "無能", "死ね"]
    return [s.strip() for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]

def find_ng_indices(lines: List[str], keywords: List[str]) -> List[int]:
    res = []
    for i, line in enumerate(lines):
        if "[NG:" in line:
            res.append(i)
            continue
        _, _, txt = parse_line(line)
        if any(k in txt for k in keywords):
            res.append(i)
    return sorted(set(res))

async def run_llm_worker() -> None:
    """ログファイルを監視し、LLMジョブを投入するメイン非同期関数"""
    stop_event = asyncio.Event()
    LOG_DIR.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"{date_str}.txt"
    summaries_dir = LOG_DIR / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)

    llm_config = LLMConfig()
    job_runner = LLMJobRunner(out_root=summaries_dir, cfg=llm_config)
    worker_task = asyncio.create_task(job_runner.worker(), name="llm-worker-bg")

    keywords = load_keywords()
    processed_line_count = 0

    print(f"[LLMワーカー] ログファイルを監視中: {log_path}")
    print(f"  - モデル: {job_runner.summarizer.model}")

    try:
        while not stop_event.is_set():
            lines = []
            if log_path.exists():
                try:
                    lines = log_path.read_text(encoding="utf-8").splitlines()
                except Exception as e:
                    print(f"[警告] ログファイルの読み込みに失敗: {e}", file=sys.stderr)

            if lines:
                ng_indices = [i for i in find_ng_indices(lines, keywords) if i >= processed_line_count]
                for index in ng_indices:
                    _, _, text = parse_line(lines[index])
                    ng_word = next((k for k in keywords if k in text), "NG")
                    await job_runner.put(Job(date=date_str, lines=lines, ng_index=index, ng_word=ng_word, out_dir=summaries_dir))
            
            processed_line_count = len(lines)
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[LLMワーカー] ユーザ操作により停止します。")
        stop_event.set()
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
        print("\n[LLMワーカー] 監視を停止しました。")

# =============================================================================
# --- 実行ブロック ---
# =============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(run_llm_worker())
    except KeyboardInterrupt:
        # asyncio.run()がKeyboardInterruptを捕捉すると、ループは既に停止している
        # ここでのメッセージは、ユーザが即座にCtrl+Cを押した場合に表示されることがある
        print("\n[LLMワーカー] プログラムを終了します。")
