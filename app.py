"""Bolo: system-wide live voice typing for Windows, in English or Hinglish, on Claude Code's /voice.

Hold Right Ctrl, speak, let go: the text is pasted where your cursor is. Esc or any other key while
holding cancels. Transcription is Claude Code's own /voice dictation, driven in a hidden ConPTY
session; Ctrl+G hands Claude's prompt to $EDITOR (a tiny .cmd) which writes it to an outbox file.

    pip install pywinpty pyte PyQt6
    pythonw app.py            # tray app, no console window
    python app.py --selftest  # no mic: start the session, type a token, capture it back
"""
import ctypes
import json
import os
import re
import shutil
import sys
import threading
import time
import types
import unicodedata
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
import pyte
import pyte.screens
from winpty import PtyProcess

# pyte keeps a zero-width character only if Unicode calls it "combining"; otherwise it drops it and
# the rest of that chunk ("क्या मैं" read as "क्य"). Devanagari vowel signs (ा ै …) aren't "combining",
# so they're declared so here and get attached to the letter before them, the way ConPTY lays them out.
# shortcut: Devanagari only; other Indic scripts would need their ranges added here.
pyte.screens.unicodedata = types.SimpleNamespace(
    normalize=unicodedata.normalize,
    combining=lambda c: 1 if "ऀ" <= c <= "ॿ" else unicodedata.combining(c))

LOCAL = Path(os.environ["LOCALAPPDATA"]) / "Bolo"
WORKSPACE, BIN, OUTBOX, LOG = LOCAL / "workspace", LOCAL / "bin", LOCAL / "outbox.txt", LOCAL / "log.txt"
# shortcut: assumes Claude's default push-to-talk key (Space); read ~/.claude/keybindings.json if you rebind voice:pushToTalk
VOICE_KEY = " "
CAPTURE_CMD = (
    "@echo off\r\n"
    'copy /y "%~1" "%BOLO_OUTBOX%.tmp" >nul\r\n'
    'move /y "%BOLO_OUTBOX%.tmp" "%BOLO_OUTBOX%" >nul\r\n'
    'type nul > "%~1"\r\n'
)
# Devanagari -> Hinglish (Hindi in casual Roman spelling), by rule, so it is instant and works on live text.
NUKTA_LETTERS = "".join(map(chr, range(0x958, 0x960)))  # क़ ख़ ग़ ज़ ड़ ढ़ फ़ य़ as single codepoints
CONSONANTS = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह" + NUKTA_LETTERS,
                      "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h q kh g z d dh f y".split()))
VOWELS = dict(zip("अआइईउऊऋएऐओऔऑऍ", "a aa i i u u ri e ai o au o e".split()))
MATRAS = dict(zip("ािीुूृेैोौॉॅॆॊ", "a i i u u ri e ai o au o e e o".split()))
SIGNS = {"ं": "n", "ँ": "n", "ः": "h"}
NUKTA = {c + "़": n for c, n in zip("कखगजडढफय", NUKTA_LETTERS)}  # base + dot -> the single codepoint
# Common words whose casual spelling the rules don't produce.
# shortcut: a small fixed list; English loanwords in Devanagari (प्रोजेक्ट) come out phonetic. Grow the list as you hit them.
HINGLISH_WORDS = {"में": "mein", "मैंने": "maine", "हूँ": "hoon", "हूं": "hoon", "नहीं": "nahi", "यह": "yeh", "वह": "woh",
                  "वो": "woh", "ये": "ye", "अच्छा": "accha", "ठीक": "theek", "बात": "baat", "काम": "kaam", "नाम": "naam",
                  "साथ": "saath", "बाद": "baad", "कुछ": "kuch", "यूज": "use", "यूज़": "use", "ओके": "okay", "सही": "sahi"}
DEVANAGARI = re.compile("[ऀ-ॿ]")
DEVANAGARI_WORD = re.compile("[ऀ-ॣ॰-ॿ]+")


