"""Generates the little robot chirps as plain 16-bit mono PCM WAVs (safe for Windows CE)."""
import math
import os
import struct
import wave

RATE = 22050
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")


def render(notes, vol=0.55):
    """notes: list of (f_start, f_end, seconds, vibrato_hz, vibrato_depth). f=0 is a rest."""
    samples = []
    phase = 0.0
    for f0, f1, dur, vhz, vdep in notes:
        n = int(RATE * dur)
        for i in range(n):
            t = i / float(n)
            if f0 == 0:
                samples.append(0.0)
                continue
            f = f0 + (f1 - f0) * t
            f *= 1.0 + vdep * math.sin(2 * math.pi * vhz * i / RATE)
            phase += 2 * math.pi * f / RATE
            # soft attack/release so there are no clicks
            env = min(1.0, i / (RATE * 0.008), (n - i) / (RATE * 0.03))
            # sine plus a quiet octave gives the "toy beep" timbre
            s = math.sin(phase) + 0.25 * math.sin(2 * phase)
            samples.append(s * env)
    peak = max(1e-9, max(abs(s) for s in samples))
    return [s / peak * vol for s in samples]


def save(name, notes, vol=0.55):
    os.makedirs(OUT, exist_ok=True)
    data = render(notes, vol)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in data))


R = (0, 0, 0.05, 0, 0)  # short rest

SOUNDS = {
    # tap with no mood change / generic boop
    "boop":      [(600, 900, 0.09, 0, 0), (900, 700, 0.07, 0, 0)],
    "normal":    [(520, 700, 0.08, 0, 0), R, (700, 880, 0.10, 0, 0)],
    # bright rising chirps: "yay"
    "happy":     [(700, 1100, 0.08, 0, 0), (900, 1400, 0.08, 0, 0), (1100, 1700, 0.12, 14, 0.02)],
    "wink":      [(900, 1500, 0.05, 0, 0), R, (1600, 1000, 0.09, 0, 0)],
    # low grumbly
    "angry":     [(210, 160, 0.14, 32, 0.07), R, (230, 150, 0.18, 32, 0.07)],
    # slow falling whimper
    "sad":       [(700, 520, 0.18, 6, 0.02), (560, 340, 0.30, 6, 0.03)],
    # quick "oh!" pop
    "surprised": [(400, 1500, 0.07, 0, 0), (1500, 1500, 0.10, 18, 0.03)],
    # curious wobble
    "thinking":  [(600, 640, 0.10, 12, 0.04), (760, 700, 0.10, 12, 0.04), (900, 880, 0.16, 12, 0.05)],
    # long yawn sliding down
    "sleepy":    [(520, 460, 0.18, 4, 0.02), (440, 220, 0.45, 4, 0.03)],
    # Halloween: evil laugh for the devil, spooky-cute arpeggio for the pumpkin, a ghostly "boo"
    "devil":     [(230, 170, 0.11, 30, 0.06), (0, 0, 0.04, 0, 0), (210, 150, 0.11, 30, 0.06), (0, 0, 0.04, 0, 0),
                  (190, 130, 0.11, 30, 0.06), (0, 0, 0.04, 0, 0), (170, 90, 0.30, 24, 0.08)],
    "pumpkin":   [(440, 440, 0.09, 0, 0), (523, 523, 0.09, 0, 0), (659, 659, 0.09, 0, 0), (523, 523, 0.09, 0, 0),
                  (784, 784, 0.22, 10, 0.02)],
    "boo":       [(150, 150, 0.05, 0, 0), (160, 520, 0.32, 6, 0.04), (520, 380, 0.22, 6, 0.04)],
    # attention-getting two-tone "ding-dong", twice: used for reminders
    "alert":     [(880, 880, 0.16, 0, 0), (660, 660, 0.24, 0, 0), R, (880, 880, 0.16, 0, 0), (660, 660, 0.30, 0, 0)],
    # music-box style tune the face sings (about 2.4 s, sways in time with it)
    "song":      [(523, 523, 0.22, 0, 0), (659, 659, 0.22, 0, 0), (784, 784, 0.22, 0, 0), (659, 659, 0.22, 0, 0),
                  (784, 784, 0.22, 0, 0), (1047, 1047, 0.32, 0, 0), (988, 988, 0.22, 0, 0), (784, 784, 0.22, 0, 0),
                  (880, 880, 0.22, 0, 0), (1047, 1047, 0.45, 8, 0.02)],
    # ticklish giggle: quick up/down chirps that get faster at the end
    "giggle":    [(1100, 1600, 0.06, 0, 0), (1600, 1150, 0.06, 0, 0), R,
                  (1150, 1650, 0.06, 0, 0), (1650, 1200, 0.06, 0, 0), R,
                  (1200, 1700, 0.05, 0, 0), (1700, 1250, 0.05, 0, 0),
                  (1250, 1750, 0.05, 0, 0), (1750, 1300, 0.07, 0, 0)],
}

if __name__ == "__main__":
    for name, notes in SOUNDS.items():
        save(name, notes)
        print("wrote", name + ".wav")
