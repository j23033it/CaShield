# src/llm/client_gemini.py
from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


@dataclass
class LLMConfig:
    """LLM通信の補助設定（トークン数やリトライ）をコード内で集中管理するクラス。

    - .env や環境変数は使わず、以下の既定値を直接編集して運用してください。
    """

    max_output_tokens: int = 1024
    max_retries: int = 5
    base_backoff_s: float = 1.0
    backoff_jitter_s: float = 0.2


class GeminiSummarizer:
    """Google AI (Gemini) で要約を取得する薄いラッパ。

    - APIキー・モデル名・温度は本クラス内のコードで管理します。
    - 出力JSONは schema に従いますが、severity は省略可能です（保存時は外部の既定値で補完）。
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

        # 返却 JSON のスキーマ（severity は任意。comfort は短い慰めの一言）
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
                "severity": types.Schema(type=types.Type.INTEGER),  # 任意
                "action": types.Schema(type=types.Type.STRING),
                "comfort": types.Schema(type=types.Type.STRING),
            },
            required=["ng_word", "turns", "summary", "action", "comfort"],
        )

        self._gen_config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.cfg.max_output_tokens,
            response_mime_type="application/json",
            response_schema=self._schema,
        )

    def _build_prompt(self, payload: Dict[str, Any]) -> str:
        """入力ペイロードから日本語プロンプトを構築する補助関数"""
        ng = payload.get("ng_word", "")
        turns = payload.get("turns", [])
        lines: List[str] = []
        lines.append("あなたはカスタマーハラスメント対策の監視AIです。")
        lines.append("与えられた数発話（日本語）のやり取りを読み、次をJSONで出力してください。")
        lines.append("1) ng_word（検知トリガ） 2) turns（そのままエコー）")
        lines.append("3) summary（簡潔な要約） 4) action（店員への推奨対応）")
        lines.append("5) comfort（被害当事者に寄り添う短い慰めの一言。断定・過度な励ましは避け、落ち着いた丁寧な文体。ユーザーに寄り添う形。出力結果に幅を持たせる、様々なバリエーションを考慮）")
        lines.append("出力は日本語。誇張せず、事実ベースで。")
        lines.append(f"\n[トリガ語候補] {ng}\n")
        lines.append("[会話ログ]")
        for t in turns:
            role = "客" if t.get("role") == "customer" else "店員"
            ts = f" {t.get('time')}" if t.get("time") else ""
            lines.append(f"- {role}{ts}: {t.get('text','')}")
        return "\n".join(lines)

    async def summarize(self, payload: Dict[str, Any]) -> "_ResultAdapter":
        """Gemini へ要約を要求し、JSONをパースして結果アダプタを返す。

        - LLM の出力に `severity` が無い場合でも KeyError にしない。
        - 必須キー（ng_word/turns/summary/action）のみ軽く検証。
        """
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=self._build_prompt(payload))],
        )

        attempt = 0
        while True:
            try:
                resp = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
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
                # 必須キーの存在を軽くチェック（severity は任意）
                for k in ("ng_word", "turns", "summary", "action", "comfort"):
                    if k not in data:
                        raise KeyError(f"missing required key: {k}")
                # severity が無ければ補完（後段では job.severity を優先利用）
                if "severity" not in data:
                    data["severity"] = 2

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
        sev = data.get("severity", 2)
        try:
            sev = int(sev)
        except Exception:
            sev = 2
        # 2段階制に合わせて 1..2 の範囲にクリップ
        self.severity: int = min(2, max(1, sev))
        self.action: str = data.get("action", "")
        # 慰めの言葉（欠落時は控えめな定型文で補完）
        self.comfort: str = (data.get("comfort") or "大丈夫ですよ。深呼吸して、まずは落ち着きましょう。")


class _TurnAdapter:
    def __init__(self, role: Optional[str], text: Optional[str], time_str: Optional[str]) -> None:
        self.role = (role or "customer")
        self.text = (text or "")
        self.time = time_str

    def model_dump(self) -> Dict[str, Any]:
        return {"role": self.role, "text": self.text, "time": self.time}