def hinglish_word(word):
    if word in HINGLISH_WORDS:
        return HINGLISH_WORDS[word]
    for pair, single in NUKTA.items():
        word = word.replace(pair, single)
    syllables = []  # [onset, vowel, coda, inherent 'a', open halant]
    for ch in word:
        cur = syllables[-1] if syllables else None
        if ch in CONSONANTS:
            if cur and cur[4]:  # after a halant: a consonant cluster
                cur[0] += CONSONANTS[ch]
                cur[4] = False
            else:
                syllables.append([CONSONANTS[ch], "a", "", True, False])
        elif ch == "्" and cur:  # halant: no vowel
            cur[1], cur[3], cur[4] = "", False, True
        elif ch in MATRAS and cur:
            cur[1], cur[3] = MATRAS[ch], False
        elif ch in SIGNS and cur:
            cur[2] += SIGNS[ch]
        elif ch in VOWELS:
            syllables.append(["", VOWELS[ch], "", False, False])
    # Hindi drops the inherent 'a' at the end of a word and in a VC_CV middle (करके -> karke, बोलता -> bolta),
    # judged right to left (समझना -> samajhna).
    if len(syllables) > 1 and syllables[-1][3] and not syllables[-1][2]:
        syllables[-1][1] = ""
    for i in range(len(syllables) - 2, 0, -1):
        s, prev, nxt = syllables[i], syllables[i - 1], syllables[i + 1]
        if s[3] and not s[2] and prev[1] and nxt[0] and nxt[1]:
            s[1] = ""
    return "".join(s[0] + s[1] + s[2] for s in syllables)


def hinglish(text):
    text = DEVANAGARI_WORD.sub(lambda m: hinglish_word(m.group()), text)
    return text.translate({0x964: ".", 0x965: ".", **{0x966 + d: str(d) for d in range(10)}})  # danda, digits
ESCAPES = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True) if sys.stdout else None
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def after(seconds, fn):
    QTimer.singleShot(int(seconds * 1000), fn)


def find_claude():
    found = shutil.which("claude")
    return found or str(Path.home() / ".local" / "bin" / "claude.exe")


def trust_workspace():
    """Pre-answer Claude's 'trust this folder' prompt for our workspace, the way Claude records it."""
    config = Path.home() / ".claude.json"
    key = str(WORKSPACE).replace("\\", "/")
    try:
        root = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
        if not isinstance(root, dict):
            log(f"{config} is not a JSON object; leaving it alone")
            return
        project = root.setdefault("projects", {}).setdefault(key, {})
        if project.get("hasTrustDialogAccepted") is True:
            return  # don't rewrite the user's config
        project["hasTrustDialogAccepted"] = True
        tmp = config.with_name(config.name + ".bolo.tmp")
        tmp.write_text(json.dumps(root, indent=2), encoding="utf-8")
        os.replace(tmp, config)  # atomic swap: an interrupted write can't truncate the config
        log(f"trusted the workspace in {config}")
    except (OSError, ValueError) as e:
        log(f"could not pre-trust the workspace: {e}")  # the 'trust this folder' fallback answers it


