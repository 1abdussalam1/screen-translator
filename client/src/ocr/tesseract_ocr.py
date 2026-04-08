import logging
from PIL import Image
from .base import OCREngine

logger = logging.getLogger(__name__)

_TESSERACT_AVAILABLE = None


def _check_tesseract() -> bool:
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is None:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            _TESSERACT_AVAILABLE = True
        except Exception:
            _TESSERACT_AVAILABLE = False
    return _TESSERACT_AVAILABLE


class TesseractOCR(OCREngine):
    """OCR engine using Tesseract via pytesseract."""

    TESSERACT_CONFIG = '--oem 3 --psm 6'

    def extract_text(self, image: Image.Image) -> str:
        """Extract text from image using Tesseract."""
        try:
            import pytesseract
            text = pytesseract.image_to_string(image, config=self.TESSERACT_CONFIG)
            return text.strip()
        except Exception as e:
            logger.error(f"Tesseract OCR error: {e}")
            return ''

    def is_available(self) -> bool:
        return _check_tesseract()

    def name(self) -> str:
        return 'Tesseract OCR'
