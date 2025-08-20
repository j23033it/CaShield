# src/llm/client_gemini.py
from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# .env を読み込む（既存の環境変数は維持）
load_dotenv()


@dataclass
class LLMConfig:
    model: str = os.environ.get("CASHIELD_GEMINI_MODEL", "gemini-2.5-flash-lite")
    temperature: float = float(os.environ.get("CASHIELD_LLM_TEMP", "0.1"))
    max_output_tokens: int = int(os.environ.get("CASHIELD_LLM_MAX_OUTPUT", "1024"))
    # リトライ/バックオフ設定
    max_retries: int = int(os.environ.get("CASHIELD_LLM_RETRIES", "5"))
    base_backoff_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_BASE", "1.0"))
    backoff_jitter_s: float = float(os.environ.get("CASHIELD_LLM_BACKOFF_JITTER", "0.2"))

    def ensure_api_key(self) -> None:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY is not set.")
        # client 初期化で明示指定するため保持
        self._resolved_api_key = key


class GeminiSummarizer:
    """
    Google AI (Gemini) で要約を取得する薄いラッパ。
    - 温度低（事実ベース）
    - 構造化JSON（Schema + response_mime_type=application/json）
    - 429/5xx 等は指数バックオフで自動リトライ
    """

    def __init__(self, cfg: Optional[LLMConfig] = None) -> None:
        self.cfg = cfg or LLMConfig()
        self.cfg.ensure_api_key()
        # 明示的に API キーを指定（GEMINI_API_KEY/GOOGLE_API_KEY どちらでも可）
        self.client = genai.Client(api_key=self.cfg._resolved_api_key)

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
            temperature=self.cfg.temperature,
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

    async def summarize(self, payload: Dict[str, Any]) -> "._ResultAdapter":
        prompt = self._build_prompt(payload)

        # google-genai v1: Part.from_text はキーワード引数で text= を渡す
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(
                    self.client.models.generate_content,  # 正: models.generate_content を使用
                    model=self.cfg.model,
                    contents=[content],                   # 引数名は contents
                    config=self._gen_config,
                )
                text = getattr(resp, "text", None)  # 取り出し（text 優先、無ければ candidates→parts→text）
                if not text:
                    cand = (getattr(resp, "candidates", []) or [None])[0]
                    if not cand or not getattr(cand, "content", None):
                        raise RuntimeError("Empty response from Gemini.")
                    parts = getattr(cand.content, "parts", []) or []
                    text = getattr(parts[0], "text", None) if parts else None

                if not text:
                    raise RuntimeError("No text in Gemini response.")

                data = json.loads(text)
                # 最低限のキーを検証
                _ = data["ng_word"], data["turns"], data["summary"], data["severity"], data["action"]
                return _ResultAdapter(data)

            except Exception as e:
                attempt += 1
                if attempt > self.cfg.max_retries:
                    raise RuntimeError(f"Gemini summarization failed: {e}") from e
                # 指数バックオフ + ジッター
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
        # 1..5 にクリップ
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
        self.time = time_str  # "HH:MM:SS" or None

    # queue.py から利用される想定の API
    def model_dump(self) -> Dict[str, Any]:
        return {"role": self.role, "text": self.text, "time": self.time}