class Session(QObject):
    """The hidden Claude Code session. All methods run on the Qt thread; only the reader thread emits."""

    _output = pyqtSignal(object, str)
    _exited = pyqtSignal(object)
    state_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.proc = None
        self.state = "stopped"
        self.screen = ""
        self.last_output = 0.0
        self.lock = threading.Lock()
        self.repeat = QTimer(self, interval=50, timeout=lambda: self.write(VOICE_KEY))
        self._output.connect(self._received)
        self._exited.connect(self._child_exited)

    def _set(self, state):
        self.state = state
        self.state_changed.emit(state)

    def start(self):
        if self.state != "stopped":
            return
        claude = find_claude()
        if not Path(claude).exists():
            log(f"claude not found at {claude}")
            return
        self._set("starting")
        self.screen = ""
        # ConPTY only redraws changed cells, so words in the raw stream lose letters ("list ning");
        # a virtual screen shows what is really displayed.
        self.vt = pyte.Screen(120, 30)
        self.vt_stream = pyte.Stream(self.vt)
        for d in (WORKSPACE, BIN):
            d.mkdir(parents=True, exist_ok=True)
        trust_workspace()
        settings = LOCAL / "session-settings.json"
        # Voice on in hold mode, never auto-submit: layered over the user's settings for this session only.
        settings.write_text(json.dumps({"voice": {"autoSubmit": False, "enabled": True, "mode": "hold"}}))
        (BIN / "bolo-capture.cmd").write_text(CAPTURE_CMD, newline="")
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("CLAUDE")}
        env.update(
            TERM="xterm-256color",
            # Claude splits $EDITOR on spaces, so the script is found through PATH, not by its folder.
            EDITOR="cmd.exe /c bolo-capture.cmd",
            VISUAL="cmd.exe /c bolo-capture.cmd",
            BOLO_OUTBOX=str(OUTBOX),
            PATH=f"{BIN};{env.get('PATH', '')}",
        )
        # shortcut: runs claude.exe directly; an npm .cmd shim would need wrapping in cmd.exe /c
        try:
            proc = PtyProcess.spawn([claude, "--settings", str(settings)], cwd=str(WORKSPACE), env=env, dimensions=(30, 120))
        except Exception as e:
            log(f"could not start {claude}: {e}")
            self._set("stopped")
            return
        self.proc = proc
        log(f"started Claude Code (pid {proc.pid})")
        threading.Thread(target=self._read_loop, args=(proc,), daemon=True).start()

    def stop(self):
        self.repeat.stop()
        if self.proc:
            try:
                self.proc.terminate(force=True)
            except Exception:
                pass

    def _read_loop(self, proc):
        while True:
            try:
                data = proc.read(65536)
            except Exception:
                break
            # Answer terminal queries ConPTY lets through, like a basic terminal.
            if "\x1b[6n" in data:
                self.write("\x1b[1;1R", proc)
            if "\x1b[c" in data or "\x1b[0c" in data:
                self.write("\x1b[?62;22c", proc)
            self._output.emit(proc, data)
        self._exited.emit(proc)

    def _received(self, proc, data):
        if proc is not self.proc:
            return
        self.vt_stream.feed(data)
        text = ESCAPES.sub(" ", data)
        self.last_output = time.monotonic()
        self.screen += text
        if len(self.screen) > 20000:
            self.screen = self.screen[-10000:]
        if self.state != "starting":
            return
        if "trust this folder" in self.screen:  # pre-trust didn't take: pick "Yes, I trust this folder"
            self.screen = ""
            self.write("\x1b[B")
            after(0.4, lambda: self.write("\r"))
        elif any(s in self.screen for s in ("shift+tab to cycle", "? for shortcuts", 'Try "')):
            log("Claude Code is ready")
            self._set("ready")

    def _child_exited(self, proc):
        if proc is not self.proc:
            return
        log(f"Claude Code exited; last screen: {self.tail(400)}")
        self.proc = None
        self.repeat.stop()
        self._set("stopped")

    def write(self, s, proc=None):
        proc = proc or self.proc
        if not proc:
            return
        with self.lock:
            try:
                proc.write(s)
            except Exception:
                pass  # just exited; _child_exited takes it from here

    def display(self):
        return "\n".join(self.vt.display)

    def prompt_text(self):
        """The live text in Claude's prompt: the '❯' line plus its 2-space-indented wrapped lines, up to
        the next ──── rule, without the voice level bars. None if the prompt isn't on screen."""
        lines = self.vt.display
        # The last '❯' line: higher up, the screen can hold a stale one (e.g. "❯ … 0 out · 0 turns").
        start = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith("❯")), None)
        if start is None:
            return None
        parts = [lines[start][2:]]
        for line in lines[start + 1:]:
            if line.startswith("─"):
                break
            parts.append(line[2:])
        # Full-width lines are soft wraps (joined as is); padded ones end in spaces, collapsed to one.
        text = re.sub(r"\s+", " ", "".join(parts).translate({ord(c): None for c in "▁▂▃▄▅▆▇█"})).strip()
        return "" if text.startswith('Try "') else text  # Claude's placeholder in an empty prompt

    def tail(self, n):
        return re.sub(r"\s+", " ", self.screen[-n:])

    # Dictation

    def start_repeats(self):
        self.write(VOICE_KEY)
        self.repeat.start()

    def finish(self, done):
        """Release the voice key, wait for the console to go quiet (ConPTY only sends changed cells,
        so 'processing' can't be watched going away), then take the text out of the prompt."""
        self.repeat.stop()
        mark, started = len(self.screen), time.monotonic()
        saw = [False]

        def poll():
            since = self.screen[mark:]
            quiet, elapsed = time.monotonic() - self.last_output, time.monotonic() - started
            if "No speech detected" in since:
                log("no speech detected")
                return done("")
            saw[0] = saw[0] or "processing" in since or "processing" in self.display()
            if (saw[0] and quiet > 0.4) or (not saw[0] and elapsed > 2.5 and quiet > 0.6) or elapsed > 20:
                self._capture_retrying(4 if saw[0] else 1, done)
            else:
                after(0.05, poll)

        after(0.1, poll)

    def _capture_retrying(self, retries, done):
        def got(text):
            if text or retries <= 0:
                return done(text)
            log("prompt was empty; capturing again")
            after(0.5, lambda: self._capture_retrying(retries - 1, done))

        self.capture(got)

    def cancel(self):
        self.repeat.stop()
        after(0.1, lambda: self.write("\x1b"))
        after(2, lambda: self.capture(lambda t: t and log(f"discarded: {t}")))

    def capture(self, done):
        """Ctrl+G: Claude opens the prompt in $EDITOR, which writes it to the outbox and empties it."""
        try:
            OUTBOX.unlink()
        except FileNotFoundError:
            pass
        self.write("\x07")
        started = time.monotonic()

        def poll():
            if OUTBOX.exists():
                try:
                    return done(OUTBOX.read_text(encoding="utf-8").strip())
                except OSError:
                    pass  # still being moved into place
            if time.monotonic() - started > 4:
                log(f"capture timed out; screen: {self.tail(300)}")
                return done("")
            after(0.05, poll)

        poll()


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetForegroundWindow.restype = wintypes.HWND
VK_RCONTROL, VK_ESCAPE, VK_BACK = 0xA3, 0x1B, 0x08
KEYUP, UNICODE = 0x2, 0x4
TAG = 0x424F4C4F  # "BOLO": marks the keys we send ourselves, so our hook ignores them


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]  # sized like MOUSEINPUT, the largest member

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def type_diff(old, new):
    """Turn already-typed `old` into `new` in the focused app: backspace to the common prefix, type the rest."""
    keep = len(os.path.commonprefix([old, new]))
    keys = [(VK_BACK, 0, 0), (VK_BACK, 0, KEYUP)] * (len(old) - keep)
    units = new[keep:].encode("utf-16-le")
    for i in range(0, len(units), 2):  # one UTF-16 unit per event, so emoji etc. arrive as surrogate pairs
        u = int.from_bytes(units[i:i + 2], "little")
        keys += [(0, u, UNICODE), (0, u, UNICODE | KEYUP)]
    if not keys:
        return
    arr = (INPUT * len(keys))(*(INPUT(type=1, ki=KEYBDINPUT(vk, scan, flags, 0, TAG)) for vk, scan, flags in keys))
    if user32.SendInput(len(keys), arr, ctypes.sizeof(INPUT)) != len(keys):
        log(f"SendInput failed ({ctypes.get_last_error()})")


