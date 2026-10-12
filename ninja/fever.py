"""Fever: the cut chain, its score multiplier and the fruit rain once it peaks.

Pure logic in `Fever`; Play (modes with the "fever" feature) keeps thin hooks: `on_cut` before scoring a cut,
`Fever.points` on every score it awards, `Fever.reset` on a strike, a lost life or a bomb, and `tick_fever` once a
frame for the timer, the rain and the drum layer.
"""
import random

from .art import REGULAR, WEIGHTS
from .settings import W, H

CHAIN_STEP = 10  # cuts per multiplier step
MAX_MULT = 5  # reaching it starts Fever
FEVER_TIME = 8.0
RAIN_EVERY = 0.12  # s between rain fruit
GRADE = (255, 236, 200)  # warm gold multiply over the world during Fever


class Fever:
    def __init__(self):
        self.chain = 0
        self.active = False
        self.t = 0.0  # Fever time left
        self.rain_t = 0.0
        self.pop = 0.0  # 1 the moment the multiplier steps up, easing to 0 (HUD badge)

    @property
    def mult(self):
        return MAX_MULT if self.active else min(MAX_MULT, 1 + self.chain // CHAIN_STEP)

    def points(self, base):
        return base * self.mult

    def cut(self):
        """Count a cut; True when it starts Fever."""
        before = self.mult
        self.chain += 1
        if self.mult > before:
            self.pop = 1.0
        if not self.active and self.mult >= MAX_MULT:
            self.active, self.t, self.rain_t = True, FEVER_TIME, 0.0
            return True
        return False

    def reset(self):
        """A miss or a bomb: the chain breaks, and a running Fever with it."""
        self.chain, self.active, self.t = 0, False, 0.0

    def update(self, dt):
        """Advance Fever by `dt` game seconds; returns the fruit kinds to rain this frame."""
        self.pop = max(0.0, self.pop - dt * 3)
        if not self.active or dt <= 0:  # dt 0: Time Stop holds the clock
            return []
        run = min(dt, self.t)  # no rain past the end of Fever
        self.t -= dt
        self.rain_t -= run
        kinds = []
        while self.rain_t <= 0 and len(kinds) < 3:  # a long frame never dumps a crate of fruit at once
            kinds.append(random.choices(REGULAR, WEIGHTS)[0])
            self.rain_t += RAIN_EVERY
        self.rain_t = max(self.rain_t, 0.0)
        if self.t <= 0:
            self.reset()
        return kinds

    def left(self):
        """Share of Fever still to run (HUD bar)."""
        return max(0.0, self.t / FEVER_TIME) if self.active else 0.0

    def grade(self):
        """Strength of Fever's gold grade: eased in at the start, out over the last moments."""
        return min(1.0, (FEVER_TIME - self.t) / 0.4, self.t / 0.6) if self.active else 0.0


# ---------------- Play hooks ----------------

def on_cut(play):
    f = play.fever
    if f is not None and f.cut():
        play.w.stamp("熱", "Fever", W / 2, H * 0.44, 120)  # clear above a power stamp (H * 0.72), caption included
        play.w.shake.kick(0.25)
        play.w.zoom_punch(1.02)


def tick_fever(play, dt):
    """Once a frame: Fever's clock runs on game time (Time Stop holds it, and no rain falls into frozen time)."""
    f = play.fever
    if f is None:
        return
    w = play.w
    if play.state == "play":
        sign = 1 if w.gflip > 0 else -1  # rain falls with gravity: from the bottom while the dojo is upside down
        for kind in f.update(dt * w.power_scale):
            b = w.throw(kind, random.uniform(W * 0.08, W * 0.92), -40 if sign > 0 else H + 40,
                        random.uniform(-120, 120), sign * random.uniform(60, 160))
            b.rain, b.flight = True, None  # never a strike; no launch arc to swell along
    play.app.audio.loop("fever", f.active and play.state == "play")


def fever_fx(play, p):
    if play.fever is not None and play.fever.active:
        p["saturation"] *= 1.15
