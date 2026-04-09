import re
from difflib import SequenceMatcher


class TextDiff:
    """Utility class to compare OCR text results and detect meaningful changes."""

    # Characters that OCR engines commonly misread as noise
    _NOISE_RE = re.compile(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u4E00-\u9FFF\u0400-\u04FF.,!?;:\-\'\"()\[\]{}]')

    # Repeated decorative characters: ---, ===, ___, ***, |||, ~~~, etc.
    _DECORATIVE_RE = re.compile(r'^[\s\-=_.*|~#<>/\\:;,\'+`^!@$%&()[\]{}]+$')

    # Lines that are just repeated single characters (e.g. "--------", "========")
    _REPEATED_CHAR_RE = re.compile(r'^(.)\1{3,}$')

    @staticmethod
    def normalize_text(text: str) -> str:
        """Strip, lowercase, remove extra whitespace, and filter OCR noise."""
        text = text.strip().lower()
        text = TextDiff._NOISE_RE.sub('', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def is_noise(text: str) -> bool:
        """Return True if text is likely OCR noise, not real readable text."""
        stripped = text.strip()
        if len(stripped) < 3:
            return True

        # Check each line — if ALL lines are decorative, it's noise
        lines = [l.strip() for l in stripped.splitlines() if l.strip()]
        if not lines:
            return True

        real_lines = 0
        for line in lines:
            # Skip lines that are just repeated/decorative chars
            if TextDiff._DECORATIVE_RE.match(line):
                continue
            if TextDiff._REPEATED_CHAR_RE.match(line):
                continue
            real_lines += 1

        if real_lines == 0:
            return True

        # After normalize, check alpha ratio
        cleaned = TextDiff.normalize_text(stripped)
        if len(cleaned) < 3:
            return True
        alpha_count = sum(1 for c in cleaned if c.isalnum())
        if alpha_count / len(cleaned) < 0.3:
            return True

        return False

    @staticmethod
    def is_same(text1: str, text2: str, threshold: float = 0.85) -> bool:
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
