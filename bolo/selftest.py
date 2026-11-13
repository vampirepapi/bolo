"""Mic-free checks: python app.py --selftest. Unit checks first, then the hidden Claude session end to end.
BOLO_SELFTEST_LANGUAGE=hindi runs the session part with that dictation language."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pyte
from PyQt6.QtCore import QObject, Qt

from .hinglish import hinglish
from .history import MAX_ENTRIES, History
from .keys import TALK_KEYS, VK_ESCAPE, Hotkey, user32
from .session import Session
from .settings import Settings
from .ui.capsule import Capsule
from .util import after


def unit_checks(qapp):
    tmp = Path(tempfile.mkdtemp(prefix="bolo-selftest-"))
    # Settings: defaults match the first release, changes persist, junk falls back to defaults.
    s = Settings(tmp / "s.json")
    assert (s["mode"], s["output"], s["hinglish"], s["talk_key"]["vk"]) == ("hold", "live", True, 0xA3)
    s.set("mode", "tap")
    s.set("words", {**s["words"], "ऑफिस": "office"})
    again = Settings(tmp / "s.json")
    assert again["mode"] == "tap" and again["words"]["ऑफिस"] == "office"
    (tmp / "bad.json").write_text("{not json", encoding="utf-8")
    assert Settings(tmp / "bad.json")["mode"] == "hold"
    (tmp / "odd.json").write_text(json.dumps({"mode": "sideways", "sounds": "yes", "talk_key": {"vk": "x"}}), encoding="utf-8")
    odd = Settings(tmp / "odd.json")
    assert odd["mode"] == "hold" and odd["sounds"] is False and odd["talk_key"]["vk"] == 0xA3
    (tmp / "letter.json").write_text(json.dumps({"talk_key": {"vk": 0x41, "name": "A"}}), encoding="utf-8")
    assert Settings(tmp / "letter.json")["talk_key"]["vk"] == 0xA3  # a typing key never becomes the talk key
    # History: newest first, capped, persisted, clearable.
    h = History(tmp / "h.json")
    for i in range(MAX_ENTRIES + 5):
        h.add(f"note {i}")
    h = History(tmp / "h.json")
    assert len(h.entries) == MAX_ENTRIES and h.entries[0]["text"] == f"note {MAX_ENTRIES + 4}"
    h.clear()
    assert History(tmp / "h.json").entries == []
    # The user's words win over the rules.
    assert hinglish("ऑफिस जाना", {"ऑफिस": "office"}) == "office jana"
    # English mixed into Hindi comes back in Devanagari; आई is "I" only before English.
    assert hinglish("क्या अभी ये वर्क कर रहा है? आई थिंक इट इज़ वर्किंग") == "kya abhi ye work kar raha hai? I think it is working"
    assert hinglish("वो आई थी") == "woh aai thi"
    assert hinglish("इज" + "़") == hinglish("ज़".join(["इ", ""])) == "is"  # ज़ as two codepoints or one
    # An existing list (seed 1) gains the new built-ins once, keeping the user's own changes.
    (tmp / "seed1.json").write_text(json.dumps({"words": {"वर्क": "werk", "में": "mein"}}), encoding="utf-8")
    seeded = Settings(tmp / "seed1.json")
    assert seeded["words"]["वर्क"] == "werk" and seeded["words"]["वर्किंग"] == "working" and seeded["words_seed"] == 2
    # A talk key is swallowed system-wide, so none may type text.
    assert not set(TALK_KEYS) & {0x20, 0x0D, 0x08, 0x09, VK_ESCAPE, 0x41, 0x30}
    # The hook's decisions, without installing the hook.
    hk = Hotkey.__new__(Hotkey)
    QObject.__init__(hk)
    hk.vk, hk.paused, hk.dictating, hk.recording, hk.down = 0xA3, False, False, False, False
    got = []
    hk.pressed.connect(lambda: got.append("press"))
    hk.released.connect(lambda: got.append("release"))
    hk.cancelled.connect(lambda erase: got.append(f"cancel {erase}"))
    hk.recorded.connect(lambda vk: got.append(vk))
    assert hk._key(0xA3, True) and hk._key(0xA3, True) and hk._key(0xA3, False)  # swallowed; auto-repeat ignored
    assert got == ["press", "release"]
    assert hk._key(0x41, True) is False and len(got) == 2  # not dictating: other keys pass untouched
    hk.dictating = True
    assert hk._key(VK_ESCAPE, True) is True and hk._key(0x41, True) is False
    assert got[-2:] == ["cancel True", "cancel False"]
    hk.dictating, hk.paused = False, True
    assert hk._key(0xA3, True) is False  # paused: the talk key is an ordinary key
    hk.paused, hk.recording = False, True
    assert hk._key(0x41, True) is True and got[-1] == 0x41 and not hk.recording
    # The capsule must never take focus: that would end live typing.
    before = user32.GetForegroundWindow()
    capsule = Capsule()
    for state in ("opening", "listening", "finishing", "message"):
        capsule.show_state(state, text="abhi main hindi mein", badge=True)
        qapp.processEvents()
    capsule.update_live("abhi main hindi mein bol raha hoon", [1, 3, 5, 7, 2])
    qapp.processEvents()
    assert user32.GetForegroundWindow() == before, "the capsule took focus"
    assert capsule.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    capsule.hide()
    shutil.rmtree(tmp, ignore_errors=True)
    print("PASS: settings, history, words, talk keys, hook logic, capsule focus", flush=True)


def selftest(qapp):
    unit_checks(qapp)
    session = Session(os.environ.get("BOLO_SELFTEST_LANGUAGE", ""))
    # prompt_text on a synthetic screen: a soft-wrapped full line, a padded line, level bars, placeholder.
    for raw, want in (("─" * 20 + "\r\n❯\xa0" + "a" * 18 + "\r\n  bb cc   \r\n  dd\r\n" + "─" * 20, "a" * 18 + "bb cc dd"),
                      ("❯\xa0▁▃▅\r\n" + "─" * 20, ""), ('❯\xa0Try "fix lint errors"\r\n' + "─" * 20, "")):
        session.vt = pyte.Screen(20, 6)
        pyte.Stream(session.vt).feed(raw)
        assert session.prompt_text() == want, (raw, session.prompt_text())
    assert session.levels() == [], session.levels()
    session.vt = pyte.Screen(20, 6)
    pyte.Stream(session.vt).feed("❯\xa0hi ▁▃▅\r\n" + "─" * 20)
    assert session.levels() == [1, 3, 5], session.levels()
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
            # Again after a capture: Ctrl+G's editor round trip (alternate screen) must not break live reading.
            after(1.5, lambda: (session.write(token2), after(1, read_again)))
        else:
            finish(1, f"FAIL: captured {text!r}, expected {token!r}; screen: {session.tail(500)}")

    token2 = "second-dictation-ok"

    def read_again():
        live = session.prompt_text()
        if live != token2:
            return finish(1, f"FAIL: after a capture the live prompt read {live!r}, expected {token2!r}")
        session.capture(got_again)

    def got_again(text):
        if text == token2:
            finish(0, "PASS: live read and capture work again after a capture; all checks")
        else:
            finish(1, f"FAIL: captured {text!r}, expected {token!r}; screen: {session.tail(500)}")

    after(90, lambda: finish(1, f"FAIL: overall timeout; screen: {session.tail(500)}"))
    session.start()
    check_ready()
    qapp.exec()
    session.stop()
    return result["code"]
