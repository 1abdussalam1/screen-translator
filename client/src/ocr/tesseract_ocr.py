import os
import logging
from PIL import Image
from .base import OCREngine

logger = logging.getLogger(__name__)

_TESSERACT_AVAILABLE = None

# Common Tesseract install paths on Windows
_WIN_TESSERACT_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(
        os.environ.get('USERNAME', 'user')
    ),
]


def _setup_tesseract_path():
    """Set pytesseract path to Tesseract executable on Windows."""
    try:
        import pytesseract
        # If already works, don't change
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            pass
        # Try known Windows paths
        for path in _WIN_TESSERACT_PATHS:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                pytesseract.get_tesseract_version()
                logger.info(f"Tesseract found at: {path}")
                return True
        return False
    except Exception:
        return False


def _check_tesseract() -> bool:
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is None:
        _TESSERACT_AVAILABLE = _setup_tesseract_path()
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
