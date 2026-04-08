import re
from difflib import SequenceMatcher


class TextDiff:
    """Utility class to compare OCR text results and detect meaningful changes."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Strip, lowercase, and remove extra whitespace."""
        text = text.strip().lower()
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def is_same(text1: str, text2: str, threshold: float = 0.95) -> bool:
        """
        Return True if text1 and text2 are considered the same (no meaningful change).
        Returns False if either text is empty or too short (<3 chars after normalization).
        Uses SequenceMatcher ratio to compare.
        """
        n1 = TextDiff.normalize_text(text1)
        n2 = TextDiff.normalize_text(text2)

        if not n1 or not n2:
            return False

        if len(n1) < 3 or len(n2) < 3:
            return False

        ratio = SequenceMatcher(None, n1, n2).ratio()
        return ratio >= threshold
