import asyncio
import logging
from typing import Optional, Callable, Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
import mss
import mss.tools
from PIL import Image

from text_diff import TextDiff
from translation_cache import TranslationCache
from api_client import APIClient

logger = logging.getLogger(__name__)


class CaptureState:
    IDLE = 'idle'
    CAPTURING = 'capturing'
    OCR_RUNNING = 'ocr_running'
    TRANSLATING = 'translating'
    ERROR = 'error'


class CaptureEngine(QObject):
    """Main pipeline: capture -> OCR -> diff check -> cache -> API -> display."""

    status_changed = pyqtSignal(str)        # CaptureState value
    status_message = pyqtSignal(str)         # human-readable status for panel
    translation_ready = pyqtSignal(str)      # translated text
    error_occurred = pyqtSignal(str)         # error message

    def __init__(
        self,
        config: dict,
        ocr_engine,
        translation_cache: TranslationCache,
        api_client: APIClient,
        on_translation_callback: Optional[Callable[[str], Any]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.config = config
        self.ocr_engine = ocr_engine
        self.translation_cache = translation_cache
        self.api_client = api_client
        self.on_translation_callback = on_translation_callback

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)

        self._state = CaptureState.IDLE
        self._previous_text: Optional[str] = None
        self._is_running = False
        self._text_diff = TextDiff()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
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

    def start(self) -> None:
        """Start the periodic capture timer."""
        interval_ms = int(self.config.get('capture_interval_seconds', 2) * 1000)
        self._is_running = True
        self._timer.start(interval_ms)
        self._set_state(CaptureState.IDLE)
        logger.info(f"CaptureEngine started, interval={interval_ms}ms")

    def stop(self) -> None:
        """Stop the periodic capture timer."""
        self._is_running = False
        self._timer.stop()
        self._set_state(CaptureState.IDLE)
        logger.info("CaptureEngine stopped.")

    def update_config(self, config: dict) -> None:
        """Update config and restart timer if running."""
        self.config = config
        if self._is_running:
            interval_ms = int(config.get('capture_interval_seconds', 2) * 1000)
            self._timer.setInterval(interval_ms)

    def _set_state(self, state: str) -> None:
        self._state = state
        self.status_changed.emit(state)

    def _on_timer(self) -> None:
        """Called by QTimer. Runs the async pipeline."""
        if self._state in (CaptureState.OCR_RUNNING, CaptureState.TRANSLATING):
            return  # Don't stack captures

        loop = self._get_loop()
        if loop.is_running():
            asyncio.ensure_future(self.capture_and_translate())
        else:
            loop.run_until_complete(self.capture_and_translate())

    async def capture_and_translate(self) -> None:
        """Full pipeline: capture -> OCR -> diff -> cache -> API -> callback."""
        try:
            # 1. Capture
            self._set_state(CaptureState.CAPTURING)
            region = self.config.get('capture_region', {})
            image = await asyncio.get_event_loop().run_in_executor(
                None, self._capture_screen, region
            )
            if image is None:
                self.status_message.emit('⚠️ فشل التقاط الشاشة')
                self._set_state(CaptureState.IDLE)
                return

            # 2. OCR
            self._set_state(CaptureState.OCR_RUNNING)
            raw_text = await asyncio.get_event_loop().run_in_executor(
                None, self._run_ocr, image
            )
            raw_text = (raw_text or '').strip()

            if not raw_text or len(raw_text) < 3:
                self._set_state(CaptureState.IDLE)
                return

            # 2.5. Noise filter — skip garbage/symbols from OCR
            if self._text_diff.is_noise(raw_text):
                self._set_state(CaptureState.IDLE)
                return

            # 3. Diff check
            if self._previous_text is not None:
                if self._text_diff.is_same(self._previous_text, raw_text):
                    self._set_state(CaptureState.IDLE)
                    return

            self._previous_text = raw_text

            # 4. Cache check
            target_lang = self.config.get('target_language', 'ar')
            cached = self.translation_cache.get(raw_text, target_lang)
            if cached is not None:
                self._deliver_translation(cached)
                self._set_state(CaptureState.IDLE)
                return

            # 5. API call
            self._set_state(CaptureState.TRANSLATING)
            source_lang = self.config.get('source_language', 'auto')
            try:
                result = await self.api_client.translate(raw_text, source_lang, target_lang)
                translated = result.get('translation', '') or result.get('translated_text', '')
                if translated:
                    # 6. Save to cache
                    self.translation_cache.put(
                        raw_text, translated,
                        result.get('source_language_detected', source_lang),
                        target_lang
                    )
                    # 7. Deliver
                    self._deliver_translation(translated)
                else:
                    logger.warning("Server returned empty translation, skipping.")
            except PermissionError as e:
                logger.warning(f"Permission error: {e}")
            except ConnectionError as e:
                logger.warning(f"Connection error: {e}")
            except TimeoutError as e:
                logger.warning(f"Timeout: {e}")
            except Exception as e:
                logger.error(f"Translation error: {e}")

        except Exception as e:
            logger.error(f"Capture pipeline error: {e}", exc_info=True)
        finally:
            self._set_state(CaptureState.IDLE)

    def _capture_screen(self, region: dict) -> Optional[Image.Image]:
        """Capture the specified screen region using mss."""
        try:
            with mss.mss() as sct:
                monitor = {
                    'left': int(region.get('x', 100)),
                    'top': int(region.get('y', 100)),
                    'width': int(region.get('width', 400)),
                    'height': int(region.get('height', 200))
                }
                screenshot = sct.grab(monitor)
                return Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            return None

    def _run_ocr(self, image: Image.Image) -> str:
        """Run OCR on the captured image."""
        try:
            return self.ocr_engine.extract_text(image)
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return ''

    def _deliver_translation(self, text: str) -> None:
        """Deliver translation to callback and emit signal."""
        self.translation_ready.emit(text)
        if self.on_translation_callback:
            self.on_translation_callback(text)

    def _show_error(self, message: str) -> None:
        """Emit error signal only (no panel display)."""
        self.error_occurred.emit(message)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def state(self) -> str:
        return self._state
