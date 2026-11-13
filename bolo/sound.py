"""Start and stop cues: two short soft tones, generated once as WAV files (nothing to ship)."""
import math
import struct
import wave
import winsound

from .util import LOCAL, log

TONES = {"start": (660, 880), "stop": (880, 660)}  # rising when listening starts, falling when it stops


def _write_tone(path, freqs, ms=70, rate=22050, volume=0.22):
    frames = bytearray()
    for freq in freqs:
        n = int(rate * ms / 1000)
        for i in range(n):
            envelope = min(1.0, i / (rate * 0.005), (n - i) / (rate * 0.02))  # no clicks at either end
            frames += struct.pack("<h", int(32767 * volume * envelope * math.sin(2 * math.pi * freq * i / rate)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def play(name):
    path = LOCAL / "sounds" / f"{name}.wav"
    try:
        if not path.exists():
            _write_tone(path, TONES[name])
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except (OSError, RuntimeError) as e:
        log(f"could not play the {name} sound: {e}")
