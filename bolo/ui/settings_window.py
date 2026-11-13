"""The Settings window: General, Hinglish, History, Claude session, About."""
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import __version__, autostart
from ..hinglish import hinglish, normalize, spellings
from ..history import when
from ..keys import TALK_KEYS, VK_ESCAPE
from ..util import LOG
from .theme import ACCENT_TEXT, AMBER, GREEN, GREY, MUTED, RED, icon, logo_icon
from .widgets import Row, Segmented, Toggle, card, hbox, label

REPO_URL = "https://github.com/vampirepapi/bolo"
LANGUAGES = [("", "Auto (Claude's default)"), ("english", "English"), ("hindi", "Hindi")]
STATUS_DOTS = {"ready": GREEN, "starting": AMBER, "stopped": RED, "paused": GREY}
SECTIONS = [("general", "General"), ("hinglish", "Hinglish"), ("history", "History"),
            ("session", "Claude session"), ("about", "About")]


def page(title, lead=""):
    """A scrollable page with a title; returns (scroll area, the column layout to fill)."""
    inner = QWidget()
    col = QVBoxLayout(inner)
    col.setContentsMargins(40, 28, 40, 28)
    col.setSpacing(14)
    col.addWidget(label(title, "h1"))
    if lead:
        col.addWidget(label(lead, "lead", wrap=True))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(inner)
    return scroll, col


