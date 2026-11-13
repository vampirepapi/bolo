"""Start with Windows: a per-user Run entry. The registry, not settings.json, is the source of truth."""
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Bolo"


def command():
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")  # no console window at login
    launcher = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{pythonw if pythonw.exists() else exe}" "{launcher}"'


def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, NAME)
        return True
    except OSError:
        return False


def set_enabled(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        elif enabled():
            winreg.DeleteValue(key, NAME)
