"""The hidden Claude Code session: ConPTY, a pyte virtual screen, and the Ctrl+G capture."""
import json
import os
import re
import shutil
import threading
import time
import types
import unicodedata
from pathlib import Path

import pyte
import pyte.screens
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from winpty import PtyProcess

from .util import BIN, LOCAL, OUTBOX, WORKSPACE, after, log

# pyte keeps a zero-width character only if Unicode calls it "combining"; otherwise it drops it and
# the rest of that chunk ("क्या मैं" read as "क्य"). Devanagari vowel signs (ा ै …) aren't "combining",
# so they're declared so here and get attached to the letter before them, the way ConPTY lays them out.
# shortcut: Devanagari only; other Indic scripts would need their ranges added here.
pyte.screens.unicodedata = types.SimpleNamespace(
    normalize=unicodedata.normalize,
    combining=lambda c: 1 if "ऀ" <= c <= "ॿ" else unicodedata.combining(c))

# shortcut: assumes Claude's default push-to-talk key (Space); read ~/.claude/keybindings.json if you rebind voice:pushToTalk
VOICE_KEY = " "
BARS = "▁▂▃▄▅▆▇█"  # Claude's microphone level bars
CAPTURE_CMD = (
    "@echo off\r\n"
    'copy /y "%~1" "%BOLO_OUTBOX%.tmp" >nul\r\n'
    'move /y "%BOLO_OUTBOX%.tmp" "%BOLO_OUTBOX%" >nul\r\n'
    'type nul > "%~1"\r\n'
)

ESCAPES = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.")

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


ALT_SCREEN_MODES = {47, 1047, 1049}


class AltScreen(pyte.Screen):
    """pyte has no alternate screen. Claude switches to it while the Ctrl+G editor runs and back after;
    without this the editor's screen overwrites the main one until Claude redraws it."""

    _saved = None

    def set_mode(self, *modes, **kwargs):
        if kwargs.get("private") and ALT_SCREEN_MODES & set(modes) and self._saved is None:
            self._saved = ({y: dict(line) for y, line in self.buffer.items()}, self.cursor.x, self.cursor.y)
            super().set_mode(*modes, **kwargs)
            self.erase_in_display(2)
            return
        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes, **kwargs):
        super().reset_mode(*modes, **kwargs)
        if kwargs.get("private") and ALT_SCREEN_MODES & set(modes) and self._saved is not None:
            lines, x, y = self._saved
            self._saved = None
            self.buffer.clear()
            for row, cells in lines.items():
                self.buffer[row].update(cells)
            self.cursor.x, self.cursor.y = x, y
            self.dirty.update(range(self.lines))


class Session(QObject):
    """The hidden Claude Code session. All methods run on the Qt thread; only the reader thread emits."""

    _output = pyqtSignal(object, str)
    _exited = pyqtSignal(object)
    state_changed = pyqtSignal(str)

    def __init__(self, language=""):
        super().__init__()
        self.language = language  # "" leaves Claude's own language setting alone
        self.vt = AltScreen(120, 30)
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
        self.vt = AltScreen(120, 30)
        self.vt_stream = pyte.Stream(self.vt)
        for d in (WORKSPACE, BIN):
            d.mkdir(parents=True, exist_ok=True)
        trust_workspace()
        settings = LOCAL / "session-settings.json"
        # Voice on in hold mode, never auto-submit: layered over the user's settings for this session only.
        session_settings = {"voice": {"autoSubmit": False, "enabled": True, "mode": "hold"}}
        if self.language:
            session_settings["language"] = self.language
        settings.write_text(json.dumps(session_settings))
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
            # Answer the device-attributes query like a basic terminal (cursor queries: see _received).
            if "\x1b[c" in data or "\x1b[0c" in data:
                self.write("\x1b[?62;22c", proc)
            self._output.emit(proc, data)
        self._exited.emit(proc)

    def _received(self, proc, data):
        if proc is not self.proc:
            return
        # Claude asks where the cursor is (at start-up and after the Ctrl+G editor) and draws relative to
        # the answer, so answer with the real position as of that point in the output. Always saying 1;1
        # made it draw the prompt at the top after the first capture: the live reader found an empty
        # prompt and nothing streamed from the second dictation on.
        parts = data.split("\x1b[6n")
        for i, part in enumerate(parts):
            self.vt_stream.feed(part)
            if i < len(parts) - 1:
                self.write(f"\x1b[{self.vt.cursor.y + 1};{self.vt.cursor.x + 1}R")
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
        log(f"Claude Code exited; screen: {self.screen_summary(400)}")
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
        text = re.sub(r"\s+", " ", "".join(parts).translate({ord(c): None for c in BARS})).strip()
        return "" if text.startswith('Try "') else text  # Claude's placeholder in an empty prompt

    def levels(self):
        """Claude's microphone level bars (▁…█) on the prompt line, as heights 1-8, newest last."""
        line = next((l for l in reversed(self.vt.display) if l.startswith("❯")), "")
        return [BARS.index(c) + 1 for c in line if c in BARS]

    def screen_summary(self, n=300):
        """Claude's screen for the log, minus the prompt block, which holds what was dictated."""
        kept, in_prompt = [], False
        for line in self.vt.display:
            if line.startswith("❯"):
                in_prompt = True
            elif line.startswith("─"):
                in_prompt = False
            if not in_prompt and line.strip():
                kept.append(line.strip())
        return re.sub(r"\s+", " ", " | ".join(kept))[-n:]

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
        after(2, lambda: self.capture(lambda t: t and log(f"discarded {len(t)} characters")))

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
                log(f"capture timed out; screen: {self.screen_summary()}")
                return done("")
            after(0.05, poll)

        poll()
