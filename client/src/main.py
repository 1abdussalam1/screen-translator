import sys
import os
import asyncio
import logging
from pathlib import Path

# Ensure src directory is on path (works both in dev and PyInstaller bundle)
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    _src_dir = Path(sys._MEIPASS)
else:
    _src_dir = Path(__file__).parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QBrush

try:
    import qasync
    _QASYNC_AVAILABLE = True
except ImportError:
    _QASYNC_AVAILABLE = False

from config import APP_VERSION, APP_NAME, load_config, save_config
from translation_cache import TranslationCache
from api_client import APIClient
from capture_engine import CaptureEngine, CaptureState
from overlay import CaptureOverlay
from translation_panel import TranslationPanel
from settings_dialog import SettingsDialog
from auto_updater import AutoUpdater
from toggle_button import FloatingToggleButton
from config import CACHE_DB

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def _make_ocr_engine(config: dict):
    """Select and return the best available OCR engine based on config."""
    from ocr.windows_ocr import WindowsOCR
    from ocr.tesseract_ocr import TesseractOCR

    engine_pref = config.get('ocr_engine', 'auto')

    if engine_pref == 'windows':
        engine = WindowsOCR()
        if engine.is_available():
            return engine
        logger.warning("Windows OCR requested but not available. Falling back.")

    elif engine_pref == 'tesseract':
        engine = TesseractOCR()
        if engine.is_available():
            return engine
        logger.warning("Tesseract requested but not available.")
        return None

    else:  # auto
        win = WindowsOCR()
        if win.is_available():
            return win
        tess = TesseractOCR()
        if tess.is_available():
            return tess

    return None


