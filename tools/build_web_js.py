"""Build the assets of the JavaScript web edition into web/assets/ (git-ignored; made for deploy).

    python tools/build_web_js.py

Copies the sprites, fonts and kanji stencils the browser needs, and converts the sounds: 16-bit mono, 22.05 kHz,
resampled with a proper low-pass (an FFT cut at 10 kHz) so nothing above the new Nyquist frequency folds back as
hiss. That cuts the sounds from 43 MB to about 9 MB. Writes web/assets/audio/manifest.json, the list of sound files
per group, which web/src/audio.js loads.

Test it locally:  python -m http.server 8000 -d web   then open http://localhost:8000
"""
import json
import re
import shutil
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets"
OUT = ROOT / "web" / "assets"

# file prefix -> game sound name: the same table as ninja/audio.py
GROUPS = {"slash": "swoosh", "splat": "splat", "explode": "explode", "fuse": "fuse", "combo": "combo",
          "power": "power", "gong": "gong", "ui": "throw", "miss": "miss", "music": "music",
          "timestop": "timestop", "clones": "clones", "dragonfire": "dragonfire", "bosshit": "boss_hit",
          "bossroar": "boss_roar", "fever": "fever", "shuriken": "shuriken"}
SKIP = {"music_2.wav", "fever_2.wav", "fuse_2.wav"}  # second takes of the long loops: ~2 MB less to download
CUTOFF_HZ = 10000
TARGET_RATE = 22050


def to_mono_22k(src, dst):
    """16-bit WAV -> mono 22.05 kHz 16-bit WAV, low-passed in the frequency domain before the rate is halved."""
    with wave.open(str(src)) as w:
        ch, rate, width, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64)
    assert width == 2, f"{src.name}: expected 16-bit audio"
    mono = data.reshape(-1, ch).mean(axis=1)
    if rate != TARGET_RATE:
        assert rate == 2 * TARGET_RATE, f"{src.name}: expected 44.1 kHz, got {rate}"
        mono = mono[: len(mono) // 2 * 2]  # an even length halves exactly
        spec = np.fft.rfft(mono)
        keep = int(CUTOFF_HZ / (rate / 2) * (len(spec) - 1))  # bins up to the cutoff
        spec = spec[: len(mono) // 4 + 1].copy()  # the new Nyquist
        spec[keep:] = 0
        mono = np.fft.irfft(spec, n=len(mono) // 2) * 0.5  # irfft divides by the new length, rfft did not by the old
    out = np.clip(np.round(mono), -32768, 32767).astype("<i2")
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes(out.tobytes())


def size_of(folder):
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("sprites", "glyphs"):  # never assets/raw: the source art is git-ignored and never ships
        shutil.copytree(SRC / sub, OUT / sub)
    (OUT / "fonts").mkdir(parents=True)
    for f in (SRC / "fonts").iterdir():
        shutil.copy2(f, OUT / "fonts" / f.name)
    shutil.copy2(SRC / "sprites" / "watermelon.png", ROOT / "web" / "favicon.png")
    audio = OUT / "audio"
    audio.mkdir()
    groups = {}
    for f in sorted((SRC / "audio").glob("*.wav")):
        m = re.match(r"([a-z]+)\d*_\d+\.wav$", f.name)
        if f.name in SKIP or not m or m.group(1) not in GROUPS:
            continue
        to_mono_22k(f, audio / f.name)
        groups.setdefault(GROUPS[m.group(1)], []).append(f.name)
    (audio / "manifest.json").write_text(json.dumps({"groups": groups}, indent=1), encoding="utf-8")
    print(f"audio {size_of(SRC / 'audio') / 1e6:.1f} MB -> {size_of(audio) / 1e6:.1f} MB ({sum(map(len, groups.values()))} files)")
    print(f"web/assets {size_of(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
