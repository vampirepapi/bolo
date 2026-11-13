"""Small building blocks of the Settings window: switch, segmented buttons, cards and rows."""
from PyQt6.QtCore import QPropertyAnimation, QRectF, QSize, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from .theme import ACCENT_STRONG


class Toggle(QAbstractButton):
    """An on/off switch (checkable button), with keyboard focus and an accessible name."""

    def __init__(self, name, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self, duration=120)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(42, 24)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    @pyqtProperty(float)
    def knob(self):
        return self._pos

    @knob.setter
    def knob(self, value):
        self._pos = value
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        off, on = QColor("#A8A29E"), QColor(ACCENT_STRONG)
        mix = lambda a, b: int(a + (b - a) * self._pos)
        p.setBrush(QColor(mix(off.red(), on.red()), mix(off.green(), on.green()), mix(off.blue(), on.blue())))
        p.drawRoundedRect(QRectF(0, 0, 42, 24), 12, 12)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(3 + 18 * self._pos, 3, 18, 18))
        if self.hasFocus():
            p.setPen(QColor(ACCENT_STRONG))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, 41, 23), 12, 12)


class Segmented(QFrame):
    """Mutually exclusive choices shown side by side."""

    changed = pyqtSignal(str)

    def __init__(self, options, value):
        super().__init__(objectName="seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, label in options:
            b = QPushButton(label, objectName="segBtn", checkable=True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bold = QFont(b.font())
            bold.setPixelSize(13)
            bold.setWeight(QFont.Weight.DemiBold)
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(label) + 34)  # room for the bold checked state
            b.setChecked(key == value)
            b.clicked.connect(lambda _, k=key: self.changed.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)

    def set_value(self, value):
        self.buttons[value].setChecked(True)


def label(text, name, wrap=False):
    lab = QLabel(text, objectName=name)
    lab.setWordWrap(wrap)
    return lab


class Row(QWidget):
    """A settings row: title and optional subtitle on the left, a control on the right. Clicking
    anywhere on a row with a switch flips the switch."""

    def __init__(self, title, subtitle="", control=None, height=60):
        super().__init__()
        self.setMinimumHeight(height)
        self.control = control
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "rowTitle"))
        if subtitle:
            self.sub = label(subtitle, "rowSub", wrap=True)
            text.addWidget(self.sub)
        lay.addLayout(text, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        if isinstance(control, Toggle):
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if isinstance(self.control, Toggle) and e.button() == Qt.MouseButton.LeftButton:
            self.control.toggle()


def card(*rows):
    """White rounded card holding rows separated by thin lines."""
    frame = QFrame(objectName="card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    for i, row in enumerate(rows):
        if i:
            lay.addWidget(QFrame(objectName="divider"))
        lay.addWidget(row)
    return frame


def hbox(*widgets, spacing=8, margins=(0, 0, 0, 0)):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for item in widgets:
        if item is None:
            lay.addStretch(1)
        else:
            lay.addWidget(item)
    return w
