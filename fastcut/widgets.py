from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QTransform,
)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame, QGraphicsScene, QGraphicsView, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from fastcut import theme


def fmt_ms(ms: int, with_ms: bool = True) -> str:
    ms = max(0, int(ms))
    total_s, msec = divmod(ms, 1000)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        base = f"{h}:{m:02d}:{s:02d}"
    else:
        base = f"{m:02d}:{s:02d}"
    return f"{base}.{msec // 10:02d}" if with_ms else base


def fmt_size(num: int) -> str:
    if num <= 0:
        return "--"
    units = ["B", "KB", "MB", "GB", "TB"]
    val = float(num)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            return f"{val:.0f} {unit}" if unit == "B" else f"{val:.1f} {unit}"
        val /= 1024
    return "--"


def media_icon(kind: str = "play", size: int = 36, color: str = "#FFFFFF") -> QPixmap:

    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    s = float(size)
    if kind == "play":
        path = QPainterPath()
        path.moveTo(s * 0.30, s * 0.18)
        path.lineTo(s * 0.82, s * 0.50)
        path.lineTo(s * 0.30, s * 0.82)
        path.closeSubpath()
        p.drawPath(path)
    else:
        w = s * 0.17
        p.drawRoundedRect(QRectF(s * 0.26, s * 0.20, w, s * 0.60), 1.5, 1.5)
        p.drawRoundedRect(QRectF(s * 0.57, s * 0.20, w, s * 0.60), 1.5, 1.5)
    p.end()
    return pm


def drop_icon(size: int = 30, color: str = "#B9A8FF") -> QPixmap:

    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s2 = float(size)
    p.drawLine(QPointF(s2 * 0.5, s2 * 0.16), QPointF(s2 * 0.5, s2 * 0.62))
    path = QPainterPath()
    path.moveTo(s2 * 0.32, s2 * 0.46)
    path.lineTo(s2 * 0.5, s2 * 0.64)
    path.lineTo(s2 * 0.68, s2 * 0.46)
    p.drawPath(path)
    tray = QPainterPath()
    tray.moveTo(s2 * 0.20, s2 * 0.72)
    tray.lineTo(s2 * 0.20, s2 * 0.84)
    tray.lineTo(s2 * 0.80, s2 * 0.84)
    tray.lineTo(s2 * 0.80, s2 * 0.72)
    p.drawPath(tray)
    p.end()
    return pm


class Panel(QWidget):

    def __init__(self, parent=None, radius: int = 0):
        super().__init__(parent)
        self._radius = radius

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self._radius, self._radius)
        p.fillPath(path, QColor("#000000"))
        p.setPen(QPen(QColor("#262626"), 1))
        p.drawPath(path)


class Orb(QWidget):


    clicked = Signal()
    contextRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(84, 84)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Fastcut 快剪 · 点击展开")
        self._hover = False
        self._pressed = False

    def set_diameter(self, diameter: int) -> None:
        self.setFixedSize(diameter, diameter)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self._pressed = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self.contextRequested.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        r = self.width() * 0.42 * (0.96 if self._pressed else 1.0)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#000000"))
        p.drawEllipse(QPointF(cx, cy), r, r)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#FFFFFF") if self._hover else QColor("#444444"),
                      1.4 if self._hover else 1.0))
        p.drawEllipse(QPointF(cx, cy), r - 0.7, r - 0.7)

        k = r / 42.0
        p.setPen(QPen(QColor("#FFFFFF"), 2.0 * k, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - 9 * k, cy - 9 * k), QPointF(cx + 7 * k, cy + 6 * k))
        p.drawLine(QPointF(cx + 9 * k, cy - 9 * k), QPointF(cx - 7 * k, cy + 6 * k))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#FFFFFF"), 1.7 * k))
        p.drawEllipse(QPointF(cx - 8.5 * k, cy + 10 * k), 3.4 * k, 3.4 * k)
        p.drawEllipse(QPointF(cx + 8.5 * k, cy + 10 * k), 3.4 * k, 3.4 * k)


