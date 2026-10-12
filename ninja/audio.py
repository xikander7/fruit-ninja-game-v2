"""Sounds come from assets/audio (built by tools/build_audio.py); anything missing is synthesized in pure Python."""
import array
import math
import os
import random
import re

import pygame

SR = 22050
IN_SCALE = [0, 1, 5, 7, 8]  # Japanese "in" (miyako-bushi) scale, semitones over the root


def _midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _svf(samples, cutoffs, q=0.7, mode="band"):
    """Chamberlin state-variable filter with a per-sample cutoff."""
    low = band = 0.0
    out = []
    for x, fc in zip(samples, cutoffs):
        f = 2 * math.sin(math.pi * min(fc, SR / 6) / SR)
        low += f * band
        high = x - low - q * band
        band += f * high
        out.append(band if mode == "band" else low if mode == "low" else high)
    return out


def _sweep(n, a, b):
    return [a * (b / a) ** (i / max(1, n - 1)) for i in range(n)]


def _noise(n, rng):
    return [rng.uniform(-1, 1) for _ in range(n)]


def _sine_drop(n, f0, f1, decay):
    out, ph = [], 0.0
    for i in range(n):
        f = f0 * (f1 / f0) ** (i / n)
        ph += math.tau * f / SR
        out.append(math.sin(ph) * math.exp(-i / (decay * SR)))
    return out


def _mix(*tracks):
    n = max(len(t) for t, _ in tracks)
    out = [0.0] * n
    for t, g in tracks:
        for i, v in enumerate(t):
            out[i] += v * g
    return out


def pluck(freq, dur, rng, bright=0.5):
    """Karplus-Strong string — reads like a koto."""
    period = max(2, int(SR / freq))
    buf = _svf(_noise(period, rng), [freq * (2 + bright * 8)] * period, 0.5, "low")
    n = int(dur * SR)
    out = [0.0] * n
    damp = 0.996
    for i in range(n):
        j = i % period
        v = buf[j]
        out[i] = v
        buf[j] = damp * 0.5 * (v + buf[(j + 1) % period])
    return out


def taiko(rng, dur=0.5, f0=120, f1=52):
    n = int(dur * SR)
    body = _sine_drop(n, f0, f1, dur * 0.35)
    k = int(0.04 * SR)
    hit = [x * math.exp(-i / (0.008 * SR)) for i, x in enumerate(_svf(_noise(k, rng), [900] * k, 0.6, "low"))]
    return _mix((body, 1.0), (hit, 1.4))


def swoosh(rng, dur=0.17, f0=2400, f1=500):
    n = int(dur * SR)
    s = _svf(_noise(n, rng), _sweep(n, f0, f1), 0.35)
    return [x * math.sin(math.pi * i / n) ** 1.5 for i, x in enumerate(s)]


def splat(rng):
    n = int(0.22 * SR)
    goo = _svf(_noise(n, rng), _sweep(n, 1400, 180), 0.5, "low")
    goo = [x * math.exp(-i / (0.05 * SR)) for i, x in enumerate(goo)]
    squelch = _sine_drop(n, rng.uniform(260, 340), 90, 0.06)
    crack = [x * math.exp(-i / (0.004 * SR)) for i, x in enumerate(_noise(n, rng))]
    return _mix((goo, 1.0), (squelch, 0.6), (crack, 0.35))


def explosion(rng):
    n = int(1.5 * SR)
    rumble = _svf(_noise(n, rng), _sweep(n, 900, 60), 0.6, "low")
    rumble = [x * math.exp(-i / (0.35 * SR)) for i, x in enumerate(rumble)]
    thump = _sine_drop(n, 80, 30, 0.25)
    crack = [x * math.exp(-i / (0.02 * SR)) for i, x in enumerate(_noise(n, rng))]
    return _mix((rumble, 1.2), (thump, 0.9), (crack, 0.6))


def fuse(rng):
    n = int(1.0 * SR)
    hiss = _svf(_noise(n, rng), [5000] * n, 0.8, "high")
    out = [x * 0.25 for x in hiss]
    for _ in range(26):  # crackle pops
        p = rng.randrange(n - 200)
        for i in range(120):
            out[p + i] += rng.uniform(-1, 1) * math.exp(-i / 25)
    return out


