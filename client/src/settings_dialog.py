import asyncio
import logging
import copy
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
    QSlider, QComboBox, QCheckBox, QColorDialog, QFontDialog,
    QProgressBar, QDialogButtonBox, QSizePolicy, QMessageBox,
    QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont

logger = logging.getLogger(__name__)

LANGUAGES = [
    ('auto', 'تلقائي'),
    ('en', 'الإنجليزية'),
    ('ar', 'العربية'),
    ('fr', 'الفرنسية'),
    ('de', 'الألمانية'),
    ('es', 'الإسبانية'),
    ('it', 'الإيطالية'),
    ('zh', 'الصينية'),
    ('ja', 'اليابانية'),
    ('ko', 'الكورية'),
    ('ru', 'الروسية'),
    ('pt', 'البرتغالية'),
    ('tr', 'التركية'),
]

OCR_ENGINES = [
    ('auto', 'تلقائي'),
    ('windows', 'Windows OCR'),
    ('tesseract', 'Tesseract OCR'),
]


def _color_button_style(hex_color: str) -> str:
    return (
        f'background-color: {hex_color}; border: 1px solid #888; '
        f'border-radius: 4px; min-width: 60px; min-height: 24px;'
    )


class SettingsDialog(QDialog):
    """Settings dialog with 5 tabbed sections."""

    def __init__(self, config: dict, api_client=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowTitle('الإعدادات')
        self.setMinimumWidth(500)
        self.setMinimumHeight(460)

        self._config = copy.deepcopy(config)
        self._api_client = api_client

        main_layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_connection_tab(), 'الاتصال')
        self._tabs.addTab(self._build_appearance_tab(), 'المظهر')
        self._tabs.addTab(self._build_behavior_tab(), 'السلوك')
        self._tabs.addTab(self._build_cache_tab(), 'التخزين المؤقت')
        self._tabs.addTab(self._build_about_tab(), 'حول')
        main_layout.addWidget(self._tabs)

        # Save / Cancel buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('حفظ')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('إلغاء')
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    #  Tab 1: Connection
    # ------------------------------------------------------------------ #
    def _build_connection_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        self._server_url_edit = QLineEdit(self._config.get('server_url', ''))
        self._server_url_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addRow('رابط الخادم:', self._server_url_edit)

        self._api_key_edit = QLineEdit(self._config.get('api_key', ''))
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addRow('مفتاح API:', self._api_key_edit)

        test_btn = QPushButton('اختبار الاتصال')
        test_btn.clicked.connect(self._test_connection)
        layout.addRow('', test_btn)

        self._conn_status_label = QLabel('')
        self._conn_status_label.setWordWrap(True)
        layout.addRow('الحالة:', self._conn_status_label)

        # Model selector
        self._model_combo = QComboBox()
        self._model_combo.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        current_model = self._config.get('ollama_model', '')
        if current_model:
            self._model_combo.addItem(current_model)
        layout.addRow('نموذج الترجمة:', self._model_combo)

        fetch_btn = QPushButton('تحديث قائمة النماذج')
        fetch_btn.clicked.connect(self._fetch_models)
        layout.addRow('', fetch_btn)

        return widget

    # ------------------------------------------------------------------ #
    #  Tab 2: Appearance
    # ------------------------------------------------------------------ #
    def _build_appearance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        appearance = self._config.get('appearance', {})

        # Border color
        self._border_color_btn = QPushButton()
        self._border_color = appearance.get('capture_border_color', '#00FF00')
        self._border_color_btn.setStyleSheet(_color_button_style(self._border_color))
        self._border_color_btn.clicked.connect(lambda: self._pick_color('border'))
        layout.addRow('لون إطار التحديد:', self._border_color_btn)

        # Border width
        self._border_width_spin = QSpinBox()
        self._border_width_spin.setRange(1, 10)
        self._border_width_spin.setValue(int(appearance.get('capture_border_width', 2)))
        layout.addRow('سُمك الإطار (بكسل):', self._border_width_spin)

        # BG color
        self._bg_color_btn = QPushButton()
        self._bg_color = appearance.get('translation_bg_color', '#000000')
        self._bg_color_btn.setStyleSheet(_color_button_style(self._bg_color))
        self._bg_color_btn.clicked.connect(lambda: self._pick_color('bg'))
        layout.addRow('لون خلفية الترجمة:', self._bg_color_btn)

        # Opacity
        opacity_layout = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(10, 100)
        current_opacity = int(float(appearance.get('translation_bg_opacity', 0.8)) * 100)
        self._opacity_slider.setValue(current_opacity)
        self._opacity_value_label = QLabel(f'{current_opacity}%')
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_value_label.setText(f'{v}%')
        )
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_value_label)
        opacity_widget = QWidget()
        opacity_widget.setLayout(opacity_layout)
        layout.addRow('شفافية الخلفية:', opacity_widget)

        # Text color
        self._text_color_btn = QPushButton()
        self._text_color = appearance.get('translation_text_color', '#FFFFFF')
        self._text_color_btn.setStyleSheet(_color_button_style(self._text_color))
        self._text_color_btn.clicked.connect(lambda: self._pick_color('text'))
        layout.addRow('لون نص الترجمة:', self._text_color_btn)

        # Font family
        self._font_family_label = QLabel(appearance.get('translation_font_family', 'Arial'))
        font_btn = QPushButton('اختر الخط')
        font_btn.clicked.connect(self._pick_font)
        font_row = QHBoxLayout()
        font_row.addWidget(self._font_family_label)
        font_row.addWidget(font_btn)
        font_widget = QWidget()
        font_widget.setLayout(font_row)
        layout.addRow('نوع الخط:', font_widget)

        # Font size
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 72)
        self._font_size_spin.setValue(int(appearance.get('translation_font_size', 16)))
        layout.addRow('حجم الخط:', self._font_size_spin)

        return widget

    # ------------------------------------------------------------------ #
    #  Tab 3: Behavior
    # ------------------------------------------------------------------ #
    def _build_behavior_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        # Capture interval
        interval_layout = QHBoxLayout()
        self._interval_slider = QSlider(Qt.Orientation.Horizontal)
        self._interval_slider.setRange(1, 10)
        self._interval_slider.setValue(int(self._config.get('capture_interval_seconds', 2)))
        self._interval_value_label = QLabel(f'{self._interval_slider.value()} ثانية')
        self._interval_slider.valueChanged.connect(
            lambda v: self._interval_value_label.setText(f'{v} ثانية')
        )
        interval_layout.addWidget(self._interval_slider)
        interval_layout.addWidget(self._interval_value_label)
        interval_widget = QWidget()
        interval_widget.setLayout(interval_layout)
        layout.addRow('فترة الالتقاط:', interval_widget)

        # Source language
        self._source_lang_combo = QComboBox()
        for code, label in LANGUAGES:
            self._source_lang_combo.addItem(label, code)
        current_src = self._config.get('source_language', 'auto')
        idx = self._source_lang_combo.findData(current_src)
        if idx >= 0:
            self._source_lang_combo.setCurrentIndex(idx)
        layout.addRow('لغة المصدر:', self._source_lang_combo)

        # Target language
        self._target_lang_combo = QComboBox()
        for code, label in LANGUAGES:
            if code != 'auto':
                self._target_lang_combo.addItem(label, code)
        current_tgt = self._config.get('target_language', 'ar')
        idx = self._target_lang_combo.findData(current_tgt)
        if idx >= 0:
            self._target_lang_combo.setCurrentIndex(idx)
        layout.addRow('لغة الترجمة:', self._target_lang_combo)

        # OCR engine
        self._ocr_combo = QComboBox()
        for code, label in OCR_ENGINES:
            self._ocr_combo.addItem(label, code)
        current_ocr = self._config.get('ocr_engine', 'auto')
        idx = self._ocr_combo.findData(current_ocr)
        if idx >= 0:
            self._ocr_combo.setCurrentIndex(idx)
        layout.addRow('محرك التعرف الضوئي:', self._ocr_combo)

        return widget

    # ------------------------------------------------------------------ #
    #  Tab 4: Cache
    # ------------------------------------------------------------------ #
    def _build_cache_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)

        cache_cfg = self._config.get('cache', {})

        self._cache_enabled_cb = QCheckBox('تفعيل التخزين المؤقت')
        self._cache_enabled_cb.setChecked(cache_cfg.get('enabled', True))
        layout.addWidget(self._cache_enabled_cb)

        self._cache_progress = QProgressBar()
        self._cache_progress.setRange(0, int(cache_cfg.get('max_entries', 10000)))
        self._cache_progress.setValue(0)
        self._cache_progress.setFormat('%v / %m مدخلة')
        layout.addWidget(QLabel('استخدام التخزين المؤقت:'))
        layout.addWidget(self._cache_progress)

        self._cache_size_label = QLabel('الحجم: غير معروف')
        layout.addWidget(self._cache_size_label)

        clear_btn = QPushButton('مسح التخزين المؤقت')
        clear_btn.clicked.connect(self._clear_cache)
        layout.addWidget(clear_btn)

        refresh_btn = QPushButton('تحديث الإحصائيات')
        refresh_btn.clicked.connect(self._refresh_cache_stats)
        layout.addWidget(refresh_btn)

        layout.addStretch()
        return widget

    def _refresh_cache_stats(self) -> None:
        """Called when stats need refreshing (triggered externally or by user)."""
        # Stats updated externally via set_cache_stats()
        pass

    def set_cache_stats(self, stats: dict) -> None:
        """Update cache stats display."""
        count = stats.get('count', 0)
        max_entries = stats.get('max_entries', 10000)
        size_bytes = stats.get('size_bytes', 0)
        self._cache_progress.setMaximum(max_entries)
        self._cache_progress.setValue(count)
        size_kb = size_bytes / 1024
        self._cache_size_label.setText(f'الحجم: {size_kb:.1f} كيلوبايت')

    def _clear_cache(self) -> None:
        reply = QMessageBox.question(
            self, 'تأكيد',
            'هل تريد مسح جميع مدخلات التخزين المؤقت؟',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_cache_callback()

    def set_clear_cache_callback(self, callback) -> None:
        self._clear_cache_callback = callback

    def _clear_cache_callback(self) -> None:
        pass  # Replaced via set_clear_cache_callback

    # ------------------------------------------------------------------ #
    #  Tab 5: About
    # ------------------------------------------------------------------ #
    def _build_about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel('مترجم الشاشة')
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        from config import APP_VERSION
        version_label = QLabel(f'الإصدار: {APP_VERSION}')
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        desc = QLabel(
            'تطبيق لالتقاط منطقة من الشاشة والتعرف على النصوص وترجمتها '
            'تلقائياً إلى العربية باستخدام الذكاء الاصطناعي.\n\n'
            'يدعم محركات OCR المتعددة ويعمل بالكامل على جهازك.'
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        layout.addStretch()
        return widget

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    def _pick_color(self, target: str) -> None:
        mapping = {
            'border': (self._border_color, '_border_color', self._border_color_btn),
            'bg': (self._bg_color, '_bg_color', self._bg_color_btn),
            'text': (self._text_color, '_text_color', self._text_color_btn),
        }
        current_hex, attr, btn = mapping[target]
        color = QColorDialog.getColor(QColor(current_hex), self, 'اختر اللون')
        if color.isValid():
            hex_color = color.name()
            setattr(self, attr, hex_color)
            btn.setStyleSheet(_color_button_style(hex_color))

    def _pick_font(self) -> None:
        current_font = QFont(self._font_family_label.text())
        font, ok = QFontDialog.getFont(current_font, self, 'اختر الخط')
        if ok:
            self._font_family_label.setText(font.family())

    def _test_connection(self) -> None:
        self._conn_status_label.setStyleSheet('color: gray;')
        self._conn_status_label.setText('⏳ جاري الاختبار...')

        server_url = self._server_url_edit.text().rstrip('/')
        api_key    = self._api_key_edit.text().strip()

        # Run in background thread so UI never freezes
        import threading, httpx

        def _run():
            try:
                # 1) health check — no auth needed
                r = httpx.get(f"{server_url}/api/v1/health", timeout=8)
                if r.status_code != 200:
                    _done(False, f'السيرفر أعاد كود {r.status_code}')
                    return
                data = r.json()
                if data.get('ollama_status') != 'online':
                    _done(False, 'السيرفر متصل لكن Ollama غير متاح')
                    return

                # 2) validate API key if provided
                if api_key:
                    r2 = httpx.post(
                        f"{server_url}/api/v1/auth/validate",
                        json={"api_key": api_key},
                        timeout=8,
                    )
                    if r2.status_code == 200 and r2.json().get('valid'):
                        user = r2.json().get('user', '')
                        _done(True, f'✓ متصل — مرحباً {user}')
                    else:
                        _done(False, '✗ مفتاح API غير صحيح أو منتهي')
                else:
                    _done(True, '✓ السيرفر متصل (لم يتم إدخال API Key)')

            except httpx.ConnectError:
                _done(False, '✗ تعذر الوصول للسيرفر — تحقق من الرابط')
            except httpx.TimeoutException:
                _done(False, '✗ انتهت مهلة الاتصال')
            except Exception as e:
                _done(False, f'✗ خطأ: {e}')

        def _done(success: bool, msg: str):
            # Must update UI from main thread
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            color = 'green' if success else 'red'
            self._conn_status_label.setStyleSheet(f'color: {color};')
            self._conn_status_label.setText(msg)

        threading.Thread(target=_run, daemon=True).start()

    def _fetch_models(self) -> None:
        """Fetch available Ollama models from server."""
        if self._api_client is None:
            return
        self._api_client.server_url = self._server_url_edit.text().rstrip('/')
        try:
            import httpx
            url = f"{self._api_client.server_url}/api/v1/models"
            resp = httpx.get(url, timeout=10)
            data = resp.json()
            models = data.get('models', [])
            self._model_combo.clear()
            for m in models:
                self._model_combo.addItem(m)
            current = data.get('current_model', '')
            idx = self._model_combo.findText(current)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
        except Exception as e:
            self._model_combo.clear()
            self._model_combo.addItem(f'خطأ: {e}')

    def _on_accept(self) -> None:
        """Collect all settings and store in _config, then accept."""
        # Connection
        self._config['server_url'] = self._server_url_edit.text().strip()
        self._config['api_key'] = self._api_key_edit.text()
        if self._model_combo.count() > 0 and not self._model_combo.currentText().startswith('خطأ'):
            self._config['ollama_model'] = self._model_combo.currentText()

        # Appearance
        self._config['appearance']['capture_border_color'] = self._border_color
        self._config['appearance']['capture_border_width'] = self._border_width_spin.value()
        self._config['appearance']['translation_bg_color'] = self._bg_color
        self._config['appearance']['translation_bg_opacity'] = self._opacity_slider.value() / 100.0
        self._config['appearance']['translation_text_color'] = self._text_color
        self._config['appearance']['translation_font_family'] = self._font_family_label.text()
        self._config['appearance']['translation_font_size'] = self._font_size_spin.value()

        # Behavior
        self._config['capture_interval_seconds'] = self._interval_slider.value()
        self._config['source_language'] = self._source_lang_combo.currentData()
        self._config['target_language'] = self._target_lang_combo.currentData()
        self._config['ocr_engine'] = self._ocr_combo.currentData()

        # Cache
        self._config['cache']['enabled'] = self._cache_enabled_cb.isChecked()

        self.accept()

    def get_config(self) -> dict:
        return self._config
