"""Colours, the stylesheet, the Bolo logo and line icons (the mockup's look)."""
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

ACCENT = "#EA580C"         # logo, live bar
ACCENT_STRONG = "#C2410C"  # buttons, switches: white text on it passes 4.5:1
ACCENT_TINT = "#FFEDD5"
ACCENT_TEXT = "#7C2D12"
TEXT, BODY, MUTED = "#1C1917", "#44403C", "#57534E"
LINE, LINE_STRONG = "#E7E5E4", "#D6D3D1"
WINDOW, SIDEBAR, SURFACE = "#FAFAF9", "#F5F5F4", "#FFFFFF"
GREEN, RED, AMBER, GREY = "#16A34A", "#DC2626", "#D97706", "#78716C"
CAPSULE = "#17171A"

STYLESHEET = f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Nirmala UI", sans-serif; color: {TEXT}; }}
QWidget#window {{ background: {WINDOW}; }}
QWidget#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {LINE}; }}
QPushButton#nav {{ text-align: left; padding: 0 12px; min-height: 40px; border: 0; border-radius: 8px;
    font-size: 14px; color: #292524; background: transparent; }}
QPushButton#nav:hover {{ background: #EEEDEB; }}
QPushButton#nav:checked {{ background: {ACCENT_TINT}; color: {ACCENT_TEXT}; font-weight: 600; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
QLabel#lead {{ font-size: 14px; color: {BODY}; }}
QLabel#section {{ font-size: 12px; font-weight: 600; letter-spacing: 1px; color: {MUTED}; }}
QLabel#rowTitle {{ font-size: 14px; font-weight: 500; }}
QLabel#rowSub, QLabel#muted {{ font-size: 12px; color: {MUTED}; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; }}
QFrame#divider {{ background: #F0EFEE; max-height: 1px; min-height: 1px; border: 0; }}
QFrame#statusBox {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
QLabel#kbd {{ font-size: 13px; font-weight: 600; background: {SIDEBAR}; border: 1px solid {LINE_STRONG};
    border-bottom-width: 2px; border-radius: 6px; padding: 4px 10px; }}
QFrame#seg {{ background: {SIDEBAR}; border: 1px solid {LINE}; border-radius: 8px; }}
QPushButton#segBtn {{ border: 0; border-radius: 6px; padding: 0 14px; min-height: 32px; font-size: 13px;
    color: {BODY}; background: transparent; }}
QPushButton#segBtn:checked {{ background: {SURFACE}; color: {TEXT}; font-weight: 600; border: 1px solid {LINE_STRONG}; }}
QPushButton {{ font-size: 13px; font-weight: 500; background: {SURFACE}; border: 1px solid {LINE_STRONG};
    border-radius: 6px; padding: 0 14px; min-height: 34px; }}
QPushButton:hover {{ background: {SIDEBAR}; }}
QPushButton#primary {{ color: #FFFFFF; background: {ACCENT_STRONG}; border: 0; font-weight: 600; }}
QPushButton#primary:hover {{ background: #9A3412; }}
QPushButton#primary:disabled {{ background: #E7B9A0; }}
QPushButton#link {{ border: 0; background: transparent; color: #9A3412; font-weight: 600; padding: 0; min-height: 24px; }}
QPushButton#icon {{ border: 0; background: transparent; min-width: 40px; max-width: 40px; padding: 0; }}
QPushButton#icon:hover {{ background: {SIDEBAR}; }}
QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {ACCENT_STRONG}; }}
QLineEdit, QComboBox {{ font-size: 14px; background: {SURFACE}; border: 1px solid {LINE_STRONG}; border-radius: 6px;
    padding: 0 10px; min-height: 36px; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QLabel#tryOut {{ font-size: 15px; font-weight: 600; color: {ACCENT_TEXT}; background: #FFF7ED;
    border: 1px solid #FED7AA; border-radius: 8px; padding: 0 12px; min-height: 40px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE_STRONG}; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: #A8A29E; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 9px 28px 9px 12px; border-radius: 6px; font-size: 14px; }}
QMenu::item:selected {{ background: {SIDEBAR}; }}
QMenu::item:disabled {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
QMenu::icon {{ padding-left: 10px; }}
QToolTip {{ background: {CAPSULE}; color: #FAFAF9; border: 0; padding: 6px 8px; }}
"""

BAR_HEIGHTS = (6, 13, 18, 11, 4)  # the logo's voice bars, out of 34


def paint_logo(p: QPainter, rect: QRectF, color: str, bars=BAR_HEIGHTS):
    """The Bolo mark: voice bars in a rounded square."""
    s = rect.width() / 34
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(rect, 9 * s, 9 * s)
    p.setBrush(QColor("#FFFFFF"))
    for i, h in enumerate(bars):
        x = rect.left() + (8 + 4.5 * i) * s
        p.drawRoundedRect(QRectF(x, rect.top() + (34 - h) / 2 * s, 2.6 * s, h * s), 1.3 * s, 1.3 * s)
    p.restore()


def logo_icon(color=ACCENT, size=64):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    paint_logo(p, QRectF(0, 0, size, size), color)
    p.end()
    return QIcon(pix)


# Line icons (24x24 strokes), drawn in the caller's colour.
ICONS = {
    "general": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "hinglish": '<path d="M4 5h8M8 3v2M5.5 5c.5 3 3 6 6 7M10.5 5c-.5 3-3 6-6 7"/><path d="M13 21l4-9 4 9M14.5 18h5"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "session": '<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 9l3 2.5L7 14M12 14h4"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "pause": '<path d="M9 5v14M15 5v14"/>',
    "play": '<path d="M7 5l12 7-12 7z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "restart": '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>',
    "quit": '<path d="M12 3v9"/><path d="M6.3 7a8 8 0 1 0 11.4 0"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/>',
}


def icon(name, color=BODY, size=20):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    pix = QPixmap()
    pix.loadFromData(QByteArray(svg.encode()), "SVG")
    return QIcon(pix)
