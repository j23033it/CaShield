"""
src.kws.keywords

keywords.txt の柔軟なパーサを提供し、
- キーワード一覧（KWS 用）
- キーワード→深刻度のマッピング（要約保存時の severity 決定用）
を取得する。

サポートするフォーマット:
1) レベル行形式（推奨・複数行対応）
   例:
     level1=[ ]
     level2=[黙れ, いい加減にしろ,
             地獄に落ちろ]
     level3=[殺す, 死ね]
   → "level<数値>" を深刻度として解釈（int）。[] 内は改行・末尾カンマ可。

2) 1行1語形式（後方互換）
   例:
     土下座
     無能
   → デフォルト深刻度=2 を付与（2段階制に合わせる）。

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

    仕様:
    - levelN=[...] は複数行に渡っても良い（']' までを1ブロックとして取り込む）
    - ブロック内は半角/全角カンマで分割、空要素はスキップ
    - レベル記法が1つも無い場合は 1行1語形式として扱い、深刻度=2 を付与
    """
    if not path.exists():
        defaults = ["土下座", "無能", "死ね"]
        # 2段階制の既定に合わせ、既定深刻度は 2
        return defaults, {w: 2 for w in defaults}

    text = path.read_text(encoding="utf-8")
    # 余分な空白除去はレベル検出時に行うため、生テキストで走査

    # --- パターン1: levelN=[ ... ] ブロックを複数行対応で抽出 ---
    level_head = re.compile(r"level\s*(\d+)\s*=\s*\[", re.IGNORECASE)
    i = 0
    n = len(text)
    any_level = False
    keywords: List[str] = []
    sev_map: Dict[str, int] = {}

    while i < n:
        m = level_head.search(text, i)
        if not m:
            break
        any_level = True
        sev = int(m.group(1))
        # 開始ブラケットの直後から対応する ']' までを探す（ネスト想定なし）
        j = m.end()
        end = text.find(']', j)
        if end == -1:
            # 閉じブラケットが無い → 異常行。以降を諦める
            break
        body = text[j:end]
        # ブロック内の改行や余分な空白を許容
        # カンマ（全角/半角）で分割し、空を除外
        for raw in re.split(r"[,、]", body):
            w = raw.strip().strip("[]")
            if not w:
                continue
            if w not in sev_map:
                keywords.append(w)
            sev_map[w] = sev
        i = end + 1

    if any_level:
        return keywords, sev_map

    # --- パターン2: 1行1語（デフォルト深刻度=2）---
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        w = ln
        if w not in sev_map:
            keywords.append(w)
        sev_map[w] = 2
    return keywords, sev_map
