import logging
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QFont

logger = logging.getLogger(__name__)


class FloatingToggleButton(QWidget):
    """
    Small draggable floating button to show/hide the overlay and translation panel.
    Always visible on screen, customizable color, opacity, and size.
    """
    toggled = pyqtSignal(bool)  # True = visible, False = hidden

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

        self._visible_state = True  # overlay is visible
        self._bg_color = QColor('#333333')
        self._bg_opacity = 0.7
        self._btn_size = 32

        self._drag_active = False
        self._drag_start_pos = QPoint()
        self._drag_start_win_pos = QPoint()
        self._was_dragged = False

        self.update_style(config.get('appearance', {}))
        # Position at top-right of screen
        self.move(20, 20)

    def update_style(self, appearance: dict) -> None:
        color_hex = appearance.get('toggle_button_color', '#333333')
        self._bg_color = QColor(color_hex)
        self._bg_opacity = float(appearance.get('toggle_button_opacity', 0.7))
        self._btn_size = int(appearance.get('toggle_button_size', 32))
        self.setFixedSize(self._btn_size, self._btn_size)
        self.update()

    def set_visible_state(self, visible: bool) -> None:
        self._visible_state = visible
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = QColor(self._bg_color)
        bg.setAlphaF(self._bg_opacity)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 6, 6)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawPath(path)

        # Draw icon: eye open/closed
        painter.setPen(QColor('#FFFFFF'))
        font = QFont('Arial', max(8, self._btn_size // 3))
        font.setBold(True)
        painter.setFont(font)
        icon = 'T' if self._visible_state else 'T'
        # Draw a line through when hidden
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, icon)

        if not self._visible_state:
            # Draw strikethrough line
            painter.setPen(QColor(255, 80, 80, 200))
            y_mid = self.height() // 2
            painter.drawLine(4, y_mid, self.width() - 4, y_mid)

        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_win_pos = self.pos()
            self._was_dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_active:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            if delta.manhattanLength() > 5:
                self._was_dragged = True
            new_pos = self._drag_start_win_pos + delta
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            if not self._was_dragged:
                # Click: toggle visibility
                self._visible_state = not self._visible_state
                self.toggled.emit(self._visible_state)
                self.update()
        super().mouseReleaseEvent(event)
