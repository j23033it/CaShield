"""
src.kws.simple

かな正規化の最小ユーティリティを提供するモジュール。

- 関数 `_to_hiragana(text)` は、与えられたテキストをひらがな列へ変換する。
- `pykakasi` を用いた簡易ラッパで、KWS 前処理（かな正規化）に利用する。

設計方針:
- 依存は既存の requirements.txt（pykakasi）に含まれているため追加不要。
- 変換器はモジュール内で遅延初期化し、複数回の呼び出しで再利用してオーバーヘッドを抑える。
"""

from __future__ import annotations

from typing import Any

try:
    # pykakasi は漢字→ひらがな・カタカナ→ひらがなへの変換を提供
    from pykakasi import kakasi  # type: ignore
except Exception as e:  # noqa: BLE001
    # 実行環境に依存するため、ImportError 時は遅延で再スローする
    kakasi = None  # type: ignore[assignment]
    _import_error: Exception | None = e
else:
    _import_error = None

_KAKASI: Any | None = None


def _get_kakasi():
    """pykakasi の変換器を遅延初期化して返す。

    - 初回呼び出しのみインスタンス化し、以降はモジュール内で再利用。
    - pykakasi の `kakasi().convert(text)` は辞書リストを返し、
      その各要素の 'hira' キーでひらがな文字列を取得できる。
    """
    global _KAKASI
    if _KAKASI is None:
        if kakasi is None:
            # 依存未導入などにより import に失敗していれば、その情報を出す
            raise (_import_error or ImportError("pykakasi is not available"))
        _KAKASI = kakasi()
    return _KAKASI


def _to_hiragana(text: str) -> str:
    """テキストをひらがなへ正規化して返す。

    用途:
    - KWS（キーワード検出）の前処理として、対象テキストおよびキーワードを共通の
      ひらがな表記へ正規化するために使用する。

    例:
    >>> _to_hiragana("土下座してください")
    'どげざしてください'

    失敗時:
    - 変換に失敗した場合は、入力テキストをそのまま返す（フェイルセーフ）。
    """
    if not text:
        return ""
    try:
        kks = _get_kakasi()
        return "".join([item.get("hira", "") for item in kks.convert(text)])
    except Exception:  # noqa: BLE001
        return text


class ExactKWS:
    """
    かな正規化後の「単純一致（部分文字列）」で NG ワードを検出するクラス。

    どんなクラスか:
    - 類似度スコア（rapidfuzz など）は使わず、ひらがなに正規化した本文に、
      ひらがな化した各キーワードが「含まれているか」を判定します。

    使い方:
    - `kws = ExactKWS(["ばか", "しね"])` のように初期化し、
      `kws.detect("…") -> [ヒットした元キーワードの配列]` を利用します。
    """

    def __init__(self, keywords: list[str]) -> None:
        # 元のキーワード（表示/ログ用）と、照合用のひらがな化キーワードを保持
        self.keywords = keywords
        self.keywords_hira = [_to_hiragana(k) for k in keywords]

    def detect(self, text: str) -> list[str]:
        """本文をひらがな化し、部分文字列一致でヒットを返す。"""
        hira = _to_hiragana(text)
        hits: list[str] = []
        for orig, hira_kw in zip(self.keywords, self.keywords_hira):
            if not hira_kw:
                continue
            if hira_kw in hira:
                hits.append(orig)
        return hits
