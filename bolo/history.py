"""The last 30 dictations: the only place dictated text is kept on disk."""
import time

from PyQt6.QtCore import QObject, pyqtSignal

from .util import HISTORY_FILE, load_json, log, save_json

MAX_ENTRIES = 30


def when(ts):
    """'14:05', 'Yesterday 14:05' or '12 Nov 14:05'."""
    t, now = time.localtime(ts), time.localtime()
    if t[:3] == now[:3]:
        return time.strftime("%H:%M", t)
    if time.localtime(time.time() - 86400)[:3] == t[:3]:
        return time.strftime("Yesterday %H:%M", t)
    return time.strftime("%d %b %H:%M", t).lstrip("0")


class History(QObject):
    changed = pyqtSignal()

    def __init__(self, path=HISTORY_FILE):
        super().__init__()
        self.path = path
        stored = load_json(path, [])
        self.entries = [e for e in stored if isinstance(e, dict) and isinstance(e.get("text"), str)
                        and isinstance(e.get("time"), (int, float))][:MAX_ENTRIES] if isinstance(stored, list) else []
        for e in self.entries:
            if not isinstance(e.get("source", ""), str):
                del e["source"]

    def add(self, text, source=""):
        """`source`: the Devanagari Claude heard, when `text` is its Hinglish; lets a spelling be fixed later."""
        entry = {"time": time.time(), "text": text, **({"source": source} if source else {})}
        self.entries = [entry] + self.entries[:MAX_ENTRIES - 1]
        self._save()

    def retext(self, entry, text):
        entry["text"] = text
        self._save()

    def clear(self):
        self.entries = []
        self._save()

    def _save(self):
        try:
            save_json(self.path, self.entries)
        except OSError as e:
            log(f"could not save history: {e}")
        self.changed.emit()
