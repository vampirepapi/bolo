# Bolo

**Hold a key, speak, and your words type themselves — live, in English or Hinglish.**

Bolo ("speak" in Hindi) is a Windows tray app that turns Claude Code's built-in voice dictation
into system-wide voice typing. Hold **Right Ctrl** anywhere, talk, and the text streams into the app
you're in as you speak. Hindi comes out as Hinglish (`abhi main hindi mein bol raha hoon`), not Devanagari.

No API keys and no extra subscription: it runs on the Claude Code login you already have.

## Requirements

- Windows 10/11
- [Claude Code](https://code.claude.com) installed and signed in, with `/voice` working (run `claude`, type `/voice`, hold Space)
- Python 3.11+ (only to run from source)

## Run

Download `Bolo.exe` from [Releases](https://github.com/vampirepapi/bolo/releases) and run it. Windows SmartScreen
may warn because the exe isn't code-signed: choose **More info → Run anyway**.

Or from source:

```sh
pip install -r requirements.txt
pythonw app.py            # tray app, no console window (Settings opens on first launch)
python app.py --selftest  # mic-free checks: settings, history, hook logic, capsule, the hidden session
```

| Do this | What happens |
|---|---|
| Hold the talk key (**Right Ctrl**), speak | text streams into the focused app; a capsule shows it's listening |
| Let go | Claude's final transcript replaces the live text |
| **Esc** while talking | cancels and erases what was typed |
| Any other key while talking | stops the dictation; the key goes to your app |
| Tray icon | latest dictations (click to copy), pause, settings, restart, quit |

## Settings

- **General**: talk key (any key that doesn't type: Right Ctrl, Right Alt, Caps Lock, F1–F24…),
  hold-to-talk or tap on/tap off, text as you speak or when you let go, Hinglish on/off, dictation
  language, capsule, sounds, start with Windows.
- **Hinglish**: a live "try it" box and your own word list — fix a spelling once (ऑफिस → office)
  and it's typed your way every time.
- **History**: the last 30 dictations, kept only on this PC, with copy and clear. On a Hinglish dictation,
  **Fix spelling** (✎) lists its Hindi words; correct one and Bolo types it your way from then on.
- **Claude session**: status, restart, the log.

The talk key is reserved for dictation while Bolo runs (pause it from the tray to use it normally).

## How it works

1. Bolo runs `claude` in a hidden pseudo console (ConPTY) with voice on in hold mode.
2. While you talk, it sends Claude Code's push-to-talk key (Space) every 50 ms.
3. It mirrors the hidden terminal into a virtual screen (`pyte`) and types the live prompt text
   into your app, correcting with backspaces as Claude revises.
4. When you stop, Ctrl+G hands Claude's prompt to `$EDITOR` (a tiny script) for the final text;
   nothing is ever sent to Claude as a message.
5. Devanagari is transliterated to Hinglish locally by rule, plus your word list, so it's instant.

```
bolo/
  session.py     hidden Claude Code session, virtual screen, Ctrl+G capture
  keys.py        keyboard hook (talk key, Esc, pause, key recording) and typing via SendInput
  controller.py  the dictation state machine
  hinglish.py    Devanagari -> Hinglish
  settings.py    settings.json with safe defaults        history.py   last 30 dictations
  sound.py       start/stop cues                          autostart.py start with Windows
  ui/            capsule, tray menu, Settings window, theme and widgets
```

Data lives in `%LOCALAPPDATA%\Bolo\` (`settings.json`, `history.json`, `log.txt`). The log never
contains what you said.

> Unofficial: not made by, affiliated with or endorsed by Anthropic.
