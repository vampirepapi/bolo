"""The dictation state machine, wiring the session, the hook, the capsule, the tray and Settings."""
import os
import re
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QGuiApplication

from . import sound
from .hinglish import DEVANAGARI, hinglish
from .history import History
from .keys import Hotkey, type_diff, user32
from .session import Session, find_claude
from .settings import Settings
from .ui.capsule import Capsule
from .ui.settings_window import SettingsWindow
from .ui.tray import Tray
from .util import LOG, after, log


class App(QObject):
    """Phases: idle -> waiting (key down, mic opening) -> listening -> transcribing -> idle."""

    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.settings, self.history = Settings(), History()
        self.capsule, self.tray, self.window = Capsule(), Tray(self.history), None
        self.phase, self.press_id = "idle", 0
        self.quitting = self.restarting = self.paused = False
        self.claude_version = ""
        self.target, self.typed = None, ""  # the window being dictated into, and what was typed there so far
        self.streamer = QTimer(self, interval=100, timeout=self.stream)
        self._on_key = None

        self.session = Session(self.settings["language"])
        self.session.state_changed.connect(self.session_changed)
        self.hotkey = Hotkey(self.settings["talk_key"]["vk"])
        self.hotkey.pressed.connect(self.pressed)
        self.hotkey.released.connect(self.released)
        self.hotkey.cancelled.connect(self.cancelled)
        self.hotkey.recorded.connect(self._recorded)
        self.settings.changed.connect(self.setting_changed)
        self.tray.copy_requested.connect(self.copy)
        self.tray.history_requested.connect(lambda: self.open_settings("history"))
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.pause_toggled.connect(self.set_paused)
        self.tray.restart_requested.connect(self.restart_session)
        self.tray.quit_requested.connect(self.quit)
        self.session.start()
        self.update_status()

    # Status

    def key_name(self):
        return self.settings["talk_key"]["name"]

    def update_status(self):
        state = self.session.state
        if state == "ready":
            verb = "tap" if self.settings["mode"] == "tap" else "hold"
            text = "Paused" if self.paused else f"Ready · {verb} {self.key_name()} to talk"
        elif state == "starting":
            text = "Starting Claude…"
        elif not Path(find_claude()).exists():
            text = "Claude Code not found"
        else:
            text = "Claude stopped; restarting…"
        if self.phase in ("waiting", "listening", "transcribing") and state == "ready":
            self.tray.set_state("listening" if self.phase == "listening" else "finishing", text)
        else:
            self.tray.set_state(state, text)
        if self.window:
            detail = f"Claude Code {self.claude_version} · hidden session" if self.claude_version else "Hidden Claude Code session"
            self.window.set_session_state("paused" if self.paused and state == "ready" else state,
                                          {"ready": "Claude is ready", "starting": "Claude is starting"}.get(state, text), detail)

    def session_changed(self, state):
        if state == "ready":
            found = re.search(r"Claude Code v([\d.]+)", self.session.display())
            self.claude_version = found.group(1) if found else self.claude_version
            self.restarting = False
        elif state == "stopped":
            self._reset_dictation()
            if not self.quitting:
                after(0.5 if self.restarting else 3, self.session.start)
        self.update_status()

    def message(self, text, ok=True):
        if self.settings["capsule"]:
            self.capsule.show_state("message", text, ok=ok)
        else:
            self.tray.notify(text)

    # Actions from the tray and Settings

    def open_settings(self, section="general"):
        if self.window is None:
            self.window = SettingsWindow(self.settings, self.history, self)
        self.update_status()
        self.window.open(section)

    def copy(self, text):
        QGuiApplication.clipboard().setText(text)
        self.message("Copied to clipboard")

    def set_paused(self, paused):
        if paused and self.phase in ("waiting", "listening"):
            self.cancelled(False)
        self.paused = self.hotkey.paused = self.tray.paused = paused
        self.update_status()

    def restart_session(self):
        self.restarting = True
        if self.session.state == "stopped":
            self.session.start()
        else:
            self.session.stop()  # the exit handler starts it again

    def open_log(self):
        os.startfile(LOG)

    def claude_path(self):
        return find_claude()

    def record_talk_key(self, callback):
        """The next key pressed anywhere goes to `callback(vk)` instead of dictating."""
        self._on_key = callback
        self.hotkey.recording = True
        after(10, lambda: self._on_key is callback and self.cancel_key_recording())

    def cancel_key_recording(self):
        if self._on_key:
            self.hotkey.recording = False
            self._recorded(None)

    def _recorded(self, vk):
        callback, self._on_key = self._on_key, None
        if callback:
            callback(vk)

    def setting_changed(self, key):
        if key == "talk_key":
            self.hotkey.vk = self.settings["talk_key"]["vk"]
        elif key == "language":
            self.session.language = self.settings["language"]
            self.restart_session()
        elif key == "capsule" and not self.settings["capsule"]:
            self.capsule.hide()
        self.update_status()

    def quit(self):
        self.quitting = True
        self.session.stop()
        self.hotkey.stop()
        self.capsule.hide()
        self.tray.hide()
        self.qapp.quit()

    # Dictation

    def _set_phase(self, phase):
        self.phase = phase
        self.hotkey.dictating = phase in ("waiting", "listening")
        self.update_status()

    def _reset_dictation(self):
        self.streamer.stop()
        self.target, self.typed = None, ""
        if self.phase != "idle":
            self.capsule.hide()
            self._set_phase("idle")

    def _show(self, state, **kw):
        if self.settings["capsule"]:
            self.capsule.show_state(state, **kw)

    def _sound(self, name):
        if self.settings["sounds"]:
            sound.play(name)

    def pressed(self):
        if self.settings["mode"] == "tap" and self.phase in ("waiting", "listening"):
            return self.stop_talking()  # the second tap
        if self.phase != "idle":
            return
        if self.session.state != "ready":
            return self.message("Claude is still starting", ok=False)
        log(f"dictation started ({self.settings['mode']}, {self.settings['output']})")
        self.press_id += 1
        self.target, self.typed = user32.GetForegroundWindow(), ""
        self._set_phase("waiting")
        self._show("opening")
        self.session.start_repeats()
        self.wait_for_mic(self.press_id, time.monotonic())

    def released(self):
        if self.settings["mode"] == "hold":
            self.stop_talking()

    def wait_for_mic(self, pid, started):
        """Show 'listening' only once Claude says it is (Claude opens the mic just before)."""
        if pid != self.press_id or self.phase != "waiting":
            return
        if "listening" in self.session.display().lower():
            log(f"listening after {int((time.monotonic() - started) * 1000)} ms")
            self._set_phase("listening")
            self._show("listening")
            self._sound("start")
            self.streamer.start()
            return
        if time.monotonic() - started > 3:
            log(f"Claude did not start listening; screen: {self.session.screen_summary()}")
            self.session.cancel()
            self._reset_dictation()
            self.message("Claude didn't start listening. Check that /voice works in claude.", ok=False)
            return
        after(0.03, lambda: self.wait_for_mic(pid, started))

    def _live(self):
        text = self.session.prompt_text()
        if text is not None and self.settings["hinglish"]:
            text = hinglish(text, self.settings["words"])
        return text

    def stream(self):
        """While talking: show the live text in the capsule and, in live mode, type it into the app."""
        text = self._live()
        self.capsule.update_live(text or "", self.session.levels())
        if self.settings["output"] != "live" or not self.target or text is None:
            return
        if user32.GetForegroundWindow() != self.target:
            log("focus moved; stopped typing into the old window")
            self.target = None
            return
        if text != self.typed:
            type_diff(self.typed, text)
            self.typed = text

    def stop_talking(self):
        if self.phase == "waiting":  # let go before Claude was listening: nothing to transcribe
            log("released before Claude was listening")
            self.session.cancel()
            self._reset_dictation()
        elif self.phase == "listening":
            self.streamer.stop()  # before Ctrl+G empties Claude's prompt, which would erase what was typed
            self.stream()
            badge = self.settings["hinglish"] and bool(DEVANAGARI.search(self.session.prompt_text() or ""))
            self._set_phase("transcribing")
            self._sound("stop")
            self._show("finishing", badge=badge)
            self.session.finish(self.transcribed)

    def cancelled(self, erase):
        """Esc (erase: take back what was typed) or another key (it went to the app; keep the text)."""
        if self.phase not in ("waiting", "listening"):
            return
        log("cancelled")
        self.streamer.stop()
        if erase and self.target and user32.GetForegroundWindow() == self.target:
            type_diff(self.typed, "")
        self.session.cancel()
        self._reset_dictation()
        if erase:
            self._sound("stop")

    def transcribed(self, text):
        """Claude's final text replaces the live one (only the differing tail is retyped)."""
        final = re.sub(r"\s+", " ", text).strip()
        source = final if self.settings["hinglish"] and DEVANAGARI.search(final) else ""
        if final and self.settings["hinglish"]:
            final = hinglish(final, self.settings["words"])
        final = final or self.typed  # no final text: keep what was typed live
        target, typed = self.target, self.typed
        self._reset_dictation()
        if not final:
            return
        self.history.add(final, source)
        if target and user32.GetForegroundWindow() == target:
            type_diff(typed, final + " ")  # trailing space so the next dictation doesn't run into this one
            log(f"typed {len(final)} characters")
        else:
            QGuiApplication.clipboard().setText(final)
            self.message("Window changed: dictation copied to clipboard")
