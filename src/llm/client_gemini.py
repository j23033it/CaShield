# src/llm/client_gemini.py
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


@dataclass
class LLMConfig:
    model: str = os.environ.get("CASHIELD_GEMINI_MODEL", "gemini-2.5-flash-lite")
    temperature: float = float(os.environ.get("CASHIELD_LLM_TEMP", "0.1"))
    max_output_tokens: int = int(os.environ.get("CASHIELD_LLM_MAX_OUTPUT", "1024"))
    # リトライ/バックオフ
    max_retries: int = int(os.environ.get("CASHIELD_LLM_RETRIES", "5"))
    base_backoff_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_BASE", "1.0"))
    backoff_jitter_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_JITTER", "0.2"))

    def ensure_api_key(self) -> None:
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is not set.")


class GeminiSummarizer:
    """
    Google AI (Gemini) クライアントの薄いラッパ。
    - 温度低め、構造化JSONで要約を取得
    - 429/5xx は指数バックオフで自動リトライ
    - 非同期APIに合わせて asyncio.to_thread で実行
    出力スキーマ:
      {
        "ng_word": str,
        "turns": [{"role": "customer"|"clerk", "text": str, "time": "HH:MM:SS"|null}, ...],
        "summary": str,
        "severity": int(1..5),
        "action": str
      }
    """

    def __init__(self, cfg: Optional[LLMConfig] = None) -> None:
        self.cfg = cfg or LLMConfig()
        self.cfg.ensure_api_key()
        self.client = genai.Client()  # GEMINI_API_KEY は環境変数から自動取得

        # 返却JSONのスキーマ
        self._schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "ng_word": types.Schema(type=types.Type.STRING),
                "turns": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "role": types.Schema(type=types.Type.STRING),
                            "text": types.Schema(type=types.Type.STRING),
                            "time": types.Schema(type=types.Type.STRING, nullable=True),
                        },
                        required=["role", "text"],
                    ),
                ),
                "summary": types.Schema(type=types.Type.STRING),
                "severity": types.Schema(type=types.Type.INTEGER),
                "action": types.Schema(type=types.Type.STRING),
            },
            required=["ng_word", "turns", "summary", "severity", "action"],
        )

        self._gen_config = types.GenerateContentConfig(
            temperature=self.cfg.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
            response_mime_type="application/json",
            response_schema=self._schema,
        )

    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        # 役割: 対話ログの要約とリスク判定（温度低）
        # 期待: JSONで返す（response_schemaで強制）
        ng = payload.get("ng_word", "")
        turns = payload.get("turns", [])
        lines = []
        lines.append("あなたはカスタマーハラスメント対策の監視AIです。")
        lines.append("与えられた数発話（日本語）のやり取りを読み、次をJSONで出力してください。")
        lines.append("1) ng_word（検知トリガ） 2) turns（そのままエコー）")
        lines.append("3) summary（簡潔な要約） 4) severity（1=軽微〜5=重大） 5) action（店員への推奨対応）")
        lines.append("出力は日本語。誇張せず、事実ベースで。")
        lines.append(f"\n[トリガ語候補] {ng}\n")
        lines.append("[会話ログ]")
        for t in turns:
            role = "客" if t.get("role") == "customer" else "店員"
            ts = f" {t.get('time')}" if t.get("time") else ""
            lines.append(f"- {role}{ts}: {t.get('text','')}")
        return "\n".join(lines)

    async def summarize(self, payload: Dict[str, Any]) -> Any:
        prompt = self._build_prompt(payload)

        # google-genai v1: Part.from_text はキーワード専用（text=...）
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(
                    self.client.responses.generate,
                    model=self.cfg.model,
                    input=[content],
                    config=self._gen_config,
                )
                # 取り出し（v1 では output_text、なければ candidates→parts）
                if hasattr(resp, "output_text") and resp.output_text:
                    text = resp.output_text
                else:
                    cand = (getattr(resp, "candidates", []) or [None])[0]
                    if not cand or not getattr(cand, "content", None):
                        raise RuntimeError("Empty response from Gemini.")
                    part0 = cand.content.parts[0] if cand.content.parts else None
                    text = getattr(part0, "text", None)

                if not text:
                    raise RuntimeError("No text in Gemini response.")

                # response_mime_type=application/json なので基本JSON
                data = json.loads(text)
                # 最低限のバリデーション
                _ = data["ng_word"], data["turns"], data["summary"], data["severity"], data["action"]
                # Pydantic等は使わず、呼び出し元で dataclass へ詰め替える
                return _ResultAdapter(data)

            except Exception as e:
                # 429/5xxを想定して指数バックオフ
                attempt += 1
                if attempt > self.cfg.max_retries:
                    raise RuntimeError(f"Gemini summarization failed: {e}") from e
                # ジッター付きバックオフ
                sleep_s = self.cfg.base_backoff_s * (2 ** (attempt - 1))
                sleep_s += random.uniform(-self.cfg.backoff_jitter_s, self.cfg.backoff_jitter_s)
                sleep_s = max(0.1, sleep_s)
                await asyncio.sleep(sleep_s)


class _ResultAdapter:
    """queue.py から扱いやすいように最低限の属性を持たせる薄いラッパ"""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.ng_word: str = data.get("ng_word", "")
        self.turns: List[_TurnAdapter] = [
            _TurnAdapter(t.get("role"), t.get("text"), t.get("time")) for t in data.get("turns", [])
        ]
        self.summary: str = data.get("summary", "")
        # 1..5 にクリップ
        sev = data.get("severity", 3)
        try:
            sev = int(sev)
        except Exception:
            sev = 3
        self.severity: int = min(5, max(1, sev))
        self.action: str = data.get("action", "")


class _TurnAdapter:
    def __init__(self, role: str, text: str, time_str: Optional[str]) -> None:
        self.role = role or "customer"
        self.text = text or ""
        self.time = time_str  # queue.py 側では model_dump() 相当を使うため、そのまま


