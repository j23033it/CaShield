# src/llm/client_gemini.py
from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


@dataclass
class LLMConfig:
    """補助的な設定（トークン数やリトライ）を管理します"""
    max_output_tokens: int = int(os.environ.get("CASHIELD_LLM_MAX_OUTPUT", "1024"))
    max_retries: int = int(os.environ.get("CASHIELD_LLM_RETRIES", "5"))
    base_backoff_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_BASE", "1.0"))
    backoff_jitter_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_JITTER", "0.2"))


class GeminiSummarizer:
    """
    Google AI (Gemini) で要約を取得する薄いラッパ。
    """

    def __init__(self, cfg: Optional[LLMConfig] = None) -> None:
        # =================================================================
        # ▼▼▼ APIキーとモデル設定をここに直接記述してください ▼▼▼
        # =================================================================
        self.api_key: str = "AIzaSyCHNEkRoY0t_mI-hbgD7vD-C0wIDBTLspU"
        self.model: str = "gemini-2.5-flash-lite"  
        self.temperature: float = 0.1
        # =================================================================
        # ▲▲▲ 設定はここまで ▲▲▲
        # =================================================================

        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            raise ValueError("APIキーが設定されていません。src/llm/client_gemini.py の self.api_key 変数を編集してください。")

        self.cfg = cfg or LLMConfig()
        self.client = genai.Client(api_key=self.api_key)

        # 返却 JSON のスキーマ
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
            temperature=self.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
            response_mime_type="application/json",
            response_schema=self._schema,
        )

    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        ng = payload.get("ng_word", "")
        turns = payload.get("turns", [])
        lines: List[str] = []
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

    async def summarize(self, payload: Dict[str, Any]) -> "_ResultAdapter":
        prompt = self._build_prompt(payload)

        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,  # ハードコードされたモデル名を使用
                    contents=[content],
                    config=self._gen_config,
                )
                text = getattr(resp, "text", None)
                if not text:
                    cand = (getattr(resp, "candidates", []) or [None])[0]
                    if not cand or not getattr(cand, "content", None):
                        raise RuntimeError("Empty response from Gemini.")
                    parts = getattr(cand.content, "parts", []) or []
                    text = getattr(parts[0], "text", None) if parts else None

                if not text:
                    raise RuntimeError("No text in Gemini response.")

                data = json.loads(text)
                _ = data["ng_word"], data["turns"], data["summary"], data["severity"], data["action"]
                return _ResultAdapter(data)

            except Exception as e:
                attempt += 1
                if attempt > self.cfg.max_retries:
                    raise RuntimeError(f"Gemini summarization failed: {e}") from e
                
                sleep_s = self.cfg.base_backoff_s * (2 ** (attempt - 1))
                sleep_s += random.uniform(-self.cfg.backoff_jitter_s, self.cfg.backoff_jitter_s)
                if sleep_s < 0.1:
                    sleep_s = 0.1
                await asyncio.sleep(sleep_s)


class _ResultAdapter:
    """呼び出し側（queue.py）で扱いやすいように整形する薄いラッパ"""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.ng_word: str = data.get("ng_word", "")
        self.turns: List[_TurnAdapter] = [
            _TurnAdapter(t.get("role"), t.get("text"), t.get("time")) for t in data.get("turns", [])
        ]
        self.summary: str = data.get("summary", "")
        sev = data.get("severity", 3)
        try:
            sev = int(sev)
        except Exception:
            sev = 3
        self.severity: int = min(5, max(1, sev))
        self.action: str = data.get("action", "")


class _TurnAdapter:
    def __init__(self, role: Optional[str], text: Optional[str], time_str: Optional[str]) -> None:
        self.role = (role or "customer")
        self.text = (text or "")
        self.time = time_str

    def model_dump(self) -> Dict[str, Any]:
        return {"role": self.role, "text": self.text, "time": self.time}