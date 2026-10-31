from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .clipmodel import Clip


class Timeline(QWidget):
    seekRequested = Signal(int)
    clipSelected = Signal(int)
    moveRequested = Signal(int, int)
    trimRequested = Signal(int, str, int)
    splitRequested = Signal(int)
    editStarted = Signal()

    PAD = 10
    HANDLE_W = 9
    SNAP_PX = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.source_ms = 0
        self.clips: list[Clip] = []
        self.sel = 0
        self.pos_ms = 0
        self._sprite: QPixmap | None = None
        self._mode: str | None = None
        self._press_x = 0.0
        self._press_t = 0
        self._orig_pos = 0
        self._snap_ms: int | None = None


    def set_sprite(self, sprite_path: str) -> None:
        pm = QPixmap(sprite_path)
        self._sprite = None if pm.isNull() else pm
        self.update()

    def clear_sprite(self) -> None:
        self._sprite = None
        self.update()

    def set_source(self, source_ms: int) -> None:
        self.source_ms = max(0, int(source_ms))
        self.update()

    def set_clips(self, clips, selected: int | None = None) -> None:
        self.clips = [c if isinstance(c, Clip) else Clip.from_tuple(c) for c in clips]
        if selected is not None:
            self.sel = int(selected)
        self.sel = max(0, min(self.sel, len(self.clips) - 1))
        self.update()

    def set_position(self, ms: int) -> None:
        self.pos_ms = max(0, int(ms))
        self.update()

    def select(self, index: int) -> None:
        self.sel = max(0, min(int(index), len(self.clips) - 1))
        self.update()


    @property
    def project_ms(self) -> int:
        if not self.clips:
            return 0
        return max(max(c.out_pos for c in self.clips), 1)

    def _body(self) -> QRectF:
        return QRectF(self.PAD, 7, max(1, self.width() - self.PAD * 2), self.height() - 14)

    def _ms_to_x(self, ms: float) -> float:
        b = self._body()
        total = max(self.project_ms, 1)
        return b.left() + b.width() * (max(0.0, min(float(ms), total)) / total)

    def _x_to_ms(self, x: float) -> int:
        b = self._body()
        if b.width() <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - b.left()) / b.width()))
        return int(ratio * max(self.project_ms, 1))

    def clip_at(self, t: int) -> int:
        for i, c in enumerate(self.clips):
            if c.pos <= t < c.out_pos:
                return i
        return -1

    def _tol_ms(self) -> int:
        b = self._body()
        if b.width() <= 0:
            return 0
        return int(max(self.project_ms, 1) * self.SNAP_PX / b.width())


    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        b = self._body()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(b, 8, 8)

        p.save()
        p.setClipPath(clip_path)
        p.fillPath(clip_path, QColor("#000000"))

        if self.clips:
            cursor = 0
            for c in self.clips:
                if c.pos > cursor:
                    self._paint_gap(p, b, cursor, c.pos)
                self._paint_clip(p, b, c)
                cursor = c.out_pos
            end = self.project_ms
            if cursor < end:
                self._paint_gap(p, b, cursor, end)

            for i, c in enumerate(self.clips):
                rect = self._rect(c)
                p.setBrush(Qt.NoBrush)
                if i == self.sel:
                    p.setPen(QPen(QColor("#C6F24E"), 2.0))
                    p.drawRect(rect.adjusted(1, 1, -1, -1))
                else:
                    p.setPen(QPen(QColor("#262626"), 1.0))
                    p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))

            if self._snap_ms is not None:
                sx = self._ms_to_x(self._snap_ms)
                p.setPen(QPen(QColor("#C6F24E"), 1.2, Qt.DashLine))
                p.drawLine(QPointF(sx, b.top() - 2), QPointF(sx, b.bottom() + 2))

            px = self._ms_to_x(self.pos_ms)
            p.setPen(QPen(QColor("#FFFFFF"), 1.0))
            p.drawLine(QPointF(px, b.top() + 2), QPointF(px, b.bottom() - 2))
        else:
            self._paint_gap(p, b, 0, max(self.project_ms, 1))
        p.restore()

        if self.clips and 0 <= self.sel < len(self.clips):
            c = self.clips[self.sel]
            for x in (self._ms_to_x(c.pos), self._ms_to_x(c.out_pos)):
                hx = min(max(x - self.HANDLE_W / 2, b.left() - 1), b.right() - self.HANDLE_W + 1)
                hr = QRectF(hx, b.top() - 1, self.HANDLE_W, b.height() + 2)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#FFFFFF"))
                p.drawRect(hr)
                p.setPen(QPen(QColor("#000000"), 1.0))
                cxp = hr.center().x()
                p.drawLine(QPointF(cxp, hr.top() + 6), QPointF(cxp, hr.bottom() - 6))

    def _rect(self, c: Clip) -> QRectF:
        b = self._body()
        x0 = self._ms_to_x(c.pos)
        x1 = self._ms_to_x(c.out_pos)
        return QRectF(x0, b.top(), max(1.0, x1 - x0), b.height())

    def _paint_clip(self, p: QPainter, b: QRectF, c: Clip) -> None:
        rect = self._rect(c)
        if self._sprite is not None and self.source_ms > 0:
            sw = self._sprite.width()
            sh = self._sprite.height()
            sx = sw * (c.start / self.source_ms)
            ex = sw * (c.end / self.source_ms)
            src = QRectF(sx, 0, max(1.0, ex - sx), sh)
            p.drawPixmap(rect, self._sprite, src)
        else:
            p.fillRect(rect, QColor("#1C1C28"))

    def _paint_badge(self, p: QPainter, rect: QRectF, index: int,
                     selected: bool) -> None:
        if rect.width() < 24:
            return
        f = QFont(self.font())
        f.setPointSizeF(7.4)
        f.setBold(True)
        p.setFont(f)
        text = str(index + 1)
        w = 14.0 if index < 9 else 18.0

        x = rect.left() + (14 if selected else 4)
        if x + w > rect.right() - 2:
            return
        badge = QRectF(x, rect.top() + 4, w, 13)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C6F24E") if selected
                   else QColor("#1A1A1A"))
        p.drawRoundedRect(badge, 4, 4)
        p.setPen(QColor("#000000") if selected else QColor("#B4B4B4"))
        p.drawText(badge, Qt.AlignCenter, text)

    def _paint_gap(self, p: QPainter, b: QRectF, a: int, e: int) -> None:

        x0, x1 = self._ms_to_x(a), self._ms_to_x(e)
        if x1 - x0 < 0.5:
            return
        rect = QRectF(x0, b.top(), x1 - x0, b.height())
        p.fillRect(rect, QColor("#0A0A0A"))
        p.save()
        p.setClipRect(rect)
        p.setPen(QPen(QColor("#1E1E1E"), 1))
        step = 10
        y = rect.top() + 6
        while y < rect.bottom():
            x = rect.left() + 4
            while x < rect.right():
                p.drawPoint(QPointF(x, y))
                x += step
            y += step
        p.restore()
        if rect.width() > 34:
            f = QFont(self.font())
            f.setPointSizeF(7.6)
            p.setFont(f)
            p.setPen(QColor("#5C5C5C"))
            p.drawText(rect, Qt.AlignCenter, "空位")


    def _handle_zone(self, x: float) -> str | None:
        if not self.clips or not (0 <= self.sel < len(self.clips)):
            return None
        c = self.clips[self.sel]
        if abs(x - self._ms_to_x(c.pos)) <= 10:
            return "start"
        if abs(x - self._ms_to_x(c.out_pos)) <= 10:
            return "end"
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self.clips:
            return
        x = event.position().x()
        zone = self._handle_zone(x)
        if zone:
            self._mode = zone
            self.editStarted.emit()
            return

        t = self._x_to_ms(x)
        idx = self.clip_at(t)
        if idx < 0:
            nxt = next((i for i, c in enumerate(self.clips) if c.pos >= t), None)
            if nxt is not None:
                self.clipSelected.emit(nxt)
                self.seekRequested.emit(self.clips[nxt].pos)
            return
        self.clipSelected.emit(idx)
        self._mode = "pending"
        self._press_x = x
        self._press_t = t
        self._orig_pos = self.clips[idx].pos

    def mouseMoveEvent(self, event):
        x = event.position().x()
        if self._mode in ("start", "end"):
            self._snap_ms = None
            t = self._snap_value(self._x_to_ms(x), self.sel)
            if t is not None:
                self.trimRequested.emit(self.sel, self._mode, t)
            return
        if self._mode == "pending":
            if abs(x - self._press_x) > 3:
                self._mode = "move"
                self.editStarted.emit()
                self.setCursor(Qt.ClosedHandCursor)
            else:
                return
        if self._mode == "move":
            desired = self._orig_pos + (self._x_to_ms(x) - self._press_t)
            snapped = self._snap_value(desired, self.sel, moving=True)
            self.moveRequested.emit(self.sel, snapped)
            return
        zone = self._handle_zone(x)
        if zone:
            self.setCursor(Qt.SizeHorCursor)
        elif self.clip_at(self._x_to_ms(x)) >= 0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self._mode == "pending":
            self.seekRequested.emit(self._press_t)
        self._mode = None
        self._snap_ms = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.clips:
            self.splitRequested.emit(self._x_to_ms(event.position().x()))

    def _snap_value(self, value: int, exclude: int, moving: bool = False) -> int:

        tol = self._tol_ms()
        cands = [0, self.pos_ms]
        for i, c in enumerate(self.clips):
            if i == exclude:
                continue
            cands.extend((c.pos, c.out_pos))
        best, best_d = value, tol + 1
        for c in cands:
            d = abs(c - value)
            if d < best_d:
                best, best_d = c, d
        if best_d <= tol:
            self._snap_ms = best
            return best
        self._snap_ms = None
        return value