class SettingsWindow(QWidget):
    def __init__(self, settings, history, controller):
        super().__init__(objectName="window")
        self.settings, self.history, self.ctl = settings, history, controller
        self.setWindowTitle("Bolo Settings")
        self.setWindowIcon(logo_icon())
        self.resize(920, 760)
        self.setMinimumSize(760, 560)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._sidebar())
        self.stack = QStackedWidget()
        for key, _ in SECTIONS:
            self.stack.addWidget(getattr(self, f"_page_{key}")())
        root.addWidget(self.stack, 1)
        self.show_section("general")
        settings.changed.connect(self._setting_changed)
        history.changed.connect(self._fill_history)

    # Navigation

    def _sidebar(self):
        side = QWidget(objectName="sidebar")
        side.setFixedWidth(220)
        col = QVBoxLayout(side)
        col.setContentsMargins(10, 14, 10, 14)
        col.setSpacing(2)
        self.nav = {}
        group = QButtonGroup(self)
        for key, title in SECTIONS:
            b = QPushButton(f"  {title}", objectName="nav", checkable=True)
            b.setIcon(icon(key, "#44403C", 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self.show_section(k))
            group.addButton(b)
            self.nav[key] = b
            col.addWidget(b)
        col.addStretch(1)
        box = QFrame(objectName="statusBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        self.side_status = QLabel()
        self.side_status.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.side_detail = label("", "muted", wrap=True)
        lay.addWidget(self.side_status)
        lay.addWidget(self.side_detail)
        col.addWidget(box)
        return side

    def show_section(self, key):
        self.nav[key].setChecked(True)
        self.stack.setCurrentIndex([k for k, _ in SECTIONS].index(key))

    def open(self, key="general"):
        self.show_section(key)
        self.start_toggle.blockSignals(True)
        self.start_toggle.setChecked(autostart.enabled())  # the registry may have changed outside Bolo
        self.start_toggle.blockSignals(False)
        self.show()
        self.raise_()
        self.activateWindow()

    def set_session_state(self, state, text, detail):
        dot = STATUS_DOTS.get(state, GREY)
        self.side_status.setText(f'<span style="color:{dot}">●</span>&nbsp; {text}')
        self.side_detail.setText(detail)
        self.session_status.setText(f'<span style="color:{dot}">●</span>&nbsp; {text}')

    # General

    def _page_general(self):
        s = self.settings
        scroll, col = page("General")
        self.key_chip = label(s["talk_key"]["name"], "kbd")
        self.change_key = QPushButton("Change…")
        self.change_key.clicked.connect(self._record_key)
        self.key_row = Row("Talk key", "Hold it in any app. Other apps no longer see this key.",
                           hbox(self.key_chip, self.change_key))
        self.mode = Segmented([("hold", "Hold to talk"), ("tap", "Tap on, tap off")], s["mode"])
        self.mode.changed.connect(lambda v: s.set("mode", v))
        self.output = Segmented([("live", "As you speak"), ("release", "When you let go")], s["output"])
        self.output.changed.connect(lambda v: s.set("output", v))
        col.addWidget(label("DICTATION", "section"))
        col.addWidget(card(self.key_row,
                           Row("How you talk", "Hold the key while you speak, or tap it once to start and again to stop.", self.mode),
                           Row("Text appears", "As you speak types words as Claude hears them, then corrects them.", self.output)))

        self.hinglish_toggle = Toggle("Write Hindi as Hinglish", s["hinglish"])
        self.hinglish_toggle.toggled.connect(lambda v: s.set("hinglish", v))
        self.language = QComboBox()
        self.language.setMinimumWidth(220)
        for value, title in LANGUAGES:
            self.language.addItem(title, value)
        self.language.setCurrentIndex([v for v, _ in LANGUAGES].index(s["language"]))
        self.language.currentIndexChanged.connect(lambda i: s.set("language", LANGUAGES[i][0]))
        col.addWidget(label("LANGUAGE", "section"))
        col.addWidget(card(Row("Write Hindi as Hinglish", "अभी मैं बोल रहा हूँ  →  abhi main bol raha hoon", self.hinglish_toggle, 64),
                           Row("Dictation language", "Passed to Claude Code's voice mode. Changing it restarts the session.", self.language)))

        self.capsule_toggle = Toggle("Show the capsule while listening", s["capsule"])
        self.capsule_toggle.toggled.connect(lambda v: s.set("capsule", v))
        self.sounds_toggle = Toggle("Start and stop sounds", s["sounds"])
        self.sounds_toggle.toggled.connect(lambda v: s.set("sounds", v))
        self.start_toggle = Toggle("Start Bolo when Windows starts", autostart.enabled())
        self.start_toggle.toggled.connect(self._set_autostart)
        col.addWidget(label("FEEDBACK AND STARTUP", "section"))
        col.addWidget(card(Row("Show the capsule while listening", "", self.capsule_toggle, 56),
                           Row("Start and stop sounds", "", self.sounds_toggle, 56),
                           Row("Start Bolo when Windows starts", "Adds Bolo to your sign-in apps (current user only).", self.start_toggle, 56)))
        col.addStretch(1)
        return scroll

    def _record_key(self):
        self.change_key.setText("Press a key…")
        self.change_key.setEnabled(False)
        self.key_chip.setText("…")
        self.ctl.record_talk_key(self._key_recorded)

    def hideEvent(self, e):
        self.ctl.cancel_key_recording()  # never leave the next key press captured
        super().hideEvent(e)

    def _key_recorded(self, vk):
        """vk: the key pressed, or None when recording was cancelled."""
        self.change_key.setText("Change…")
        self.change_key.setEnabled(True)
        if vk in TALK_KEYS:
            self.settings.set("talk_key", {"vk": vk, "name": TALK_KEYS[vk]})
            self.key_row.sub.setText("Hold it in any app. Other apps no longer see this key.")
        elif vk not in (None, VK_ESCAPE):
            self.key_row.sub.setText("That key types text, so it can't be the talk key. Try Right Ctrl, Right Alt, "
                                     "Caps Lock, Menu, Insert, Pause, Scroll Lock or F1–F24.")
        self.key_chip.setText(self.settings["talk_key"]["name"])

    def _set_autostart(self, on):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self.start_toggle.blockSignals(True)
            self.start_toggle.setChecked(autostart.enabled())
            self.start_toggle.blockSignals(False)
            self.ctl.message(f"Couldn't change sign-in apps: {e}", ok=False)

    def _setting_changed(self, key):
        if key == "words":
            self._fill_words()
            self._update_try()

    # Hinglish

    def _page_hinglish(self):
        scroll, col = page("Hinglish", "Hindi you speak is typed in Roman letters, on this PC, as you talk. "
                                       "Fix a word once here and it's typed your way every time.")
        self.try_in = QLineEdit("मुझे आज ऑफिस जाना है")
        self.try_in.setAccessibleName("Try it: Hindi text")
        self.try_in.textChanged.connect(self._update_try)
        self.try_out = label("", "tryOut")
        arrow = QLabel()
        arrow.setPixmap(icon("arrow", MUTED).pixmap(20, 20))
        try_box = QFrame(objectName="card")
        lay = QVBoxLayout(try_box)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(label("TRY IT", "section"))
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.try_in, 1)
        row.addWidget(arrow)
        row.addWidget(self.try_out, 1)
        lay.addLayout(row)
        col.addWidget(try_box)

        words = QFrame(objectName="card")
        wl = QVBoxLayout(words)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        self.words_title = QLabel()
        self.words_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.search = QLineEdit(placeholderText="Search")
        self.search.setAccessibleName("Search words")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._fill_words)
        wl.addWidget(hbox(self.words_title, None, self.search, margins=(18, 12, 18, 12)))
        wl.addWidget(QFrame(objectName="divider"))
        head = hbox(label("HINDI", "section"), label("TYPED AS", "section"), margins=(18, 8, 70, 8), spacing=0)
        head.layout().setStretch(0, 1)
        head.layout().setStretch(1, 1)
        wl.addWidget(head)
        self.word_rows = QVBoxLayout()
        self.word_rows.setSpacing(0)
        holder = QWidget()
        holder.setLayout(self.word_rows)
        wl.addWidget(holder)
        wl.addWidget(QFrame(objectName="divider"))
        self.new_hi = QLineEdit(placeholderText="हिंदी शब्द")
        self.new_hi.setAccessibleName("Hindi word")
        self.new_en = QLineEdit(placeholderText="typed as")
        self.new_en.setAccessibleName("Typed as")
        self.add_word = QPushButton("Add word", objectName="primary")
        self.add_word.clicked.connect(self._add_word)
        self.new_en.returnPressed.connect(self._add_word)
        for field in (self.new_hi, self.new_en):
            field.textChanged.connect(lambda _: self.add_word.setEnabled(bool(self.new_hi.text().strip() and self.new_en.text().strip())))
        self.add_word.setEnabled(False)
        add = hbox(self.new_hi, self.new_en, self.add_word, margins=(18, 12, 18, 12), spacing=10)
        add.setStyleSheet("background: #FAFAF9; border-bottom-left-radius: 10px; border-bottom-right-radius: 10px;")
        wl.addWidget(add)
        col.addWidget(words)
        col.addStretch(1)
        self._fill_words()
        self._update_try()
        return scroll

    def _update_try(self):
        self.try_out.setText(hinglish(self.try_in.text(), self.settings["words"]))

    def _fill_words(self):
        while self.word_rows.count():
            old = self.word_rows.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        words = self.settings["words"]
        q = self.search.text().strip().lower()
        self.words_title.setText(f'Your words <span style="font-weight:500;color:{MUTED}">· {len(words)}</span>')
        shown = [(hi, en) for hi, en in words.items() if not q or q in hi or q in en.lower()]
        for hi, en in sorted(shown, key=lambda w: w[1].lower()):
            row = QWidget(objectName="wordRow")
            grid = QGridLayout(row)
            grid.setContentsMargins(18, 2, 18, 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            hi_label, en_label = QLabel(hi), QLabel(en)
            hi_label.setStyleSheet("font-size: 16px;")
            en_label.setStyleSheet("font-size: 14px; font-weight: 500;")
            remove = QPushButton(objectName="icon")
            remove.setIcon(icon("trash", MUTED, 16))
            remove.setAccessibleName(f"Remove {hi}")
            remove.setToolTip("Remove")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _, h=hi: self._remove_word(h))
            grid.addWidget(hi_label, 0, 0)
            grid.addWidget(en_label, 0, 1)
            grid.addWidget(remove, 0, 2)
            row.setMinimumHeight(44)
            row.setStyleSheet("QWidget#wordRow { border-bottom: 1px solid #F5F5F4; }")
            self.word_rows.addWidget(row)
        if not shown:
            self.word_rows.addWidget(hbox(label("No words match." if q else "No words yet.", "muted"), margins=(18, 12, 18, 12)))

    def _add_word(self):
        hi, en = normalize(self.new_hi.text().strip()), self.new_en.text().strip()
        if not hi or not en:
            return
        self.settings.set("words", {**self.settings["words"], hi: en})
        self.new_hi.clear()
        self.new_en.clear()
        self.new_hi.setFocus()

    def _remove_word(self, hi):
        self.settings.set("words", {k: v for k, v in self.settings["words"].items() if k != hi})

    # History

    def _page_history(self):
        scroll, col = page("History", "Your last 30 dictations, kept only on this PC.")
        self.clear_history = QPushButton("Clear history")
        self.clear_history.clicked.connect(self.history.clear)
        col.addWidget(hbox(None, self.clear_history))
        self.history_card = QFrame(objectName="card")
        self.history_rows = QVBoxLayout(self.history_card)
        self.history_rows.setContentsMargins(0, 0, 0, 0)
        self.history_rows.setSpacing(0)
        col.addWidget(self.history_card)
        col.addStretch(1)
        self._fill_history()
        return scroll

    def _fill_history(self):
        while self.history_rows.count():
            old = self.history_rows.takeAt(0).widget()
            old.hide()  # deleteLater waits for the event loop; until then the old row would still paint
            old.deleteLater()
        entries = self.history.entries
        self.clear_history.setEnabled(bool(entries))
        if not entries:
            key = self.settings["talk_key"]["name"]
            self.history_rows.addWidget(hbox(label(f"No dictations yet. Hold {key} and speak.", "muted"), margins=(18, 18, 18, 18)))
        for i, entry in enumerate(entries):
            if i:
                self.history_rows.addWidget(QFrame(objectName="divider"))
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(when(entry["time"]), "muted"))
            body = label(entry["text"], "rowTitle", wrap=True)
            body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.addWidget(body)
            copy = QPushButton(objectName="icon")
            copy.setIcon(icon("copy", MUTED, 18))
            copy.setAccessibleName("Copy")
            copy.setToolTip("Copy")
            copy.setCursor(Qt.CursorShape.PointingHandCursor)
            copy.clicked.connect(lambda _, t=entry["text"]: self.ctl.copy(t))
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(18, 10, 10, 10)
            lay.addLayout(text, 1)
            if entry.get("source"):
                fix = QPushButton(objectName="icon")
                fix.setIcon(icon("edit", MUTED, 18))
                fix.setAccessibleName("Fix spelling")
                fix.setToolTip("Fix spelling")
                fix.setCursor(Qt.CursorShape.PointingHandCursor)
                fix.clicked.connect(lambda _, e=entry: self.fix_spelling(e))
                lay.addWidget(fix, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(copy, 0, Qt.AlignmentFlag.AlignTop)
            self.history_rows.addWidget(row)

    def fix_spelling(self, entry):
        """Each Hindi word of a dictation with how it was typed; a changed spelling joins the word list."""
        dialog = QDialog(self, objectName="window")
        dialog.setWindowTitle("Fix spelling")
        dialog.setMinimumWidth(520)
        col = QVBoxLayout(dialog)
        col.setContentsMargins(28, 24, 28, 22)
        col.setSpacing(12)
        col.addWidget(label("Fix spelling", "h1"))
        col.addWidget(label("Type a word the way you want it. Bolo remembers it for next time.", "lead", wrap=True))
        box = QFrame(objectName="card")
        grid = QGridLayout(box)
        grid.setContentsMargins(18, 12, 18, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.addWidget(label("HINDI", "section"), 0, 0)
        grid.addWidget(label("TYPED AS", "section"), 0, 1)
        fields = []
        for i, (hi, typed) in enumerate(spellings(entry["source"], self.settings["words"]), 1):
            word = QLabel(hi)
            word.setStyleSheet("font-size: 16px;")
            field = QLineEdit(typed)
            field.setAccessibleName(f"How to type {hi}")
            grid.addWidget(word, i, 0)
            grid.addWidget(field, i, 1)
            fields.append((hi, typed, field))
        grid.setColumnStretch(1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(box)
        scroll.setMaximumHeight(420)
        col.addWidget(scroll)
        cancel, save = QPushButton("Cancel"), QPushButton("Save", objectName="primary")
        cancel.clicked.connect(dialog.reject)
        save.clicked.connect(dialog.accept)
        save.setDefault(True)
        col.addWidget(hbox(None, cancel, save))
        if fields:
            fields[0][2].setFocus()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changes = {hi: field.text().strip() for hi, typed, field in fields if field.text().strip() not in ("", typed)}
        if changes:
            self.settings.set("words", {**self.settings["words"], **changes})
            self.history.retext(entry, hinglish(entry["source"], self.settings["words"]))

    # Claude session

    def _page_session(self):
        scroll, col = page("Claude session", "Bolo runs Claude Code hidden in the background and uses its voice dictation. "
                                             "Nothing you say is sent to Claude as a message.")
        self.session_status = QLabel()
        self.session_status.setStyleSheet("font-size: 14px; font-weight: 600;")
        restart = QPushButton("Restart")
        restart.clicked.connect(self.ctl.restart_session)
        open_log = QPushButton("Open log")
        open_log.clicked.connect(self.ctl.open_log)
        col.addWidget(card(Row("Status", "", self.session_status),
                           Row("Claude Code", self.ctl.claude_path()),
                           Row("Restart the session", "Use this if dictation stops responding.", restart),
                           Row("Log", str(LOG), open_log)))
        col.addStretch(1)
        return scroll

    # About

    def _page_about(self):
        scroll, col = page("About")
        logo = QLabel()
        logo.setPixmap(logo_icon().pixmap(64, 64))
        name = QLabel(f'<span style="font-size:20px;font-weight:700">Bolo</span>'
                      f'&nbsp;&nbsp;<span style="color:{MUTED}">version {__version__}</span>')
        col.addWidget(hbox(logo, name, None, spacing=16))
        col.addWidget(label("Hold a key, speak, and your words type themselves, live, in English or Hinglish. "
                            "Runs on the Claude Code you already have: no API keys, no extra subscription.", "lead", wrap=True))
        source = QPushButton("Source code on GitHub", objectName="link")
        source.setStyleSheet(f"color: {ACCENT_TEXT};")
        source.setCursor(Qt.CursorShape.PointingHandCursor)
        source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        col.addWidget(hbox(source, None))
        col.addWidget(label("Unofficial: not made by, affiliated with or endorsed by Anthropic.", "muted", wrap=True))
        col.addStretch(1)
        return scroll
