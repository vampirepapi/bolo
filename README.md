# Bolo

**Hold a key, speak, and your words type themselves — live, in English or Hinglish.**

Bolo ("speak" in Hindi) is a tiny Windows tray app that turns Claude Code's built-in voice dictation
into system-wide voice typing. Hold **Right Ctrl** anywhere, talk, and the text streams into the app
you're in as you speak. Hindi comes out as Hinglish (`abhi main hindi mein bol raha hoon`), not Devanagari.

No API keys and no extra subscription: it runs on the Claude Code login you already have.

## Requirements

- Windows 10/11
- [Claude Code](https://code.claude.com) installed and signed in, with `/voice` working (run `claude`, type `/voice`, hold Space)
- Python 3.11+

## Run

```sh
pip install -r requirements.txt
pythonw app.py            # tray app, no console window
python app.py --selftest  # checks the hidden session, live prompt reading and Hinglish, no mic needed
```

| Do this | What happens |
|---|---|
| Hold **Right Ctrl**, speak | text streams into the focused app as you talk |
| Let go | Claude's final transcript replaces the live text |
| **Esc** while holding | cancels and erases what was typed |
| Tray icon › Quit | stops the app and its hidden Claude session |

Right Ctrl is reserved for dictation; use Left Ctrl for shortcuts.

## How it works

1. Bolo runs `claude` in a hidden pseudo console (ConPTY) with voice on in hold mode.
2. While you hold the key, it sends Claude Code's push-to-talk key (Space) every 50 ms.
3. It mirrors the hidden terminal into a virtual screen (`pyte`) and types the live prompt text
   into your app, correcting with backspaces as Claude revises.
4. On release, Ctrl+G hands Claude's prompt to `$EDITOR` (a tiny script) for the final text;
   nothing is ever sent to Claude as a message.
5. Devanagari is transliterated to Hinglish locally by rule, so it's instant.

The log is at `%LOCALAPPDATA%\Bolo\log.txt`.

> Unofficial: not made by, affiliated with or endorsed by Anthropic.
