"""The floating capsule near the bottom of the screen. It never takes focus or clicks: if it became the
foreground window, the dictation would think you switched apps and fall back to the clipboard."""
import ctypes
import math

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .theme import ACCENT, CAPSULE

H, PAD = 48, 18          # pill height, room around it for the shadow
TEXT_MAX = 340           # widest live text before it is elided at the start
MESSAGE_MS = 2500
WHITE, DIM = QColor("#FAFAF9"), QColor("#A8A29E")

_user32 = ctypes.WinDLL("user32")
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x20, 0x80
_dwm = ctypes.WinDLL("dwmapi")
# Windows 11 draws a rounded, bordered frame around every window, which shows as a faint box around the pill.
NO_FRAME = ((33, 1), (34, 0xFFFFFFFE))  # DWMWA_WINDOW_CORNER_PREFERENCE = do not round, DWMWA_BORDER_COLOR = none


class Capsule(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.state, self.text, self.badge, self.ok, self.levels = None, "", False, True, []
        self.font15 = QFont("Segoe UI", weight=QFont.Weight.Medium)
        self.font15.setPixelSize(15)
        self.font12 = QFont("Segoe UI", weight=QFont.Weight.DemiBold)
        self.font12.setPixelSize(12)
        self.fm, self.fm12 = QFontMetrics(self.font15), QFontMetrics(self.font12)
        self.tick = 0
        self.anim = QTimer(self, interval=60, timeout=self._advance)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.hide)

    # Public API

    def show_state(self, state, text="", badge=False, ok=True):
        """state: opening | listening | finishing | message."""
        self.state, self.text, self.badge, self.ok, self.levels = state, text, badge, ok, []
        self._place()
        if not self.isVisible():
            self.show()
        self.anim.start()
        if state == "message":
            self.hide_timer.start(MESSAGE_MS)
        else:
            self.hide_timer.stop()
        self.update()

    def update_live(self, text, levels):
        if self.state != "listening":
            return
        width_before = self._content_width()
        self.text, self.levels = text, levels
        if self._content_width() != width_before:
            self._place()
        self.update()

    def hide(self):
        self.anim.stop()
        self.state = None
        super().hide()

    # Layout and painting

    def showEvent(self, e):
        super().showEvent(e)
        hwnd = int(self.winId())
        style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        for attr, value in NO_FRAME:  # fails harmlessly on Windows 10, which has no such frame
            _dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(ctypes.c_uint(value)), 4)

    def _advance(self):
        self.tick += 1
        self.update()

    def _live_text(self):
        return self.fm.elidedText(self.text, Qt.TextElideMode.ElideLeft, TEXT_MAX) if self.text else "Listening…"

    def _label(self):
        return {"opening": "Opening the mic…", "finishing": "Finishing…"}.get(self.state, self.text)

    def _content_width(self):
        fm = self.fm
        if self.state == "listening":
            return 16 + 10 + 14 + 34 + 14 + fm.horizontalAdvance(self._live_text()) + 14 + self.fm12.horizontalAdvance("Esc") + 14 + 14
        if self.state == "finishing":
            badge = 12 + self.fm12.horizontalAdvance("हि → hi") + 18 if self.badge else 0
            return 16 + 30 + 12 + fm.horizontalAdvance(self._label()) + badge + 18
        return 16 + 18 + 12 + min(fm.horizontalAdvance(self._label()), 460) + 20

    def _place(self):
        w = self._content_width()
        self.resize(w + 2 * PAD, H + 2 * PAD)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2, geo.bottom() - 40 - self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pill = QRectF(PAD, PAD, self.width() - 2 * PAD, H)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(8, 0, -1):  # soft shadow
            p.setBrush(QColor(0, 0, 0, 7))
            p.drawRoundedRect(pill.adjusted(-i, -i + 4, i, i + 4), H / 2 + i, H / 2 + i)
        p.setBrush(QColor(CAPSULE))
        p.drawRoundedRect(pill, H / 2, H / 2)
        x, cy = pill.left() + 16, pill.center().y()
        getattr(self, f"_paint_{self.state or 'message'}")(p, x, cy)

    def _text(self, p, x, cy, text, color, font=None):
        p.setFont(font or self.font15)
        p.setPen(color)
        fm = QFontMetrics(font or self.font15)
        p.drawText(QPointF(x, cy + (fm.ascent() - fm.descent()) / 2), text)
        return x + fm.horizontalAdvance(text)

    def _paint_opening(self, p, x, cy):
        p.setPen(QPen(DIM, 2, cap=Qt.PenCapStyle.RoundCap))
        c = QPointF(x + 9, cy)
        for i in range(8):
            a = (i + self.tick // 2) * math.pi / 4
            p.setOpacity(0.25 + 0.75 * (i / 7))
            p.drawLine(c + QPointF(math.cos(a) * 4, math.sin(a) * 4), c + QPointF(math.cos(a) * 8, math.sin(a) * 8))
        p.setOpacity(1)
        self._text(p, x + 30, cy, self._label(), DIM)

    def _paint_listening(self, p, x, cy):
        p.setBrush(QColor("#F87171"))
        p.drawEllipse(QPointF(x + 5, cy), 5, 5)
        x += 24
        levels = self.levels[-5:]
        for i in range(5):
            if len(levels) == 5:
                h = 4 + (levels[i] - 1) / 7 * 16  # Claude's own microphone level, 1-8
            else:
                h = 5 + abs(math.sin(self.tick * 0.35 + i * 1.3)) * 9  # gentle idle motion until levels arrive
            p.setBrush(QColor(ACCENT) if i == 2 else WHITE)
            p.drawRoundedRect(QRectF(x + i * 7.5, cy - h / 2, 3.5, h), 1.75, 1.75)
        x += 34 + 14
        x = self._text(p, x, cy, self._live_text(), WHITE if self.text else DIM) + 14
        esc_w = self.fm12.horizontalAdvance("Esc") + 14
        p.setPen(QPen(QColor("#57534E"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x, cy - 11, esc_w, 22), 6, 6)
        self._text(p, x + 7, cy, "Esc", QColor("#D6D3D1"), self.font12)

    def _paint_finishing(self, p, x, cy):
        for i in range(3):
            p.setBrush(QColor("#FBBF24"))
            p.setOpacity(0.35 + 0.65 * ((self.tick // 3 - i) % 3 == 0))
            p.drawEllipse(QPointF(x + 4 + i * 11, cy), 3.5, 3.5)
        p.setOpacity(1)
        x = self._text(p, x + 42, cy, self._label(), WHITE)
        if self.badge:
            text = "हि → hi"
            w = self.fm12.horizontalAdvance(text) + 18
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FDBA74"))
            p.drawRoundedRect(QRectF(x + 12, cy - 11, w, 22), 11, 11)
            self._text(p, x + 21, cy, text, QColor(CAPSULE), self.font12)

    def _paint_message(self, p, x, cy):
        pen = QPen(QColor("#86EFAC" if self.ok else "#FBBF24"), 2.4, cap=Qt.PenCapStyle.RoundCap,
                   join=Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if self.ok:
            p.drawPolyline([QPointF(x + 2, cy), QPointF(x + 7, cy + 5), QPointF(x + 16, cy - 5)])
        else:
            p.drawLine(QPointF(x + 9, cy - 7), QPointF(x + 9, cy + 2))
            p.drawPoint(QPointF(x + 9, cy + 7))
        text = self.fm.elidedText(self._label(), Qt.TextElideMode.ElideRight, 460)
        self._text(p, x + 30, cy, text, WHITE)
