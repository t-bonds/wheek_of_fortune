import math
import random
from PySide6 import QtCore, QtGui, QtWidgets

from utils import fmt_money
from data import DEFAULT_WEDGES


class WheelWidget(QtWidgets.QWidget):
    spin_finished: QtCore.Signal = QtCore.Signal(object)

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.parent = parent
        self.sounds = self.parent.sounds
        self.wedges: list[float | str] = DEFAULT_WEDGES[:]
        self._angle_per: float = 360.0 / max(1, len(self.wedges))
        self.rotation: float = 0.0
        self._anim_timer: QtCore.QTimer = QtCore.QTimer()
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_animate)
        self.velocity: float = 0.0
        self.friction: float = 0.988
        self.setMinimumSize(420, 420)

    def paintEvent(self, event) -> None:
        painter: QtGui.QPainter = QtGui.QPainter(self)
        painter.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )

        # Use a monospace font for the wedges
        font: QtGui.QFont = QtGui.QFont("monospace")
        font.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)
        font.setPointSize(15)
        painter.setFont(font)

        rect: QtCore.QRect = self.rect()
        size: int = min(rect.width(), rect.height()) - 20
        radius: float = size / 2
        center: QtCore.QPoint = rect.center()

        # --- Draw the wheel (rotate painter so wedges move together) ---
        painter.save()
        painter.translate(center)
        painter.rotate(self.rotation)

        wheel_rect: QtCore.QRectF = QtCore.QRectF(-radius, -radius, size, size)

        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 2))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(240, 240, 240)))
        painter.drawEllipse(wheel_rect)

        n: int = len(self.wedges)
        if n == 0:
            painter.restore()
            painter.end()
            return

        # font metrics (we'll use these to size the stacked characters)
        fm: QtGui.QFontMetrics = painter.fontMetrics()
        char_height: int = fm.height()
        char_spacing: int = max(1, int(char_height * 0.05))
        step: int = char_height + char_spacing

        for i, wedge in enumerate(self.wedges):
            start_angle: float = (
                i * self._angle_per
            )  # local angle for the wedge (degrees)

            # choose color and text color
            if wedge == "BANKRUPT":
                color: QtGui.QColor = QtGui.QColor(0, 0, 0)
            elif wedge == "LOSE A TURN":
                color: QtGui.QColor = QtGui.QColor(255, 255, 255)
            else:
                color: QtGui.QColor = QtGui.QColor.fromHsv(
                    int((i * 360 / n) % 360), 200, 220
                )
            painter.setBrush(QtGui.QBrush(color))
            path: QtGui.QPainterPath = QtGui.QPainterPath()
            path.moveTo(0, 0)
            path.arcTo(wheel_rect, -start_angle, -self._angle_per)
            path.closeSubpath()
            painter.drawPath(path)

        painter.restore()  # done drawing the colored wedges

        # --- Draw stacked labels: compute screen positions and draw each stack in device coords ---
        # Doing it after restoring means we can compute absolute screen positions
        for i, wedge in enumerate(self.wedges):
            start_angle: float = i * self._angle_per

            mid_angle_total: float = (
                -self.rotation - (start_angle + self._angle_per / 2.0)
            ) % 360.0
            mid_rad: float = math.radians(mid_angle_total)

            # outward unit vector (screen coords)
            ux: float = math.cos(mid_rad)
            uy: float = -math.sin(mid_rad)

            # outermost character location (screen coords)
            label_radius: float = radius * 0.82
            px: float = center.x() + ux * label_radius
            py: float = center.y() + uy * label_radius

            # prepare the label text
            if wedge == "BANKRUPT":
                label_text = "BANKRUPT"
                text_color: QtGui.QColor = QtGui.QColor(255, 255, 255)
            elif wedge == "LOSE A TURN":
                label_text = "LOSE A TURN"
                text_color: QtGui.QColor = QtGui.QColor(0, 0, 0)
            else:
                try:
                    label_text: str = fmt_money(float(wedge))
                    text_color: QtGui.QColor = QtGui.QColor(0, 0, 0)
                except Exception:
                    label_text: str = str(wedge)
                    text_color: QtGui.QColor = QtGui.QColor(0, 0, 0)

            chars: list[str] = list(label_text)

            # compute rotation so local +Y points toward center:
            rot: float = -mid_angle_total + 90.0

            # draw characters in device coordinates: translate to px,py, rotate by rot,
            # and draw characters stacked along local +Y (outer -> inner)
            painter.save()
            painter.resetTransform()  # draw in widget/device coords now
            painter.translate(px, py)
            painter.rotate(rot)

            painter.setPen(QtGui.QPen(text_color))
            # draw each character centered at (0, j*step) where j=0 is outermost
            for j, ch in enumerate(chars):
                y: int = j * step
                w: int = max(fm.horizontalAdvance(ch), char_height) + 6
                h: int = char_height + 4
                rect_char: QtCore.QRectF = QtCore.QRectF(-w / 2.0, y - h / 2.0, w, h)
                painter.drawText(rect_char, QtCore.Qt.AlignmentFlag.AlignCenter, ch)

            painter.restore()
            pointer: QtGui.QPolygonF = QtGui.QPolygonF(
                [
                    QtCore.QPointF(center.x(), center.y() - radius + 12),
                    QtCore.QPointF(center.x() - 24, center.y() - radius - 36),
                    QtCore.QPointF(center.x() + 24, center.y() - radius - 36),
                ]
            )
            painter.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.red))
            painter.drawPolygon(pointer)

    def spin(self) -> None:
        # random initial angular velocity (degrees per frame step baseline)
        # choose a random velocity within a wider range for noticeable variance
        self.velocity = random.uniform(30.0, 140.0)
        # random friction factor (closer to 1.0 -> longer spin)
        self.friction = random.uniform(0.980, 0.994)
        # small random jitter in timer interval (keeps visual variance subtle)
        jitter: float = random.uniform(-2, 2)
        base_interval = 16
        self._anim_timer.setInterval(max(8, int(base_interval + jitter)))
        self._anim_timer.start()

    def _on_animate(self) -> None:
        self.rotation = (self.rotation + self.velocity) % 360.0

        self.velocity *= self.friction
        # stop threshold chosen small so some spins last longer
        if abs(self.velocity) < 0.04:
            self._anim_timer.stop()
            selected: dict[str, float | str | None] = self._wedge_at_angle()
            self.spin_finished.emit(selected)
        self.update()

    def _wedge_at_angle(self) -> dict[str, float | str | None]:
        n: int = len(self.wedges)
        if n == 0:
            return {"index": None, "value": None}

        # reproduce the same geometry calculations used in paintEvent
        rect: QtCore.QRect = self.rect()
        size: int = min(rect.width(), rect.height()) - 20
        radius: float = size / 2.0
        center: QtCore.QPoint = rect.center()

        # pointer first point (same as in paintEvent)
        ptr_x: float = center.x()
        ptr_y: float = center.y() - radius + 12
        # vector from center to pointer point (screen coordinates)
        vx: float = ptr_x - center.x()  # always 0 here, kept general
        vy: float = ptr_y - center.y()

        # convert vector to the same angle convention used in paintEvent:
        # mid_rad = atan2(-vy, vx) -> mid_angle_total degrees
        mid_rad: float = math.atan2(-vy, vx)
        mid_angle_total: float = (math.degrees(mid_rad)) % 360.0

        # Using the same relation as in paintEvent:
        # mid_angle_total = (-rotation - (start_angle + angle_per/2)) % 360
        # so s = ( -rotation - mid_angle_total ) % 360  == start_angle + angle_per/2
        s: float = (-self.rotation - mid_angle_total) % 360.0

        # start_angle = (s - angle_per/2) % 360
        start_angle: float = s % 360.0

        # index = floor(start_angle / angle_per)
        idx: int = int(math.floor(start_angle / self._angle_per)) % n

        return {"index": idx, "value": self.wedges[idx]}
