# src/llm/windowing.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import re

@dataclass
class Turn:
    role: str           # "customer" | "clerk"
    text: str
    time: Optional[datetime]  # 既存ログから抽出（無い場合は None）

@dataclass
class Snippet:
    ng_word: str
    anchor_time: Optional[str]  # 表示用 "HH:MM:SS"
    turns: List[Turn]
    lo_index: int
    hi_index: int

_TIME_RE = re.compile(r"^\[(?P<dt>[\d\-]+\s+[\d:]+)\]\s*(?P<body>.*)$")

def parse_line(line: str) -> Tuple[Optional[datetime], str, str]:
    """
    1行のログを (timestamp, role, text) に分解。
    想定:
    [YYYY-MM-DD HH:MM:SS] 店員: ... / [YYYY-MM-DD HH:MM:SS] 客: ...
    """
    ts: Optional[datetime] = None
    role = "customer"
    text = line.strip()

    m = _TIME_RE.match(text)
    if m:
        try:
            ts = datetime.strptime(m.group("dt"), "%Y-%m-%d %H:%M:%S")
        except Exception:
            ts = None
        text = m.group("body").lstrip()

    if text.startswith("店員:"):
        role = "clerk"
        text = text[len("店員:"):].lstrip()
    elif text.startswith("客:"):
        role = "customer"
        text = text[len("客:"):].lstrip()

    return ts, role, text

def estimate_tokens_ja(s: str) -> int:
    """
    日本語の概算トークン数（保守的）。文字数 * 0.66 を目安に。
    """
    return max(1, int(len(s) * 0.66))

def build_window(
    lines: List[str],
    ng_index: int,
    ng_word: str,
    min_sec: int = 12,
    max_sec: int = 30,
    max_tokens: int = 512,
) -> Snippet:
    """
    窓取り：基点=ng_index。
    1) 前後2–3発話を初期窓に
    2) min_sec(>=10–12s)まで前後に拡張、max_sec(<=30s)・max_tokens(<=512)で打ち止め
    """
    parsed = [parse_line(l) for l in lines]
    # 初期範囲（前後2発話）
    lo = max(0, ng_index - 2)
    hi = min(len(lines) - 1, ng_index + 2)

    def window_duration(a: int, b: int) -> float:
        times = [t for (t, _, _) in parsed[a:b+1] if t is not None]
        if not times:
            # 時刻不明なら 1発話 ≈ 3秒 として見積もる
            approx = (b - a + 1) * 3.0
            return approx
        return (max(times) - min(times)).total_seconds()

    # 時間が短ければ広げる
    while window_duration(lo, hi) < float(min_sec):
        if lo > 0:
            lo -= 1
            if window_duration(lo, hi) >= float(min_sec):
                break
        if hi < len(lines) - 1:
            hi += 1
        if lo == 0 and hi == len(lines) - 1:
            break

    # 上限制約（時間 / トークン）
    def tokens_in(a: int, b: int) -> int:
        text = "".join(parsed[i][2] for i in range(a, b+1))
        return estimate_tokens_ja(text)

    # 時間の上限
    while window_duration(lo, hi) > float(max_sec) and (hi - lo) >= 1:
        # 端から短い方を削る（発話数の少ない側）
        if (ng_index - lo) > (hi - ng_index):
            lo += 1
        else:
            hi -= 1

    # トークンの上限
    while tokens_in(lo, hi) > int(max_tokens) and (hi - lo) >= 1:
        if (ng_index - lo) > (hi - ng_index):
            lo += 1
        else:
            hi -= 1

    anchor_ts = parsed[ng_index][0].strftime("%H:%M:%S") if parsed[ng_index][0] else None
    turns = [Turn(role=r, text=tx, time=ts) for (ts, r, tx) in parsed[lo:hi+1]]
    return Snippet(ng_word=ng_word, anchor_time=anchor_ts, turns=turns, lo_index=lo, hi_index=hi)
