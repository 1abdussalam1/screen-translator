import asyncio
import logging
import io
import struct
from PIL import Image

from .base import OCREngine

logger = logging.getLogger(__name__)

_WINRT_AVAILABLE = None


def _check_winrt() -> bool:
    global _WINRT_AVAILABLE
    if _WINRT_AVAILABLE is None:
        try:
            import winrt.windows.media.ocr as _ocr  # noqa: F401
            import winrt.windows.globalization as _glob  # noqa: F401
            import winrt.windows.graphics.imaging as _img  # noqa: F401
            _WINRT_AVAILABLE = True
        except (ImportError, Exception):
            _WINRT_AVAILABLE = False
    return _WINRT_AVAILABLE


class WindowsOCR(OCREngine):
    """OCR engine using Windows built-in OCR (WinRT)."""

    def __init__(self):
        self._engine = None
        self._loop = None

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _init_engine(self):
        """Lazily initialize the Windows OCR engine."""
        if self._engine is not None:
            return
        try:
            import winrt.windows.globalization as globalization
            import winrt.windows.media.ocr as ocr

            # Use the first available language or English
            languages = globalization.Language.get_available_recognizer_languages()
            lang = None
            for l in languages:
                lang = l
                break
            if lang is None:
                lang = globalization.Language('en')
            self._engine = ocr.OcrEngine.try_create_from_language(lang)
        except Exception as e:
            logger.error(f"Failed to init Windows OCR engine: {e}")
            self._engine = None

    def _pil_to_software_bitmap(self, image: Image.Image):
        """Convert PIL Image to WinRT SoftwareBitmap."""
        import winrt.windows.graphics.imaging as imaging
        import winrt.windows.storage.streams as streams

        # Convert to RGBA
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        width, height = image.size
        raw_bytes = image.tobytes()

        # Create a DataWriter to write the bytes
        data_writer = streams.DataWriter()
        data_writer.write_bytes(list(raw_bytes))
        buffer = data_writer.detach_buffer()

        bitmap = imaging.SoftwareBitmap.create_copy_from_buffer(
            buffer,
            imaging.BitmapPixelFormat.RGBA8,
            width,
            height,
            imaging.BitmapAlphaMode.PREMULTIPLIED
        )
        return bitmap

    async def _do_ocr_async(self, image: Image.Image) -> str:
        """Run async Windows OCR."""
        try:
            import winrt.windows.media.ocr as ocr
            import winrt.windows.graphics.imaging as imaging

            self._init_engine()
            if self._engine is None:
                return ''

            bitmap = self._pil_to_software_bitmap(image)
            result = await self._engine.recognize_async(bitmap)
            if result and result.text:
                return result.text
            return ''
        except Exception as e:
            logger.error(f"Windows OCR async error: {e}")
            return ''

    def extract_text(self, image: Image.Image) -> str:
        """Extract text from image using Windows OCR."""
        try:
            loop = self._get_or_create_loop()
            if loop.is_running():
                # We're inside a running loop; use run_coroutine_threadsafe if needed
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self._do_ocr_async(image), loop
                )
                return future.result(timeout=10)
            else:
                return loop.run_until_complete(self._do_ocr_async(image))
        except Exception as e:
            logger.error(f"Windows OCR extract_text error: {e}")
            return ''

    def is_available(self) -> bool:
        return _check_winrt()

    def name(self) -> str:
        return 'Windows OCR'
