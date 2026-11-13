"""User settings: a JSON file whose defaults match how Bolo first worked."""
from PyQt6.QtCore import QObject, pyqtSignal

from .hinglish import HINGLISH_WORDS, LOANWORDS, WORDS_SEED, normalize
from .keys import TALK_KEYS
from .util import SETTINGS_FILE, load_json, log, save_json

DEFAULTS = {
    "talk_key": {"vk": 0xA3, "name": "Right Ctrl"},
    "mode": "hold",        # hold: talk while held | tap: tap to start, tap to stop
    "output": "live",      # live: type as you speak | release: type when you let go
    "hinglish": True,
    "language": "",        # "" = Claude's default; otherwise passed to Claude Code as its language setting
    "capsule": True,
    "sounds": False,
    "words": dict(HINGLISH_WORDS),  # the user's Hinglish spellings, seeded with the built-ins
    "words_seed": WORDS_SEED,       # which built-in additions the stored list already has
}
CHOICES = {"mode": ("hold", "tap"), "output": ("live", "release"), "language": ("", "english", "hindi")}


class Settings(QObject):
    changed = pyqtSignal(str)

    def __init__(self, path=SETTINGS_FILE):
        super().__init__()
        self.path = path
        stored = load_json(path, {})
        if not isinstance(stored, dict):
            log(f"{path} is not a JSON object; using defaults")
            stored = {}
        self.data = {}
        for key, default in DEFAULTS.items():
            value = stored.get(key, default)
            # A value of the wrong type or outside its choices (hand-edited, older version) falls back.
            if type(value) is not type(default) or (key in CHOICES and value not in CHOICES[key]):
                value = default
            self.data[key] = value
        self.data["words"] = {normalize(k): v for k, v in self.data["words"].items() if isinstance(v, str)}
        if stored.get("words_seed", 1) < 2 and "words" in stored:
            # New built-ins reach an existing list once; words the user changed or removed earlier stay as they are.
            self.data["words"] = {**{k: v for k, v in LOANWORDS.items() if k not in self.data["words"]}, **self.data["words"]}
            self.data["words_seed"] = WORDS_SEED
            self.save()
        vk = self.data["talk_key"].get("vk")
        self.data["talk_key"] = {"vk": vk, "name": TALK_KEYS[vk]} if vk in TALK_KEYS else DEFAULTS["talk_key"]

    def __getitem__(self, key):
        return self.data[key]

    def set(self, key, value):
        if self.data[key] == value:
            return
        self.data[key] = value
        self.save()
        self.changed.emit(key)

    def save(self):
        try:
            save_json(self.path, self.data)
        except OSError as e:
            log(f"could not save settings: {e}")
