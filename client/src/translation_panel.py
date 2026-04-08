import logging
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPainterPath

logger = logging.getLogger(__name__)

PANEL_MARGIN = 8
CORNER_RADIUS = 8
MIN_PANEL_HEIGHT = 40


class TranslationPanel(QWidget):
    """
    Frameless, always-on-top semi-transparent panel that displays Arabic translation.
    Positioned above the capture overlay. Supports RTL text, configurable colors/fonts.
    """

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumHeight(MIN_PANEL_HEIGHT)

        self._bg_color = QColor('#000000')
        self._bg_opacity = 0.8
        self._text_color = QColor('#FFFFFF')
        self._font_family = 'Arial'
        self._font_size = 16

        # Main label
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        layout.addWidget(self._label)
        self.setLayout(layout)

        self.update_style(config.get('appearance', {}))
        self.set_translation('جاري...')

    def update_style(self, appearance: dict) -> None:
        """Apply color/font settings from appearance config dict."""
        bg_hex = appearance.get('translation_bg_color', '#000000')
        self._bg_color = QColor(bg_hex)
        self._bg_opacity = float(appearance.get('translation_bg_opacity', 0.8))
        text_hex = appearance.get('translation_text_color', '#FFFFFF')
        self._text_color = QColor(text_hex)
        self._font_family = appearance.get('translation_font_family', 'Arial')
        self._font_size = int(appearance.get('translation_font_size', 16))

        font = QFont(self._font_family, self._font_size)
        self._label.setFont(font)
        self._label.setStyleSheet(f'color: {text_hex}; background: transparent;')
        self.update()

    def set_translation(self, text: str) -> None:
        """Update the displayed translation text and resize panel accordingly."""
        self._label.setText(text)
        self._label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._adjust_height()
        self.update()

    def _adjust_height(self) -> None:
        """Resize height to fit the current text."""
        self._label.adjustSize()
        hint = self._label.sizeHint()
        new_height = max(MIN_PANEL_HEIGHT, hint.height() + 2 * PANEL_MARGIN)
        self.setFixedHeight(new_height)

    def set_position_from_overlay(self, overlay) -> None:
        """Position this panel directly above the given CaptureOverlay widget."""
        region = overlay.get_region()
        x = region['x']
        y = region['y']
        w = region['width']
        panel_h = self.height()
        # Place above overlay with a small gap
        self.setFixedWidth(w)
        self.move(x, max(0, y - panel_h - 4))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = QColor(self._bg_color)
        bg.setAlphaF(self._bg_opacity)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), CORNER_RADIUS, CORNER_RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawPath(path)
        painter.end()
        super().paintEvent(event)
