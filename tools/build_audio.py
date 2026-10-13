"""Turn assets/raw/audio (mp3, git-ignored) into game-ready WAVs in assets/audio.

Dev-time only (needs numpy, which the game itself does not).  Run from the repo root:
    python tools/build_audio.py
pygame cannot write OGG, so everything is 16-bit stereo 44.1 kHz WAV.
"""
import json
import os
import sys
import wave

import numpy as np

# pygame is only used here to decode the mp3 files; the 'dummy' driver lets it run without a sound card.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Tuning knobs for chopping the raw recordings. Levels are in dB: 0 dB is full volume, -40 dB is nearly silent.
SR = 44100
GAP_DB = -40.0        # below this level counts as silence
MIN_GAP = 0.120       # s of silence that separates two hits
MIN_HIT = 0.060       # s; shorter fragments are dropped
FADE = 0.005          # s
PEAK_DB = -1.0
WHOLE = ("fuse", "music", "fever")  # looped files: keep whole, no splitting
WIN = int(0.005 * SR)      # 5 ms envelope window
# The source files sometimes hold long ambient runs or tiny clicks; keep each hit game-sized.
# name prefix -> (min seconds, max seconds); over-long hits get a 150 ms fade-out at the cap.
LIMITS = {"explode": (0.06, 4.0), "gong": (0.06, 6.0), "slash": (0.15, 1.2), "splat": (0.15, 1.0), "ui": (0.06, 1.0), "miss": (0.15, 2.0),
          "timestop": (0.25, 8.0), "clones": (0.25, 8.0), "dragonfire": (0.25, 8.0), "bossroar": (0.25, 8.0),
          "shuriken": (0.12, 3.0), "bosshit": (0.12, 4.0)}
MIN_RMS_DB = -32.0         # after normalising: a near-silent hit with one spike is a click, drop it
CAP_FADE = 0.150
LOOP_XFADE = {"fuse": 0.5, "music": 1.0, "fever": 1.0}  # s


def decode(path):
    """mp3 -> float32 (n, 2) in [-1, 1] at the mixer rate."""
    snd = pygame.mixer.Sound(path)
    rate, fmt, ch = pygame.mixer.get_init()
    # pygame hands us raw bytes: turn them into numbers, then scale 16-bit integers down to the range -1..1.
    a = np.frombuffer(snd.get_raw(), dtype=np.int16 if fmt == -16 else np.float32).astype(np.float32)
    if fmt == -16:
        a /= 32768.0
    a = a.reshape(-1, ch)
    # A mono sound is copied to both speakers so every sound has a left and a right channel.
    if ch == 1:
        a = np.repeat(a, 2, axis=1)
    return a[:, :2]


def split_hits(a):
    """Return (start, end) sample ranges of non-silent regions separated by >= MIN_GAP of silence."""
    n = len(a) // WIN
    if n == 0:
        return []
    # Loudness is measured in tiny 5 ms slices: each slice's level is its loudest sample.
    env = np.abs(a[: n * WIN]).max(axis=1).reshape(n, WIN).max(axis=1)
    loud = env > 10 ** (GAP_DB / 20)
    gap_w = int(round(MIN_GAP * SR / WIN))
    # Walk through the slices. A hit starts at the first loud slice and ends once MIN_GAP of quiet has passed.
    hits, start, quiet = [], None, 0
    for i, v in enumerate(loud):
        if v:
            if start is None:
                start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet >= gap_w:
                hits.append((start * WIN, (i - quiet + 1) * WIN))
                start, quiet = None, 0
    if start is not None:
        hits.append((start * WIN, n * WIN))
    return [(s, e) for s, e in hits if (e - s) / SR >= MIN_HIT]


def make_loop(a, overlap):
    """Equal-power crossfade of the tail into the head so the file wraps without a click or hole."""
    k = int(overlap * SR)
    t = np.linspace(0, np.pi / 2, k, dtype=np.float32)[:, None]
    # Drop the last k samples and blend them into the first k, so the end flows smoothly back into the start when looped.
    out = a[:-k].copy()
    out[:k] = a[-k:] * np.cos(t) + a[:k] * np.sin(t)
    return out


def finish(a, fade=True):
    """Fade both ends (no clicks), then scale the sound so its loudest point sits at PEAK_DB."""
    a = a.copy()
    if fade:
        k = min(int(FADE * SR), len(a) // 2)
        ramp = np.linspace(0, 1, k, dtype=np.float32)[:, None]
        a[:k] *= ramp
        a[len(a) - k:] *= ramp[::-1]
    peak = float(np.abs(a).max())
    return a * (10 ** (PEAK_DB / 20) / peak) if peak > 0 else a


def limit_hit(name, a):
    """Apply per-name min/max length; returns None when the hit should be dropped."""
    # Find the length limits whose name prefix matches (e.g. 'slash'); other sounds only get a minimum length.
    lo, hi = next((v for k, v in LIMITS.items() if name.startswith(k)), (MIN_HIT, None))
    if len(a) / SR < lo:
        return None
    if hi and len(a) / SR > hi:
        a = a[: int(hi * SR)].copy()
        k = int(CAP_FADE * SR)
        a[-k:] *= np.linspace(1, 0, k, dtype=np.float32)[:, None]
    a = finish(a)
    # If the whole hit is still too quiet it was probably just a click, so drop it.
    return a if stats(a)[2] >= MIN_RMS_DB else None


def write_wav(path, a):
    """Save a float array (-1..1) as a 16-bit stereo WAV file."""
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def stats(a):
    """Return (length in seconds, peak level in dB, RMS level in dB). RMS is the sound's average loudness."""
    peak = float(np.abs(a).max())
    rms = float(np.sqrt((a ** 2).mean()))
    db = lambda x: 20 * np.log10(max(x, 1e-9))
    return len(a) / SR, db(peak), db(rms)


def main():
    """Decode every source mp3, chop it into hits (or loop it), and write the WAV files."""
    # Ask for 44.1 kHz, 16-bit, stereo. The assert below makes sure the mixer really gave us that rate.
    pygame.mixer.init(SR, -16, 2, 512)
    assert pygame.mixer.get_init()[0] == SR, "mixer did not give 44.1 kHz"
    with open(os.path.join(ROOT, "assets/raw/audio/manifest.json")) as f:
        manifest = json.load(f)
    out = os.path.join(ROOT, "assets/audio")
    os.makedirs(out, exist_ok=True)
    # Start clean so sounds that were removed or renamed don't linger from an earlier run.
    for old in os.listdir(out):
        if old.endswith(".wav"):
            os.remove(os.path.join(out, old))
    print(f"{'file':16}{'src s':>7}{'hits':>5}{'dur s':>8}{'peak dB':>9}{'rms dB':>8}")
    for name, paths in manifest.items():
        n = 0
        stem = name.replace("_", "")  # audio.py parses <letters><digits>_<n>.wav, so boss_hit -> bosshit_1.wav
        for p in paths:
            a = decode(os.path.join(ROOT, p))
            # Long loops are kept whole (with a crossfade); every other file is chopped into separate hits.
            if name in WHOLE:
                parts = [finish(make_loop(a, LOOP_XFADE[name]), fade=False)]
            else:
                parts = [limit_hit(name, a[s:e]) for s, e in split_hits(a)]
                parts = [x for x in parts if x is not None]
            for part in parts:
                n += 1
                write_wav(os.path.join(out, f"{stem}_{n}.wav"), part)
                d, pk, rms = stats(part)
                print(f"{stem + '_' + str(n):16}{len(a) / SR:7.2f}{len(parts):5d}{d:8.2f}{pk:9.1f}{rms:8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