class VideoView(QGraphicsView):


    def __init__(self, item: QGraphicsVideoItem, parent=None):
        super().__init__(parent)
        self._item = item
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.addItem(item)
        item.setAspectRatioMode(Qt.KeepAspectRatio)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background:#000000; border:none;")
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._rotate = 0
        self._mirror = False

    def apply_transform(self, rotate: int = 0, mirror: bool = False) -> None:

        self._rotate = int(rotate) % 360
        self._mirror = bool(mirror)
        self._relayout()

    def _relayout(self) -> None:
        vp = self.viewport().size()
        w, h = float(vp.width()), float(vp.height())
        self._scene.setSceneRect(0, 0, w, h)
        if w <= 1 or h <= 1:
            return
        item = self._item
        if self._rotate % 180 == 90:
            item.setSize(QSizeF(h, w))
        else:
            item.setSize(QSizeF(w, h))
        item.setPos(0, 0)
        item.setTransformOriginPoint(item.size().width() / 2, item.size().height() / 2)
        t = QTransform()
        t.rotate(self._rotate)
        if self._mirror:
            t.scale(-1, 1)
        item.setTransform(t)
        rect = item.mapRectToScene(QRectF(QPointF(0, 0), item.size()))
        item.setPos(w / 2 - (rect.width() / 2 + rect.x()),
                    h / 2 - (rect.height() / 2 + rect.y()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()


class DropZone(QWidget):

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(200)
        self._hover = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(0)
        lay.addStretch(1)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setPixmap(drop_icon(22, "#FFFFFF"))
        self.icon.setFixedSize(44, 44)
        self.icon.setStyleSheet(
            "background:#0A0A0A; border:1px solid #262626; border-radius:22px;"
        )
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)
        lay.addSpacing(16)

        self.title = QLabel("把视频拖进来")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("font-size:15px; font-weight:600; color:#FFFFFF;")
        lay.addWidget(self.title)
        lay.addSpacing(4)

        self.sub = QLabel("或点下面的按钮选择文件")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setObjectName("hint")
        lay.addWidget(self.sub)
        lay.addSpacing(18)

        self.btn = QPushButton("选择文件")
        self.btn.setObjectName("primary")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFixedSize(120, 36)
        self.btn.clicked.connect(self.clicked.emit)
        lay.addWidget(self.btn, 0, Qt.AlignHCenter)
        lay.addSpacing(26)

        self.tips = QLabel("拖动两端手柄调整范围   ·   S 键分割   ·   Delete 删除")
        self.tips.setAlignment(Qt.AlignCenter)
        self.tips.setWordWrap(True)
        self.tips.setStyleSheet("color:#5C5C5C; font-size:11px;")
        lay.addWidget(self.tips)
        lay.addStretch(1)

        self.formats = QLabel("MP4 · MOV · MKV · AVI · WEBM · M4V · TS")
        self.formats.setAlignment(Qt.AlignCenter)
        self.formats.setStyleSheet("color:#5C5C5C; font-size:11px;")
        lay.addWidget(self.formats)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 0, 0)
        p.fillPath(path, QColor(255, 255, 255, 5 if self._hover else 0))
        pen = QPen(QColor("#3A3A3A") if self._hover else QColor("#1F1F1F"), 1.0, Qt.DashLine)
        pen.setDashPattern([3, 5])
        p.setPen(pen)
        p.drawPath(path)


class Toast(QFrame):


    def __init__(self, parent=None, reposition=None):
        super().__init__(parent)
        self._reposition = reposition
        self.setObjectName("toast")
        self.setStyleSheet(
            "QFrame#toast { background: #111111;"
            " border: 1px solid #262626; border-radius: 6px; }"
        )
        self.setVisible(False)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setStyleSheet("color:#FFFFFF; font-size:12px;")
        self._btn = QPushButton("打开文件夹")
        self._btn.setObjectName("textBtn")
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setVisible(False)

        from PySide6.QtWidgets import QHBoxLayout
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(8)
        lay.addWidget(self._label, 1)
        lay.addWidget(self._btn)

        self._timer = None

    def show_message(self, text: str, action=None, action_text: str = "打开文件夹",
                     msec: int = 4200) -> None:
        from PySide6.QtCore import QTimer
        self._label.setText(text)
        if action is not None:
            self._btn.setVisible(True)
            self._btn.setText(action_text)
            try:
                if self._btn.receivers(self._btn.clicked) > 0:
                    self._btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._btn.clicked.connect(action)
        else:
            self._btn.setVisible(False)
        self.adjustSize()
        self.setVisible(True)
        self.raise_()
        if self._reposition is not None:
            self._reposition()
            self.raise_()
        if self._timer is not None:
            self._timer.stop()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.setVisible(False))
        self._timer.start(msec)


class ElidedLabel(QLabel):


    def __init__(self, text: str = "", parent=None):
        super().__init__("", parent)
        self._full = text
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full = text
        self._apply()

    def _apply(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.ElideMiddle, max(10, self.width() - 2)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()


class Chip(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        f = QFont(self.font())
        f.setPointSizeF(7.8)
        self.setFont(f)


def elide(text: str, widget: QWidget, width: int) -> str:
    fm = QFontMetrics(widget.font())
    return fm.elidedText(text, Qt.ElideMiddle, width)
