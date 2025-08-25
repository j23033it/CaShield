"""
src.kws.keywords

keywords.txt の柔軟なパーサを提供し、
- キーワード一覧（KWS 用）
- キーワード→深刻度のマッピング（要約保存時の severity 決定用）
を取得する。

サポートするフォーマット:
1) レベル行形式（推奨）
   例:
     level1=[ ]
     level2=[黙れ,いい加減にしろ]
     level3=[殺す,死ね]
   → "level<数値>" を深刻度として解釈（int）。

2) 1行1語形式（後方互換）
   例:
     土下座
     無能
   → デフォルト深刻度=3 を付与。

備考:
- 空白・全角カンマ・混在スペースにある程度対応。
- 解析に失敗した場合はフォールバックとして既定の NG 語を返す。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple


def load_keywords_with_severity(path: Path) -> Tuple[List[str], Dict[str, int]]:
    """`config/keywords.txt` を読み取り、(keywords, severity_map) を返す。

    - keywords: KWS 用キーワード（重複排除・順序維持）
    - severity_map: キーワード→深刻度（int）
    """
    if not path.exists():
        defaults = ["土下座", "無能", "死ね"]
        return defaults, {w: 3 for w in defaults}

    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # パターン1: levelN=[w1,w2,...]
    level_pat = re.compile(r"^level\s*(\d+)\s*=\s*\[(.*)\]$", re.IGNORECASE)
    any_level = False
    keywords: List[str] = []
    sev_map: Dict[str, int] = {}

    for ln in lines:
        m = level_pat.match(ln)
        if not m:
            continue
        any_level = True
        sev = int(m.group(1))
        # 中身をカンマ分割（全角カンマも考慮）
        body = m.group(2).strip()
        # 空の場合
        if not body:
            continue
        # カンマ区切りで分割 → 余分な空白・ブラケットを削除
        for raw in re.split(r"[,、]", body):
            w = raw.strip().strip("[]")
            if not w:
                continue
            if w not in sev_map:
                keywords.append(w)
            sev_map[w] = sev

    if any_level:
        return keywords, sev_map

    # パターン2: 1行1語（デフォルト深刻度=3）
    for ln in lines:
        w = ln
        if w not in sev_map:
            keywords.append(w)
        sev_map[w] = 3
    return keywords, sev_map

