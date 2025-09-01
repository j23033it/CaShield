from typing import List

from rapidfuzz.fuzz import partial_ratio

from src.kws.simple import _to_hiragana


class FuzzyKWS:
    """
    かな正規化 + 類似度（partial_ratio）で KWS を行うクラス。

    どんなクラスか:
    - rapidfuzz.partial_ratio による部分一致スコアを使って、ひらがな化した本文との近さで判定する。
    - 誤検知を抑えるため、短すぎるキーワードを無視する最小長（かな長）を併せて用意。

    コンストラクタ引数:
    - keywords: NGワードのリスト（原表記）。ログ表示には原表記を返す。
    - threshold: 類似度しきい値（0..100）。高いほど厳密（誤検知減、取りこぼし増）。
    - min_hira_len: ひらがな化したキーワードの最小長（この長さ未満は無視）。
    """

    def __init__(self, keywords: List[str], threshold: int, min_hira_len: int = 2) -> None:
        self.keywords = keywords
        self.threshold = int(threshold)
        self.min_hira_len = int(min_hira_len)
        self.keywords_hira = [_to_hiragana(k) for k in keywords]

    def detect(self, text: str) -> List[str]:
        hira = _to_hiragana(text)
        hits: List[str] = []
        for orig, hira_kw in zip(self.keywords, self.keywords_hira):
            if not hira_kw:
                continue
            if len(hira_kw) < self.min_hira_len:
                # 短すぎる語は誤検知を招きやすいのでスキップ
                continue
            score = partial_ratio(hira_kw, hira)
            if score >= self.threshold:
                hits.append(orig)
        return hits
