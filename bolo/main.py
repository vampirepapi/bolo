"""Entry point: python app.py (tray app) or python app.py --selftest (mic-free checks)."""
import os
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from .util import LOCAL, SETTINGS_FILE, install_excepthook, log

SERVER = f"bolo-{os.environ.get('USERNAME', 'user')}"


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    if sys.stdout:  # the console's cp1252 can't print Claude's box-drawing characters
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    install_excepthook()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("Bolo")
    from .ui.theme import STYLESHEET
    qapp.setStyleSheet(STYLESHEET)
    if "--selftest" in sys.argv:
        from .selftest import selftest
        sys.exit(selftest(qapp))

    # One Bolo at a time: two keyboard hooks would both type. A second launch opens Settings instead.
    probe = QLocalSocket()
    probe.connectToServer(SERVER)
    if probe.waitForConnected(300):
        probe.write(b"settings")
        probe.waitForBytesWritten(300)
        log("Bolo is already running; asked it to open Settings")
        return
    QLocalServer.removeServer(SERVER)  # left behind by a crash
    server = QLocalServer()
    server.listen(SERVER)

    from .controller import App
    first_launch = not SETTINGS_FILE.exists()
    app = App(qapp)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), app.open_settings()))
    if first_launch:
        app.settings.save()
        app.open_settings()
    qapp.aboutToQuit.connect(app.session.stop)
    sys.exit(qapp.exec())