def _create_tray_icon(color: str = '#00AA00') -> QIcon:
    """Create a simple colored-square tray icon programmatically."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 8, 8)

    # Draw 'T' for Translator
    painter.setPen(QColor('#FFFFFF'))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, 'T')
    painter.end()
    return QIcon(pixmap)


class ScreenTranslatorApp:
    """Main application controller."""

    TRAY_COLORS = {
        CaptureState.IDLE: '#00AA00',
        CaptureState.CAPTURING: '#00AA00',
        CaptureState.OCR_RUNNING: '#FFAA00',
        CaptureState.TRANSLATING: '#FFAA00',
        CaptureState.ERROR: '#CC0000',
        'paused': '#888888',
    }

    def __init__(self, app: QApplication):
        self.app = app
        self.config = load_config()
        self._paused = False

        # Cache
        cache_cfg = self.config.get('cache', {})
        self.cache = TranslationCache(
            CACHE_DB,
            max_entries=int(cache_cfg.get('max_entries', 10000))
        )

        # API client
        self.api_client = APIClient(
            server_url=self.config.get('server_url', ''),
            api_key=self.config.get('api_key', '')
        )
        self.api_client.provider = self.config.get('provider', 'server')
        or_config = self.config.get('openrouter', {})
        self.api_client.openrouter_key = or_config.get('api_key', '')
        self.api_client.openrouter_model = or_config.get('model', 'google/gemma-3-1b-it:free')

        # OCR engine
        self.ocr_engine = _make_ocr_engine(self.config)
        if self.ocr_engine is None:
            logger.warning("No OCR engine available! Translations will not work.")

        # Overlay (capture region border)
        self.overlay = CaptureOverlay(self.config)
        self.overlay.region_changed.connect(self._on_region_changed)
        self.overlay.show()

        # Translation panel (above overlay)
        self.panel = TranslationPanel(self.config)
        self.panel.set_position_from_overlay(self.overlay)
        self.panel.show()

        # Floating toggle button
        self.toggle_btn = FloatingToggleButton(self.config)
        self.toggle_btn.toggled.connect(self._on_toggle_button)
        self.toggle_btn.show()

        # Capture engine
        self.capture_engine = CaptureEngine(
            config=self.config,
            ocr_engine=self.ocr_engine,
            translation_cache=self.cache,
            api_client=self.api_client,
            on_translation_callback=None
        )
        self.capture_engine.translation_ready.connect(self._on_translation)
        self.capture_engine.status_changed.connect(self._on_status_changed)
        self.capture_engine.status_message.connect(self._on_status_message)
        self.capture_engine.error_occurred.connect(self._on_error)

        # System tray
        self._tray_icon = None
        self._setup_tray()

        # Auto updater
        self.auto_updater = AutoUpdater()

        # Start capture
        if self.ocr_engine:
            logger.info(f"OCR engine: {self.ocr_engine.name()}")
            self.panel.set_translation(f'✅ جاهز - محرك OCR: {self.ocr_engine.name()}')
            self.capture_engine.start()
        else:
            no_ocr_msg = '❌ لا يوجد محرك OCR! ثبّت Tesseract أو استخدم Windows 10+'
            logger.error(no_ocr_msg)
            self.panel.set_translation(no_ocr_msg)
            self._show_tray_message(
                'تحذير',
                'لم يتم العثور على محرك OCR. يرجى تثبيت Tesseract.',
                QSystemTrayIcon.MessageIcon.Warning
            )

        # Check for updates after a delay (non-blocking)
        QTimer.singleShot(3000, self._check_updates)

        # First run notification
        self._check_first_run()

    def _setup_tray(self) -> None:
        self._tray_icon = QSystemTrayIcon(self.app)
        self._tray_icon.setIcon(_create_tray_icon('#00AA00'))
        self._tray_icon.setToolTip(APP_NAME)
        self._tray_icon.activated.connect(self._on_tray_activated)

        menu = QMenu()
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._action_toggle_visibility = menu.addAction('إخفاء')
        self._action_toggle_visibility.triggered.connect(self._toggle_visibility)

        self._action_settings = menu.addAction('الإعدادات')
        self._action_settings.triggered.connect(self._open_settings)

        self._action_pause_resume = menu.addAction('إيقاف مؤقت')
        self._action_pause_resume.triggered.connect(self._toggle_pause)

        menu.addSeparator()

        action_about = menu.addAction('حول')
        action_about.triggered.connect(self._show_about)

        menu.addSeparator()

        action_exit = menu.addAction('خروج')
        action_exit.triggered.connect(self._on_exit)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _toggle_visibility(self) -> None:
        if self.overlay.isVisible() and self.panel.isVisible():
            self.overlay.hide()
            self.panel.hide()
            self._action_toggle_visibility.setText('إظهار')
            self.toggle_btn.set_visible_state(False)
        else:
            self.overlay.show()
            self.panel.show()
            self.panel.set_position_from_overlay(self.overlay)
            self._action_toggle_visibility.setText('إخفاء')
            self.toggle_btn.set_visible_state(True)

    def _on_toggle_button(self, visible: bool) -> None:
        """Called when the floating toggle button is clicked."""
        if visible:
            self.overlay.show()
            self.panel.show()
            self.panel.set_position_from_overlay(self.overlay)
            self._action_toggle_visibility.setText('إخفاء')
        else:
            self.overlay.hide()
            self.panel.hide()
            self._action_toggle_visibility.setText('إظهار')

    def _toggle_pause(self) -> None:
        if self._paused:
            self._paused = False
            self.capture_engine.start()
            self._action_pause_resume.setText('إيقاف مؤقت')
            self._set_tray_color('#00AA00')
        else:
            self._paused = True
            self.capture_engine.stop()
            self._action_pause_resume.setText('استئناف')
            self._set_tray_color(self.TRAY_COLORS['paused'])

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.config, api_client=self.api_client)
        stats = self.cache.get_stats()
        dialog.set_cache_stats(stats)
        dialog.set_clear_cache_callback(self._clear_cache)

        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            new_config = dialog.get_config()
            self._apply_config(new_config)

    def _apply_config(self, new_config: dict) -> None:
        """Apply new configuration to all components."""
        self.config = new_config
        save_config(new_config)

        # Update API client
        self.api_client.server_url = new_config.get('server_url', '').rstrip('/')
        self.api_client.api_key = new_config.get('api_key', '')
        self.api_client.provider = new_config.get('provider', 'server')
        or_config = new_config.get('openrouter', {})
        self.api_client.openrouter_key = or_config.get('api_key', '')
        self.api_client.openrouter_model = or_config.get('model', '')

        # Update cache
        cache_cfg = new_config.get('cache', {})
        self.cache.max_entries = int(cache_cfg.get('max_entries', 10000))

        # Update OCR engine
        new_ocr = _make_ocr_engine(new_config)
        if new_ocr:
            self.ocr_engine = new_ocr
            self.capture_engine.ocr_engine = new_ocr

        # Update capture engine
        self.capture_engine.update_config(new_config)

        # Update overlay appearance
        appearance = new_config.get('appearance', {})
        self.overlay.update_style(
            appearance.get('capture_border_color', '#00FF00'),
            int(appearance.get('capture_border_width', 2))
        )

        # Update panel appearance
        self.panel.update_style(appearance)
        self.panel.set_position_from_overlay(self.overlay)

        # Update toggle button
        self.toggle_btn.update_style(appearance)

        # Update region
        region = new_config.get('capture_region', {})
        if region:
            self.overlay.set_region(
                region.get('x', 100), region.get('y', 100),
                region.get('width', 400), region.get('height', 200)
            )
            self.panel.set_position_from_overlay(self.overlay)

    def _clear_cache(self) -> None:
        self.cache.clear()
        logger.info("Cache cleared.")

    def _on_region_changed(self, x: int, y: int, w: int, h: int) -> None:
        """Called when user drags/resizes the overlay."""
        self.config['capture_region'] = {'x': x, 'y': y, 'width': w, 'height': h}
        self.capture_engine.update_config(self.config)
        self.panel.set_position_from_overlay(self.overlay)
        save_config(self.config)

    def _on_status_message(self, message: str) -> None:
        """Show pipeline status in the translation panel."""
        self.panel.set_translation(message)
        self.panel.set_position_from_overlay(self.overlay)

    def _on_translation(self, text: str) -> None:
        self.panel.set_translation(text)
        self.panel.set_position_from_overlay(self.overlay)
        if not self.panel.isVisible():
            self.panel.show()

    def _on_status_changed(self, state: str) -> None:
        color = self.TRAY_COLORS.get(state, '#00AA00')
        if not self._paused:
            self._set_tray_color(color)

        status_map = {
            CaptureState.IDLE: APP_NAME,
            CaptureState.CAPTURING: f'{APP_NAME} - يلتقط...',
            CaptureState.OCR_RUNNING: f'{APP_NAME} - يتعرف على النص...',
            CaptureState.TRANSLATING: f'{APP_NAME} - يترجم...',
            CaptureState.ERROR: f'{APP_NAME} - خطأ',
        }
        if self._tray_icon:
            self._tray_icon.setToolTip(status_map.get(state, APP_NAME))

    def _on_error(self, message: str) -> None:
        logger.error(f"Capture error: {message}")
        self._set_tray_color(self.TRAY_COLORS[CaptureState.ERROR])

    def _set_tray_color(self, color: str) -> None:
        if self._tray_icon:
            self._tray_icon.setIcon(_create_tray_icon(color))

    def _show_about(self) -> None:
        QMessageBox.about(
            None,
            f'حول {APP_NAME}',
            f'<div dir="rtl">'
            f'<h2>مترجم الشاشة</h2>'
            f'<p>الإصدار: {APP_VERSION}</p>'
            f'<p>تطبيق لالتقاط منطقة من الشاشة والتعرف على النصوص وترجمتها '
            f'تلقائياً إلى العربية باستخدام الذكاء الاصطناعي.</p>'
            f'</div>'
        )

    def _check_updates(self) -> None:
        """Trigger async update check."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    self.auto_updater.check_for_updates(
                        self.api_client, APP_VERSION
                    )
                )
            else:
                loop.run_until_complete(
                    self.auto_updater.check_for_updates(
                        self.api_client, APP_VERSION
                    )
                )
        except Exception as e:
            logger.warning(f"Could not schedule update check: {e}")

    def _check_first_run(self) -> None:
        """Show first-run notification if no previous config exists."""
        from config import CONFIG_FILE
        if not CONFIG_FILE.exists():
            QTimer.singleShot(1000, lambda: self._show_tray_message(
                'مرحباً بك!',
                'اسحب المربع الأخضر فوق النص الذي تريد ترجمته',
                QSystemTrayIcon.MessageIcon.Information
            ))

    def _show_tray_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information
    ) -> None:
        if self._tray_icon and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon.showMessage(title, message, icon, 5000)

    def _on_exit(self) -> None:
        """Clean up and exit."""
        self.capture_engine.stop()
        self.cache.close()
        save_config(self.config)
        if self._tray_icon:
            self._tray_icon.hide()
        self.app.quit()


def main() -> None:
    _setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # Prevent app from quitting when last window is closed (tray app)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            'خطأ',
            'لا يوجد دعم لأيقونة صينية على هذا النظام.'
        )
        sys.exit(1)

    if _QASYNC_AVAILABLE:
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        with loop:
            controller = ScreenTranslatorApp(app)
            loop.run_forever()
    else:
        logger.warning("qasync not available — falling back to synchronous event loop.")
        controller = ScreenTranslatorApp(app)
        sys.exit(app.exec())


if __name__ == '__main__':
    main()
