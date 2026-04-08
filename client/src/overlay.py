import logging
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import (
    Qt, QRect, QPoint, QSize, pyqtSignal, QRegion
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QCursor

logger = logging.getLogger(__name__)

HANDLE_SIZE = 10
MIN_WIDTH = 100
MIN_HEIGHT = 50

# Handle positions
HANDLE_TOP_LEFT = 0
HANDLE_TOP_MID = 1
HANDLE_TOP_RIGHT = 2
HANDLE_MID_RIGHT = 3
HANDLE_BOT_RIGHT = 4
HANDLE_BOT_MID = 5
HANDLE_BOT_LEFT = 6
HANDLE_MID_LEFT = 7


class CaptureOverlay(QWidget):
    """
    Frameless, always-on-top transparent overlay that shows a colored border
    around the capture region. The interior is click-through.
    8 resize handles + drag from border area.
    """
    region_changed = pyqtSignal(int, int, int, int)  # x, y, w, h

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._border_color = QColor(config.get('appearance', {}).get('capture_border_color', '#00FF00'))
        self._border_width = config.get('appearance', {}).get('capture_border_width', 2)

        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        region = config.get('capture_region', {'x': 100, 'y': 100, 'width': 400, 'height': 200})
        self.move(region['x'], region['y'])
        self.resize(region['width'], region['height'])

        self._drag_active = False
        self._drag_start_pos = QPoint()
        self._drag_start_win_pos = QPoint()

        self._resize_handle = -1
        self._resize_start_pos = QPoint()
        self._resize_start_geom = QRect()

        self._update_mask()

    def _handle_rects(self) -> list:
        """Return list of 8 QRect objects for the resize handles."""
        w, h = self.width(), self.height()
        hs = HANDLE_SIZE
        half = hs // 2
        return [
            QRect(0, 0, hs, hs),                             # TL
            QRect(w // 2 - half, 0, hs, hs),                 # TM
            QRect(w - hs, 0, hs, hs),                        # TR
            QRect(w - hs, h // 2 - half, hs, hs),            # MR
            QRect(w - hs, h - hs, hs, hs),                   # BR
            QRect(w // 2 - half, h - hs, hs, hs),            # BM
            QRect(0, h - hs, hs, hs),                        # BL
            QRect(0, h // 2 - half, hs, hs),                 # ML
        ]

    def _border_region(self) -> QRegion:
        """Return a QRegion that covers only the border + handles (not the interior)."""
        w, h = self.width(), self.height()
        bw = max(self._border_width, HANDLE_SIZE)
        outer = QRegion(0, 0, w, h)
        inner = QRegion(bw, bw, w - 2 * bw, h - 2 * bw)
        return outer.subtracted(inner)

    def _update_mask(self) -> None:
        """Apply mask so only the border area receives mouse events."""
        self.setMask(self._border_region())

    def resizeEvent(self, event) -> None:
        self._update_mask()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Draw border
        pen = QPen(self._border_color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        bw = self._border_width
        painter.drawRect(bw // 2, bw // 2, self.width() - bw, self.height() - bw)

        # Draw handles
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._border_color))
        for rect in self._handle_rects():
            painter.fillRect(rect, self._border_color)

        painter.end()

    def _hit_handle(self, pos: QPoint) -> int:
        """Return handle index if pos is in a handle, else -1."""
        for i, rect in enumerate(self._handle_rects()):
            if rect.contains(pos):
                return i
        return -1

    def _in_border(self, pos: QPoint) -> bool:
        """Return True if pos is in the border region (for drag)."""
        return self._border_region().contains(pos)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            handle = self._hit_handle(pos)
            if handle >= 0:
                self._resize_handle = handle
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
            elif self._in_border(pos):
                self._drag_active = True
                self._drag_start_pos = event.globalPosition().toPoint()
                self._drag_start_win_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.pos()

        if self._resize_handle >= 0:
            self._do_resize(event.globalPosition().toPoint())
            return

        if self._drag_active:
            delta = event.globalPosition().toPoint() - self._drag_start_pos
            new_pos = self._drag_start_win_pos + delta
            self.move(new_pos)
            self._emit_region()
            return

        # Update cursor
        handle = self._hit_handle(pos)
        cursors = [
            Qt.CursorShape.SizeFDiagCursor,
            Qt.CursorShape.SizeVerCursor,
            Qt.CursorShape.SizeBDiagCursor,
            Qt.CursorShape.SizeHorCursor,
            Qt.CursorShape.SizeFDiagCursor,
            Qt.CursorShape.SizeVerCursor,
            Qt.CursorShape.SizeBDiagCursor,
            Qt.CursorShape.SizeHorCursor,
        ]
        if handle >= 0:
            self.setCursor(QCursor(cursors[handle]))
        elif self._in_border(pos):
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resize_handle >= 0 or self._drag_active:
                self._emit_region()
            self._resize_handle = -1
            self._drag_active = False
        super().mouseReleaseEvent(event)

    def _do_resize(self, global_pos: QPoint) -> None:
        """Resize the window based on handle being dragged."""
        delta = global_pos - self._resize_start_pos
        geom = QRect(self._resize_start_geom)
        dx, dy = delta.x(), delta.y()

        h = self._resize_handle
        if h == HANDLE_TOP_LEFT:
            geom.setLeft(geom.left() + dx)
            geom.setTop(geom.top() + dy)
        elif h == HANDLE_TOP_MID:
            geom.setTop(geom.top() + dy)
        elif h == HANDLE_TOP_RIGHT:
            geom.setRight(geom.right() + dx)
            geom.setTop(geom.top() + dy)
        elif h == HANDLE_MID_RIGHT:
            geom.setRight(geom.right() + dx)
        elif h == HANDLE_BOT_RIGHT:
            geom.setRight(geom.right() + dx)
            geom.setBottom(geom.bottom() + dy)
        elif h == HANDLE_BOT_MID:
            geom.setBottom(geom.bottom() + dy)
        elif h == HANDLE_BOT_LEFT:
            geom.setLeft(geom.left() + dx)
            geom.setBottom(geom.bottom() + dy)
        elif h == HANDLE_MID_LEFT:
            geom.setLeft(geom.left() + dx)

        # Enforce minimum size
        if geom.width() < MIN_WIDTH:
            if h in (HANDLE_TOP_LEFT, HANDLE_MID_LEFT, HANDLE_BOT_LEFT):
                geom.setLeft(geom.right() - MIN_WIDTH)
            else:
                geom.setRight(geom.left() + MIN_WIDTH)
        if geom.height() < MIN_HEIGHT:
            if h in (HANDLE_TOP_LEFT, HANDLE_TOP_MID, HANDLE_TOP_RIGHT):
                geom.setTop(geom.bottom() - MIN_HEIGHT)
            else:
                geom.setBottom(geom.top() + MIN_HEIGHT)

        self.setGeometry(geom)
        self._emit_region()

    def _emit_region(self) -> None:
        pos = self.pos()
        self.region_changed.emit(pos.x(), pos.y(), self.width(), self.height())

    def get_region(self) -> dict:
        pos = self.pos()
        return {
            'x': pos.x(),
            'y': pos.y(),
            'width': self.width(),
            'height': self.height()
        }

    def set_region(self, x: int, y: int, w: int, h: int) -> None:
        self.move(x, y)
        self.resize(max(w, MIN_WIDTH), max(h, MIN_HEIGHT))
        self._update_mask()

    def update_style(self, border_color: str, border_width: int) -> None:
        self._border_color = QColor(border_color)
        self._border_width = border_width
        self._update_mask()
        self.update()