def tick(rng):
    n = int(0.08 * SR)
    return [(math.sin(math.tau * 1150 * i / SR) + 0.5 * math.sin(math.tau * 1730 * i / SR)) * math.exp(-i / (0.012 * SR)) for i in range(n)]


def arpeggio(rng, notes, gap, dur=0.9):
    out = [0.0] * int((gap * len(notes) + dur) * SR)
    for k, m in enumerate(notes):
        p = pluck(_midi(m), dur, rng, 0.8)
        o = int(k * gap * SR)
        for i, v in enumerate(p):
            out[o + i] += v
    return out


def music(rng):
    """24 s koto + taiko loop in the in-scale on D."""
    bpm, steps = 80, 64
    step = 60 / bpm / 2
    total = int(steps * step * SR)
    out = [0.0] * total
    root = 62

    def add(sig, at, g):
        o = int(at * SR)
        for i, v in enumerate(sig):
            out[(o + i) % total] += v * g  # wrap the tail so the loop is seamless

    def deg(d):
        return root + 12 * (d // 5) + IN_SCALE[d % 5]

    motif, d = [], 5
    for _ in range(16):  # a 2-bar phrase, repeated with variation
        if rng.random() < 0.42:
            motif.append(None)
        else:
            d = max(2, min(11, d + rng.choice((-2, -1, -1, 1, 1, 2))))
            motif.append(d)
    for k in range(steps):
        m = motif[k % 16]
        if k >= 32 and m is not None and rng.random() < 0.3:
            m = max(2, min(11, m + rng.choice((-1, 1))))
        if m is not None:
            add(pluck(_midi(deg(m)), 1.4, rng, 0.45), k * step, 0.5)
    for bar in range(8):
        bass = [0, 0, 3, 0, 0, 0, 3, 2][bar]
        add(pluck(_midi(deg(bass) - 24), 2.6, rng, 0.2), bar * 8 * step, 0.55)
        add(taiko(rng, 0.6), bar * 8 * step, 0.5)
        add(taiko(rng, 0.3, 160, 80), (bar * 8 + 5) * step, 0.18)
        if bar % 4 == 3:
            add(taiko(rng, 0.4), (bar * 8 + 6) * step, 0.35)
            add(taiko(rng, 0.4), (bar * 8 + 7) * step, 0.42)
    return out


AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audio")
# file prefix -> game sound name (ui clicks double as the quiet "throw" whoosh)
GROUPS = {"slash": "swoosh", "splat": "splat", "explode": "explode", "fuse": "fuse", "combo": "combo",
          "power": "power", "gong": "gong", "ui": "throw", "miss": "miss", "music": "music",
          "timestop": "timestop", "clones": "clones", "dragonfire": "dragonfire", "bosshit": "boss_hit",
          "bossroar": "boss_roar", "fever": "fever", "shuriken": "shuriken"}
ALIASES = {"stamp": "combo", "life": "power"}  # names that reuse another group's files
# Per-name level. Files are peak-normalised to -1 dBFS with RMS between about -14 and -25 dBFS,
# so these bring them into balance; music sits well under the effects.
LEVEL = {"swoosh": 0.9, "splat": 0.9, "throw": 0.35, "explode": 0.8, "fuse": 0.45, "miss": 0.75,
         "combo": 0.7, "power": 0.7, "stamp": 0.6, "life": 0.55, "gong": 0.75, "music": 0.4,
         "timestop": 0.7, "clones": 0.7, "dragonfire": 0.7, "boss_hit": 0.8, "boss_roar": 0.8, "fever": 0.45,
         "shuriken": 0.7}


def _load_files(folder):
    """{game name: [Sound]} for every wav/ogg named <prefix><digit>_<n>.<ext> in folder."""
    files = {}
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            m = re.match(r"([a-z]+)\d*_\d+\.(wav|ogg)$", fn)
            if m and m.group(1) in GROUPS:
                files.setdefault(GROUPS[m.group(1)], []).append(os.path.join(folder, fn))
    for alias, src in ALIASES.items():
        if src in files:
            files[alias] = files[src]
    out = {}
    for name, paths in files.items():
        for path in paths:
            try:
                snd = pygame.mixer.Sound(path)  # own Sound per name: each has its own level
            except pygame.error:
                continue  # unreadable file: the synthesized fallback covers it
            snd.set_volume(LEVEL[name])
            out.setdefault(name, []).append(snd)
    return out


class Audio:
    def __init__(self, folder=AUDIO_DIR):
        global SR
        self.ok = False
        self.muted = False
        self.s = {}
        try:
            pygame.mixer.init(SR, -16, 1, 512)
        except pygame.error:
            return  # no audio device: the game still runs silently
        SR, _, self.channels = pygame.mixer.get_init()
        pygame.mixer.set_num_channels(32)
        pygame.mixer.set_reserved(2)
        self.fuse_ch = pygame.mixer.Channel(0)
        self.music_ch = pygame.mixer.Channel(1)
        self.s = _load_files(folder)
        rng = random.Random(5)
        # Synthesis costs about a second, so each fallback only runs when its files are missing.
        fallback = {
            "swoosh": lambda: [self._snd(swoosh(rng, rng.uniform(0.13, 0.2), rng.uniform(1800, 3000), rng.uniform(400, 700))) for _ in range(4)],
            "splat": lambda: [self._snd(splat(rng)) for _ in range(4)],
            "throw": lambda: [self._snd(swoosh(rng, 0.28, 250, 900), 0.35)],
            "explode": lambda: [self._snd(explosion(rng))],
            "fuse": lambda: [self._snd(fuse(rng), 0.5)],
            "tick": lambda: [self._snd(tick(rng), 0.6)],
            "miss": lambda: [self._snd(_mix((_sine_drop(int(0.25 * SR), 170, 85, 0.07), 1.0), (taiko(rng, 0.25, 90, 50), 0.6)), 0.8)],
            "stamp": lambda: [self._snd(_mix((taiko(rng, 0.45, 140, 60), 1.0), (swoosh(rng, 0.06, 3000, 1500), 0.5)))],
            "combo": lambda: [self._snd(arpeggio(rng, [74, 79, 81, 86], 0.06), 0.8)],
            "power": lambda: [self._snd(arpeggio(rng, [74, 77, 81, 86, 89, 93], 0.045, 1.4), 0.9)],
            "life": lambda: [self._snd(arpeggio(rng, [81, 86], 0.09), 0.7)],
            "gong": lambda: [self._snd(_mix((taiko(rng, 1.0, 100, 45), 1.0), (pluck(_midi(50), 1.8, rng, 0.3), 0.6)))],
            "music": lambda: [self._snd(music(rng), 0.42)],
        }
        for name, build in fallback.items():
            if name not in self.s:
                self.s[name] = build()
        # new sounds with no files reuse an existing group's sounds (fever stays a quiet one-shot rather than a loop)
        for name, src in (("timestop", "power"), ("clones", "power"), ("dragonfire", "power"), ("fever", "power"),
                          ("boss_hit", "splat"), ("boss_roar", "gong"), ("shuriken", "swoosh")):
            if name not in self.s:
                self.s[name] = self.s[src]
        self.music_snd = random.choice(self.s["music"])  # one loop per session
        self.ok = True

    def _snd(self, samples, vol=0.9):
        peak = max(1e-6, max(abs(x) for x in samples))
        k = 32767 * vol / peak
        a = array.array("h", (int(x * k) for x in samples))
        if self.channels == 2:
            st = array.array("h", bytes(len(a) * 4))
            st[0::2] = a
            st[1::2] = a
            a = st
        return pygame.mixer.Sound(buffer=a.tobytes())

    def play(self, name, vol=1.0):
        if not self.ok or self.muted:
            return
        ch = random.choice(self.s[name]).play()
        if ch:
            ch.set_volume(min(1.0, vol * random.uniform(0.94, 1.06)))

    def fuse(self, on):
        if not self.ok:
            return
        if on and not self.muted and not self.fuse_ch.get_busy():
            self.fuse_ch.play(random.choice(self.s["fuse"]), loops=-1)
            self.fuse_ch.set_volume(0.35)
        elif not on and self.fuse_ch.get_busy():
            self.fuse_ch.stop()

    def start_music(self):
        if self.ok and not self.muted and not self.music_ch.get_busy():
            self.music_ch.play(self.music_snd, loops=-1, fade_ms=1500)
            self.music_ch.set_volume(0.55)

    def toggle_mute(self):
        self.muted = not self.muted
        if self.ok:
            if self.muted:
                pygame.mixer.stop()
            else:
                self.start_music()
