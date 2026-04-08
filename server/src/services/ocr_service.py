import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed — OCR endpoint will be unavailable")


def extract_text(image_bytes: bytes, language: str = "eng") -> str:
    """
    Extract text from raw image bytes using Tesseract OCR.
    Raises RuntimeError if Tesseract is not available.
    """
    if not _TESSERACT_AVAILABLE:
        raise RuntimeError(
            "pytesseract is not installed. Install it with: pip install pytesseract"
        )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Convert to RGB to avoid issues with RGBA/palette images
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        text = pytesseract.image_to_string(image, lang=language)
        return text.strip()
    except Exception as exc:
        logger.error("OCR extraction failed: %s", exc)
        raise RuntimeError(f"OCR failed: {exc}") from exc
