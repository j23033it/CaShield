# src/llm/client_gemini.py
from __future__ import annotations
import os
import asyncio
import json
from dataclasses import dataclass
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from .rate_limiter import RateLimiter

# ======== Pydantic schema (Structured output) ========

class TurnOut(BaseModel):
    role: Literal["customer", "clerk"]
    text: str
    time: Optional[str] = None  # "HH:MM:SS" or None

class SummaryOut(BaseModel):
    ng_word: str
    turns: List[TurnOut]
    summary: str
    severity: int = Field(ge=1, le=5)
    action: str

# ======== Client wrapper ========

@dataclass
class LLMConfig:
    model: str = os.environ.get("CASHIELD_GEMINI_MODEL", "gemini-2.5-flash-lite")
    temperature: float = float(os.environ.get("CASHIELD_TEMPERATURE", "0.1"))
    rpm: int = int(os.environ.get("CASHIELD_LLM_RPM", "15"))
    rpd: int = int(os.environ.get("CASHIELD_LLM_RPD", "500"))

class GeminiSummarizer:
    def __init__(self, cfg: LLMConfig):
        self.client = genai.Client()  # GEMINI_API_KEY は環境変数から自動取得
        self.cfg = cfg
        self.rl = RateLimiter(rpm=cfg.rpm, rpd=cfg.rpd)

    async def summarize(self, payload: dict) -> SummaryOut:
        """
        payload: { "ng_word": str, "turns":[{role,text,time?}], "policy": {...} }
        """
        await self.rl.acquire()

        # 指数バックオフ（最大3回、2^n秒 + ジッタ）
        delay = 1.0
        last_err: Optional[Exception] = None
        for _ in range(4):
            try:
                resp = self.client.models.generate_content(
                    model=self.cfg.model,
                    contents=_build_prompt(payload),
                    config=types.GenerateContentConfig(
                        temperature=self.cfg.temperature,
                        response_mime_type="application/json",
                        response_schema=SummaryOut,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                # SDK が JSON を検証して返すパス
                if hasattr(resp, "parsed") and resp.parsed:
                    return resp.parsed  # SummaryOut
                # 後方互換：text を JSON として解釈
                data = json.loads(resp.text)
                return SummaryOut.model_validate(data)
            except Exception as e:
                last_err = e
                await asyncio.sleep(delay)
                delay = min(16.0, delay * 2)  # 1,2,4,8,16...
        raise RuntimeError(f"Gemini summarization failed: {last_err}")

def _build_prompt(p: dict):
    """
    Chat-like contents を構成。system相当のガイド＋会話断片（JSON）。
    """
    sys = (
        "あなたは『カスハラ対策』の要約アシスタントです。"
        "与えられた会話断片（NG語を含む）を読み、"
        "1) 事実ベースの短要約、2) 深刻度(1–5)、3) 店員向けの一次対応アクション（丁寧・日本語・箇条書き1–2）を返してください。"
        "出力形式はスキーマに完全準拠してください。"
    )
    data = json.dumps(
        {
            "ng_word": p["ng_word"],
            "turns": p["turns"],  # [{role,text,time?}]
        },
        ensure_ascii=False,
    )
    return [
        types.Content(role="user", parts=[types.Part.from_text(sys)]),
        types.Content(role="user", parts=[types.Part.from_text(f"会話断片:\n{data}")]),
    ]
