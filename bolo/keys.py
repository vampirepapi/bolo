"""The global keyboard hook and typing into the focused app (SendInput)."""
import ctypes
import os
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

from .util import log


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
VK_ESCAPE, VK_BACK = 0x1B, 0x08
KEYUP, UNICODE = 0x2, 0x4
TAG = 0x424F4C4F  # "BOLO": marks the keys we send ourselves, so our hook ignores them
ALTGR_SCAN = 0x21D  # the fake Left Ctrl that Right Alt (AltGr) sends on some keyboard layouts

# Keys that can be the talk key: ones that type nothing, since the talk key is swallowed system-wide.
TALK_KEYS = {0xA3: "Right Ctrl", 0xA5: "Right Alt", 0x5C: "Right Win", 0x5D: "Menu", 0x14: "Caps Lock",
             0x91: "Scroll Lock", 0x13: "Pause", 0x2D: "Insert",
             **{0x70 + i: f"F{i + 1}" for i in range(24)}}


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
    """The talk key via a raw WH_KEYBOARD_LL hook on its own thread. The callback only reads plain
    attributes and emits, so Windows never drops the hook for being slow. The controller sets
    `vk`, `paused`, `dictating` and `recording`."""

    pressed = pyqtSignal()
    released = pyqtSignal()
    cancelled = pyqtSignal(bool)  # True: Esc (ours, erase what was typed); False: a key the app also got
    recorded = pyqtSignal(int)    # a key pressed while recording a new talk key

    def __init__(self, vk=0xA3):
        super().__init__()
        self.vk = vk
        self.paused = False      # the talk key goes through to apps as a normal key
        self.dictating = False   # Esc and other keys cancel only while dictating
        self.recording = False   # the next key is reported via `recorded` and swallowed
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
            if k.dwExtraInfo != TAG and k.scanCode != ALTGR_SCAN and self._key(k.vkCode, wparam in (0x100, 0x104)):
                return 1  # swallowed: other apps never see it
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _key(self, vk, down):
        """Returns True to swallow the key. The talk key is swallowed: if apps saw it (Ctrl held), the
        text typed while you talk would turn into shortcuts (Ctrl+W, Ctrl+Backspace…)."""
        if self.recording:
            if down:
                self.recording = False
                self.recorded.emit(vk)
            return True
        if self.paused:
            return False
        if vk == self.vk:
            if down and not self.down:  # ignore auto-repeat
                self.down = True
                self.pressed.emit()
            elif not down and self.down:
                self.down = False
                self.released.emit()
            return True
        if down and self.dictating:
            if vk == VK_ESCAPE:
                self.cancelled.emit(True)
                return True
            self.cancelled.emit(False)  # another key: stop dictating, and let the key through
        return False
