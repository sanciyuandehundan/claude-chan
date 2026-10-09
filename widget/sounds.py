"""合成几段 8-bit 风格的短音效，存成 assets/*.wav（缺了就重新生成）。"""
from __future__ import annotations

import math
import os
import pathlib
import random
import struct
import wave

RATE = 22050
ASSETS = pathlib.Path(os.environ.get("CLAWD_WIDGET_DATA") or (pathlib.Path.home() / ".claude" / "clawd-widget")) / "assets"


def _square(phase: float, duty: float = 0.5) -> float:
    return 1.0 if (phase % 1.0) < duty else -1.0


def _tri(phase: float) -> float:
    p = phase % 1.0
    return 4 * p - 1 if p < 0.5 else 3 - 4 * p


def _tone(freqs, dur, wave_fn=_square, vol=0.22, attack=0.004, decay=6.0, vibrato=0.0):
    """freqs 是 (t 0..1) -> Hz 的函数，按相位累加以免变频时爆音。"""
    n = int(RATE * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / n
        f = freqs(t)
        if vibrato:
            f *= 1 + vibrato * math.sin(2 * math.pi * 9 * i / RATE)
        phase += f / RATE
        env = min(1.0, (i / RATE) / attack) * math.exp(-decay * t)
        out.append(wave_fn(phase) * env * vol)
    return out


def _seq(*parts):
    out = []
    for p in parts:
        out += p
    return out


def _echo(samples, delay=0.07, gain=0.35):
    d = int(RATE * delay)
    out = samples + [0.0] * d
    for i, s in enumerate(samples):
        out[i + d] += s * gain
    return out


def _write(name: str, samples) -> None:
    ASSETS.mkdir(exist_ok=True)
    with wave.open(str(ASSETS / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))


def build() -> None:
    random.seed(7)
    _write("pop.wav", _tone(lambda t: 520 + 700 * t, 0.14, lambda p: _square(p, 0.25), vol=0.34, decay=3.5))
    _write("coin.wav", _seq(
        _tone(lambda t: 988, 0.06, vol=0.32, decay=1),
        _tone(lambda t: 1319, 0.26, vol=0.32, decay=4.5),
    ))
    _write("sparkle.wav", _echo(_seq(*[
        _tone(lambda t, f=f: f, 0.06, _tri, vol=0.45, decay=2) for f in (1047, 1319, 1568, 2093)
    ])))
    _write("boing.wav", _tone(lambda t: 260 + 340 * abs(math.sin(t * math.pi * 2.2)) * (1 - t), 0.34, _tri, vol=0.5, decay=3))
    _write("squeak.wav", _seq(
        _tone(lambda t: 1700 + 900 * t, 0.05, lambda p: _square(p, 0.3), vol=0.26, decay=2),
        [0.0] * int(RATE * 0.03),
        _tone(lambda t: 1900 + 1100 * t, 0.07, lambda p: _square(p, 0.3), vol=0.26, decay=2),
    ))
    _write("huh.wav", _seq(
        _tone(lambda t: 660, 0.12, vol=0.3, vibrato=0.03, decay=1.5),
        _tone(lambda t: 440 - 60 * t, 0.2, vol=0.3, vibrato=0.04, decay=3),
    ))
    _write("warn.wav", _seq(
        _tone(lambda t: 880, 0.08, lambda p: _square(p, 0.25), vol=0.26, decay=1),
        [0.0] * int(RATE * 0.05),
        _tone(lambda t: 880, 0.08, lambda p: _square(p, 0.25), vol=0.26, decay=1),
    ))


CLICK = ["pop.wav", "coin.wav", "sparkle.wav", "boing.wav", "squeak.wav"]
ANNOYED = "huh.wav"
WARN = "warn.wav"


def ensure() -> None:
    need = CLICK + [ANNOYED, WARN]
    if not all((ASSETS / n).exists() for n in need):
        build()


if __name__ == "__main__":
    build()
    print(sorted(p.name for p in ASSETS.glob("*.wav")))