class Hotkey(QObject):
    """Right Ctrl via a raw WH_KEYBOARD_LL hook on its own thread (pynput lost Right Ctrl's key-down
    here). The callback only emits, so Windows never drops the hook for being slow."""

    pressed = pyqtSignal()
    released = pyqtSignal()
    cancelled = pyqtSignal(bool)  # True: Esc (ours, erase what was typed); False: a key the app also got

    def __init__(self):
        super().__init__()
        self.down = False
        self.thread_id = 0
        self._proc = HOOKPROC(self._hook)  # keep a reference, or ctypes frees the callback
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.SetWindowsHookExW(13, self._proc, None, 0):  # 13 = WH_KEYBOARD_LL
            log(f"could not install the keyboard hook (error {ctypes.get_last_error()})")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)  # WM_QUIT ends the hook thread

    def _hook(self, code, wparam, lparam):
        if code == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if k.dwExtraInfo != TAG and self._key(k.vkCode, wparam in (0x100, 0x104)):  # WM_(SYS)KEYDOWN
                return 1  # swallowed: other apps never see it
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _key(self, vk, down):
        """Returns True to swallow the key. Right Ctrl is always swallowed: if apps saw Ctrl held, the
        text typed while you talk would turn into shortcuts (Ctrl+W, Ctrl+Backspace…)."""
        if vk == VK_RCONTROL:
            if down and not self.down:  # ignore auto-repeat
                self.down = True
                self.pressed.emit()
            elif not down and self.down:
                self.down = False
                self.released.emit()
            return True
        if down and vk == VK_ESCAPE and self.down:
            self.cancelled.emit(True)
            return True
        if down and self.down:  # another key while talking: stop, and let the key through
            self.cancelled.emit(False)
        return False


