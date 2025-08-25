from typing import List

from rapidfuzz.fuzz import partial_ratio

from src.kws.simple import _to_hiragana


class FuzzyKWS:
    """
    Kana-normalized fuzzy keyword search using rapidfuzz.partial_ratio.
    Returns original keywords when similarity >= threshold.
    """

    def __init__(self, keywords: List[str], threshold: int) -> None:
        self.keywords = keywords
        self.threshold = int(threshold)
        self.keywords_hira = [_to_hiragana(k) for k in keywords]

    def detect(self, text: str) -> List[str]:
        hira = _to_hiragana(text)
        hits: List[str] = []
        for orig, hira_kw in zip(self.keywords, self.keywords_hira):
            if not hira_kw:
                continue
            score = partial_ratio(hira_kw, hira)
            if score >= self.threshold:
                hits.append(orig)
        return hits

