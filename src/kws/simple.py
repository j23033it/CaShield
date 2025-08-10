from typing import List


def _to_hiragana(text: str) -> str:
    try:
        from pykakasi import kakasi

        kks = kakasi()
        conv = kks.convert(text)
        return "".join([x.get("hira", "") for x in conv])
    except Exception:
        return text


class SimpleKWS:
    def __init__(self, keywords: List[str]):
        self.keywords = keywords
        self.keywords_hira = [_to_hiragana(k) for k in keywords]

    def detect(self, text: str) -> List[str]:
        hira = _to_hiragana(text)
        hits = [orig for orig, hira_kw in zip(self.keywords, self.keywords_hira) if hira_kw and hira_kw in hira]
        return hits