def dot_icon(color):
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QColor("white"))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pix)


class App(QObject):
    ICONS = {"stopped": "#666666", "starting": "#666666", "idle": "#3b82f6", "listening": "#ef4444", "transcribing": "#f59e0b"}

    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.phase = "idle"
        self.press_id = 0
        self.quitting = False
        self.target, self.typed = None, ""  # the window being dictated into, and what was typed there so far
        self.streamer = QTimer(self, interval=100, timeout=self.stream)
        self.icons = {k: dot_icon(v) for k, v in self.ICONS.items()}

        self.tray = QSystemTrayIcon(self.icons["starting"])
        menu = QMenu()
        self.status = menu.addAction("Starting Claude…")
        self.status.setEnabled(False)
        menu.addAction("Restart session", self.restart)
        menu.addAction("Open log", lambda: os.startfile(LOG))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.menu = menu

        self.session = Session()
        self.session.state_changed.connect(self.session_changed)
        self.hotkey = Hotkey()
        self.hotkey.pressed.connect(self.pressed)
        self.hotkey.released.connect(self.released)
        self.hotkey.cancelled.connect(self.cancelled)
        self.session.start()
        if self.session.state == "stopped":
            self.notify("Claude Code was not found (looked on PATH and in ~/.local/bin)")

    def notify(self, msg):
        self.tray.showMessage("Bolo", msg, QSystemTrayIcon.MessageIcon.Information, 2500)

    def set_icon(self, name, tip):
        self.tray.setIcon(self.icons[name])
        self.tray.setToolTip(f"Bolo: {tip}")
        self.status.setText(tip)

    def session_changed(self, state):
        if state == "ready":
            self.set_icon("idle", "Ready: hold Right Ctrl to dictate")
        elif state == "starting":
            self.set_icon("starting", "Starting Claude…")
        else:
            self.phase = "idle"
            self.set_icon("stopped", "Claude stopped; restarting…")
            if not self.quitting:
                after(3, self.session.start)

    def restart(self):
        self.session.stop()  # exit handler restarts it

    def quit(self):
        self.quitting = True
        self.session.stop()
        self.hotkey.stop()
        self.tray.hide()
        self.qapp.quit()

    # Dictation

    def pressed(self):
        log(f"dictation key pressed (session {self.session.state}, phase {self.phase})")
        if self.phase != "idle":
            return
        if self.session.state != "ready":
            return self.notify("Claude is still starting")
        self.press_id += 1
        self.phase = "waiting"
        self.target, self.typed = user32.GetForegroundWindow(), ""
        self.session.start_repeats()
        self.wait_for_mic(self.press_id, time.monotonic())

    def stream(self):
        """While talking: mirror Claude's live prompt into the app you were in, as Claude shows it."""
        if not self.target:
            return
        if user32.GetForegroundWindow() != self.target:
            log("focus moved; stopped typing into the old window")
            self.target = None
            return
        text = self.session.prompt_text()
        if text is not None:
            text = hinglish(text)
        if text is not None and text != self.typed:
            type_diff(self.typed, text)
            self.typed = text

    def wait_for_mic(self, pid, started):
        """Show 'listening' only once Claude says it is (Claude opens the mic just before)."""
        if pid != self.press_id or self.phase != "waiting":
            return
        if "listening" in self.session.display().lower():
            self.phase = "listening"
            self.set_icon("listening", "Listening…")
            log(f"listening after {int((time.monotonic() - started) * 1000)} ms")
            self.streamer.start()
            return
        if time.monotonic() - started > 3:
            log(f"Claude did not start listening; screen: {self.session.tail(300)}")
            self.session.cancel()
            self.phase = "idle"
            self.notify("Claude didn't start listening: check /voice works in claude")
            return
        after(0.03, lambda: self.wait_for_mic(pid, started))

    def released(self):
        if self.phase == "waiting":  # let go before Claude was listening: nothing to transcribe
            log(f"released before Claude was listening; screen: {self.session.tail(200)}")
            self.session.cancel()
            self.phase = "idle"
        elif self.phase == "listening":
            self.streamer.stop()  # before Ctrl+G empties Claude's prompt, which would erase what was typed
            self.stream()
            self.phase = "transcribing"
            self.set_icon("transcribing", "Transcribing…")
            self.session.finish(self.transcribed)

    def cancelled(self, erase):
        if self.phase in ("waiting", "listening"):
            log("cancelled")
            self.streamer.stop()
            if erase and self.target and user32.GetForegroundWindow() == self.target:
                type_diff(self.typed, "")
            self.target, self.typed = None, ""
            self.session.cancel()
            self.phase = "idle"
            self.set_icon("idle", "Ready: hold Right Ctrl to dictate")

    def transcribed(self, text):
        """Claude's final text replaces the live one (only the differing tail is retyped)."""
        final = re.sub(r"\s+", " ", text).strip() or self.typed  # no final text: keep what was typed live
        self.deliver(hinglish(final))

    def deliver(self, final):
        self.phase = "idle"
        self.set_icon("idle", "Ready: hold Right Ctrl to dictate")
        if final:
            if self.target and user32.GetForegroundWindow() == self.target:
                type_diff(self.typed, final + " ")  # trailing space so the next dictation doesn't run into this one
                log(f"typed {len(final)} characters")
            else:
                QGuiApplication.clipboard().setText(final)
                self.notify("Focus changed while you talked: the dictation is on the clipboard")
        self.target, self.typed = None, ""


