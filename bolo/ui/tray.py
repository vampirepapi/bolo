"""The tray icon and its menu: status, the latest dictations, pause, settings, restart, quit."""
from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QCursor, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget, QWidgetAction

from ..history import when
from .theme import ACCENT, AMBER, GREEN, GREY, MUTED, RED, icon, logo_icon, paint_logo

STATE_COLORS = {"ready": (ACCENT, GREEN), "listening": (RED, RED), "finishing": (AMBER, AMBER),
                "starting": (GREY, AMBER), "stopped": (GREY, RED), "paused": (GREY, GREY)}


class Tray(QObject):
    copy_requested = pyqtSignal(str)
    history_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    pause_toggled = pyqtSignal(bool)
    restart_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, history):
        super().__init__()
        self.history = history
        self.state, self.status, self.paused = "starting", "Starting Claude…", False
        self.icons = {s: logo_icon(c[0]) for s, c in STATE_COLORS.items()}
        self.menu = QMenu()
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                                 | Qt.WindowType.NoDropShadowWindowHint)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # rounded corners
        self.menu.setMinimumWidth(320)
        self.menu.aboutToShow.connect(self._build)
        self.tray = QSystemTrayIcon(self.icons["starting"])
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.set_state("starting", self.status)
        self.tray.show()

    def set_state(self, state, status):
        self.state, self.status = state, status
        self.tray.setIcon(self.icons["paused" if self.paused and state == "ready" else state])
        self.tray.setToolTip(f"Bolo: {status}")

    def notify(self, text):
        self.tray.showMessage("Bolo", text, QSystemTrayIcon.MessageIcon.Information, 2500)

    def hide(self):
        self.tray.hide()

    def _activated(self, reason):
        # Windows opens the menu only on right-click; a left-click is what most people try first.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.popup(QCursor.pos())
            self.menu.activateWindow()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.settings_requested.emit()

    def _header(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(12)
        pix = QPixmap(68, 68)
        pix.setDevicePixelRatio(2)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        paint_logo(p, QRectF(0, 0, 34, 34), STATE_COLORS[self.state][0] if not self.paused else GREY)
        p.end()
        logo = QLabel()
        logo.setPixmap(pix)
        lay.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel("Bolo")
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        dot = STATE_COLORS["paused" if self.paused else self.state][1]
        status = QLabel(f'<span style="color:{dot}">●</span>&nbsp; {"Paused" if self.paused else self.status}')
        status.setStyleSheet(f"font-size: 12px; color: {MUTED};")
        text.addWidget(name)
        text.addWidget(status)
        lay.addLayout(text, 1)
        action = QWidgetAction(self.menu)
        action.setDefaultWidget(w)  # left enabled: Qt greys out the logo in a disabled item
        return action

    def _build(self):
        m = self.menu
        m.clear()
        m.addAction(self._header())
        m.addSeparator()
        label = m.addAction("RECENT · CLICK TO COPY")
        label.setEnabled(False)
        if not self.history.entries:
            m.addAction("No dictations yet").setEnabled(False)
        for entry in self.history.entries[:3]:
            snippet = " ".join(entry["text"].split())
            snippet = snippet if len(snippet) <= 42 else snippet[:41] + "…"
            a = QAction(f"{snippet}\t{when(entry['time'])}", m)
            a.setToolTip(entry["text"])
            a.triggered.connect(lambda _, t=entry["text"]: self.copy_requested.emit(t))
            m.addAction(a)
        m.addAction("Show all history…", self.history_requested.emit)
        m.addSeparator()
        pause = m.addAction(icon("play" if self.paused else "pause"), "Resume dictation" if self.paused else "Pause dictation")
        pause.triggered.connect(lambda: self.pause_toggled.emit(not self.paused))
        m.addAction(icon("settings"), "Settings…", self.settings_requested.emit)
        m.addAction(icon("restart"), "Restart Claude session", self.restart_requested.emit)
        m.addSeparator()
        m.addAction(icon("quit"), "Quit Bolo", self.quit_requested.emit)
