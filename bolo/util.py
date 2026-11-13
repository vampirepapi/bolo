"""Paths, logging, JSON storage and Qt timing helpers shared by every module."""
import json
import os
import sys
import time
import traceback
from pathlib import Path

from PyQt6.QtCore import QTimer

LOCAL = Path(os.environ["LOCALAPPDATA"]) / "Bolo"
WORKSPACE, BIN, OUTBOX, LOG = LOCAL / "workspace", LOCAL / "bin", LOCAL / "outbox.txt", LOCAL / "log.txt"
SETTINGS_FILE, HISTORY_FILE = LOCAL / "settings.json", LOCAL / "history.json"


LOG_LIMIT = 1_000_000  # bytes; then log.txt becomes log.old.txt, so the two never pass about 2 MB


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True) if sys.stdout else None
    try:
        if LOG.exists() and LOG.stat().st_size > LOG_LIMIT:
            os.replace(LOG, LOG.with_name("log.old.txt"))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def after(seconds, fn):
    QTimer.singleShot(int(seconds * 1000), fn)


def load_json(path, default):
    """The file's JSON, or `default` when it is missing or unreadable (logged, never fatal)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        log(f"could not read {path}: {e}; using defaults")
        return default


def save_json(path, data):
    """Write to a sibling file and swap it in, so a crash mid-write can't truncate the old file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def install_excepthook():
    """Under pythonw nothing is printed, and PyQt aborts on an exception in a slot unless a hook is
    set: log the traceback and keep running."""
    def hook(kind, value, tb):
        log("unhandled error:\n" + "".join(traceback.format_exception(kind, value, tb)).rstrip())
    sys.excepthook = hook