def selftest(qapp):
    """End-to-end without a mic: spawn, reach Ready, type a token, read it live, Ctrl+G, read the outbox."""
    session = Session()
    # prompt_text on a synthetic screen: a soft-wrapped full line, a padded line, level bars, placeholder.
    for raw, want in (("─" * 20 + "\r\n❯\xa0" + "a" * 18 + "\r\n  bb cc   \r\n  dd\r\n" + "─" * 20, "a" * 18 + "bb cc dd"),
                      ("❯\xa0▁▃▅\r\n" + "─" * 20, ""), ('❯\xa0Try "fix lint errors"\r\n' + "─" * 20, "")):
        session.vt = pyte.Screen(20, 6)
        pyte.Stream(session.vt).feed(raw)
        assert session.prompt_text() == want, (raw, session.prompt_text())
    for hindi, want in (("अभी मैं हिंदी में बोल रहा हूँ Claude यूज करके।", "abhi main hindi mein bol raha hoon Claude use karke."),
                        ("क्या तुम समझना चाहते हो", "kya tum samajhna chahte ho"), ("बाज़ार १२ बजे", "bazar 12 baje"),
                        ("मैंने कमला को बोलकर", "maine kamla ko bolkar")):
        assert hinglish(hindi) == want, (hinglish(hindi), want)
    token = "selftest-ok-क्यामैंआवाज़"  # no spaces: Space is the push-to-talk key; Hindi checks the width patch
    result = {"code": 1}

    def finish(code, msg):
        print(msg, flush=True)
        result["code"] = code
        session.stop()
        after(0.5, qapp.quit)

    def check_ready(started=time.monotonic()):
        if session.state == "ready":
            # Typed a second after Ready, like a real press: Claude is still redrawing its start-up screen.
            return after(1, lambda: (session.write(token), after(1, read_prompt)))
        if time.monotonic() - started > 60 or session.state == "stopped":
            return finish(1, f"FAIL: session not ready (state {session.state}); screen: {session.tail(500)}")
        after(0.2, check_ready)

    def read_prompt():
        live = session.prompt_text()
        if live != token:
            return finish(1, f"FAIL: live prompt read {live!r}, expected {token!r}")
        session.capture(got)

    def got(text):
        if text == token:
            print(f"PASS: captured {text!r} from the hidden session", flush=True)
            finish(0, "PASS: all checks")
        else:
            finish(1, f"FAIL: captured {text!r}, expected {token!r}; screen: {session.tail(500)}")

    after(90, lambda: finish(1, f"FAIL: overall timeout; screen: {session.tail(500)}"))
    session.start()
    check_ready()
    qapp.exec()
    session.stop()
    return result["code"]


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    if sys.stdout:  # the console's cp1252 can't print Claude's box-drawing characters
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    if "--selftest" in sys.argv:
        sys.exit(selftest(qapp))
    app = App(qapp)
    qapp.aboutToQuit.connect(app.session.stop)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
