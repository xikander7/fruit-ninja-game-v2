"""Ninja Path hazards and special fruit: the shuriken, the ice bomb, the golden fruit and the chaos fruit.

Path mode only (the "hazards" feature): `roll_hazard` swaps wave items for hazards after HAZARDS_FROM s of game time.
Play keeps thin hooks: `launch_hazard` in launch, `on_hit` at the top of hit, `slice_hazards` at the top of slice,
`tick_hazards` once a frame, `draw` in the world's extra layer; the HUD reads `blade_frozen` and `Hazards.flip_t`.
"""
import math
import random

import pygame

from .art import make_shadow
from .entities import draw_shadow, seg_hits_circle
from .fx import glow, shade
from .settings import W, H, GOLD, STEEL

# Chance (0 to 1) that a wave item becomes each hazard. They are tried in order, so the odds add up (19% in total).
HAZARD_ODDS = {"shuriken": 0.08, "icebomb": 0.05, "golden": 0.03, "chaos": 0.03}
HAZARDS_FROM = 20.0  # s of game time before the first hazard

# Shuriken numbers, in pixels: speed (px/s), how close it must get to your cursor to hurt you, and its radius for being parried.
SHURIKEN_SPEED, SHURIKEN_HIT, SHURIKEN_R = 700.0, 22.0, 26.0
# Parrying: the blade must move faster than PARRY_SPEED px/s; a parry scores PARRY_POINTS; the star bounces back PARRY_BOOST times faster.
PARRY_SPEED, PARRY_POINTS, PARRY_BOOST = 1500.0, 2, 1.3
# How long (seconds) an ice bomb freezes your blade, and how long a chaos fruit flips gravity.
FREEZE_TIME, FLIP_TIME = 2.0, 5.0
# Golden fruit: hits needed, minimum seconds between hits (so one swipe counts once), points per hit, and the final bonus.
GOLD_HITS, GOLD_GAP, GOLD_HIT_POINTS, GOLD_BONUS = 5, 0.08, 5, 25
ICE = (170, 215, 250)
VIOLET = (170, 100, 255)
ICE_BLADE = ((30, 60, 90), (80, 120, 155), (130, 165, 195), (120, 155, 185))  # pale and dim: it cannot cut


def roll_hazard(rng, game_time):
    """The hazard (or special fruit) to put in place of one wave item, or None."""
    if game_time < HAZARDS_FROM:
        return None
    r = rng.random()
    for kind, p in HAZARD_ODDS.items():
        if r < p:
            return kind
        r -= p
    return None


class Shuriken:
    """A throwing star: straight at its target at 700 px/s, spinning, no gravity."""

    def __init__(self, x, y, tx, ty):
        d = math.hypot(tx - x, ty - y) or 1
        self.x, self.y = x, y
        self.vx, self.vy = (tx - x) / d * SHURIKEN_SPEED, (ty - y) / d * SHURIKEN_SPEED
        self.ang, self.spin = random.uniform(0, 90), random.choice((-1, 1)) * 1260
        self.parried = self.struck = False
        self.trail = []  # recent positions, newest last
        self.age = 0.0

    def update(self, dt):
        """Fly in a straight line and spin. `dt` is the seconds since the last frame; a trail of recent spots is kept for the smear effect."""
        if dt <= 0:
            return
        self.trail = (self.trail + [(self.x, self.y, self.ang)])[-4:]
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ang += self.spin * dt
        self.age += dt

    @property
    def gone(self):
        # off screen and still heading away (it starts just off an edge, heading in)
        return (self.x < -80 and self.vx <= 0 or self.x > W + 80 and self.vx >= 0 or
                self.y < -80 and self.vy <= 0 or self.y > H + 80 and self.vy >= 0)

    def near(self, px, py):
        """Is the point (px, py), usually the player's cursor, close enough to be hit by the star?"""
        return math.hypot(px - self.x, py - self.y) < SHURIKEN_HIT

    def parry(self, dx=0.0, dy=0.0):
        """Knocked away by the blade (moving along dx, dy): the velocity reflects off the blade's edge, is pushed
        along the swing, and leaves 1.3x faster."""
        self.parried = True
        L = math.hypot(dx, dy)
        vx, vy = self.vx, self.vy
        if L > 0:
            ux, uy = dx / L, dy / L
            nx, ny = -uy, ux
            dot = vx * nx + vy * ny
            vx, vy = vx - 2 * dot * nx, vy - 2 * dot * ny  # mirror off the edge...
            sp = math.hypot(vx, vy) or 1
            vx, vy = vx / sp + ux * 1.2, vy / sp + uy * 1.2  # ...and carried along the swing
        else:
            vx, vy = -vx, -vy
        sp = math.hypot(vx, vy) or 1
        self.vx, self.vy = vx / sp * SHURIKEN_SPEED * PARRY_BOOST, vy / sp * SHURIKEN_SPEED * PARRY_BOOST
        self.spin *= -1.6


class Hazards:
    """Per-run hazard state on Play (`play.hz`)."""

    def __init__(self):
        """Start a run with no shurikens, no flip and no visual flashes."""
        self.shurikens = []
        self.flip_t = 0.0  # gravity-flip time left (game seconds)
        self.punch = 0.0  # violet pulse on a flip / flip back: 1 easing to 0
        self.red = 0.0  # red flash after a shuriken hit
        self.rings = []  # [x, y, age]: metallic ring of a parry
        self.mist_t = 0.0


# ---------------- Play hooks ----------------

def throw_shuriken(play, x, y, tx, ty):
    """Create a shuriken at (x, y) flying toward (tx, ty) and add it to the game."""
    s = Shuriken(x, y, tx, ty)
    play.hz.shurikens.append(s)
    play.app.audio.play("shuriken", 0.8)
    return s


def launch_hazard(play, kind, x=None):
    """Launch a shuriken from a random screen edge at the cursor; True when `kind` was one (Play.launch does the rest)."""
    if kind != "shuriken":
        return False
    edge = random.choice(("left", "right", "top", "bottom"))
    if edge in ("left", "right"):
        x0, y0 = (-40 if edge == "left" else W + 40), random.uniform(H * 0.15, H * 0.85)
    else:
        x0, y0 = random.uniform(W * 0.1, W * 0.9), (-40 if edge == "top" else H + 40)
    throw_shuriken(play, x0, y0, *play.app.mouse)
    return True


def on_hit(play, b, seg):
    """Hazard rules for a hit body; True when the hit is fully handled here (Play.hit does nothing more)."""
    w = play.w
    if b.hazard == "ice":
        b.alive = False
        play.blade_frozen = FREEZE_TIME
        for _ in range(26):  # shattered ice: pale glassy beads and cold sparks
            a, sp = random.uniform(0, math.tau), random.uniform(150, 650)
            w.particles.drop(b.x, b.y, math.cos(a) * sp, math.sin(a) * sp - 120, random.uniform(0.4, 0.8),
                             random.uniform(1.6, 3.4), ICE)
        w.particles.sparks(b.x, b.y, (225, 242, 255), 40, 800, 0.5)
        for _ in range(8):
            w.particles.add(b.x, b.y, random.uniform(-160, 160), random.uniform(-160, 60), random.uniform(0.5, 0.9),
                            random.uniform(30, 60), ICE, "glow", -0.1)
        w.shake.kick(0.35)
        w.flash = max(w.flash, 0.25)
        w.zoom_punch(1.02)
        play.app.audio.play("explode", 0.45)
        return True
    if b.kind == "golden":
        now = w.t
        if now - b.hit_t < GOLD_GAP:
            return True  # the same swipe still crossing it
        b.hit_t = now
        b.hp -= 1
        if b.hp <= 0:  # the fifth hit cuts it: Play.hit scores it with the bonus
            b.points = GOLD_BONUS
            coins(w, b.x, b.y, 46, 720)
            w.particles.sparks(b.x, b.y, (255, 236, 170), 50, 950, 0.6)
            w.particles.embers(b.x, b.y, 24, 520)
            w.zoom_punch(1.025)
            w.shake.kick(0.3)
            w.hitstop = max(w.hitstop, 0.06)
            play.app.audio.play("power")
            return False
        pts = play.fever.points(GOLD_HIT_POINTS) if play.fever else GOLD_HIT_POINTS
        play.add_score(pts)
        w.popups.add(f"+{pts}", b.x + (GOLD_HITS - b.hp - 2.5) * 30, b.y - b.r - 10, GOLD)  # side by side, not a heap
        coins(w, b.x, b.y, 12, 420)
        w.particles.sparks(b.x, b.y, GOLD, 14, 520, 0.4)
        if not b.static:  # each hit juggles it a little higher
            b.vy -= 160 * w.gflip
        b.spin = -b.spin * 1.4
        w.shake.kick(0.08)
        play.app.audio.play("splat", 0.5)
        return True
    if b.kind == "chaos":
        flip(play, True)
    return False


def coins(w, x, y, n, speed):
    """Gold beads with a bright glint: the coin sparks of a golden hit."""
    for _ in range(n):
        a, sp = random.uniform(0, math.tau), random.uniform(0.3, 1.0) * speed
        w.particles.drop(x, y, math.cos(a) * sp, math.sin(a) * sp - 180, random.uniform(0.5, 0.9), random.uniform(2.2, 3.4), GOLD)


def flip(play, on):
    """Turn the upside-down gravity effect on or off, with a screen punch, stamp and gong."""
    w, hz = play.w, play.hz
    if on:
        hz.flip_t = FLIP_TIME
    w.gflip = -1.0 if on else 1.0
    hz.punch = 1.0
    w.zoom_punch(1.02)
    w.shake.kick(0.3)
    if on:
        w.stamp("逆", "Gravity flipped", W / 2, H * 0.58, 110)  # between Fever's stamp (0.44) and the powers' (0.72)
    play.app.audio.play("gong", 0.5)


def slice_hazards(play):
    """Before the normal slice: a fast blade parries shurikens. True while the blade is frozen (no slicing)."""
    if play.blade_frozen > 0:
        return True
    app, w = play.app, play.w
    if app.speed <= PARRY_SPEED or (play.power and play.power.blocks_slicing):
        return False
    for s in play.hz.shurikens:
        if s.parried or s.struck:
            continue
        for ax, ay, bx, by in app.segments:
            if seg_hits_circle(ax, ay, bx, by, s.x, s.y, SHURIKEN_R):
                s.parry(bx - ax, by - ay)
                play.add_score(PARRY_POINTS)
                w.popups.add(f"Parry +{PARRY_POINTS}", s.x, s.y - 40, STEEL, True)
                w.particles.sparks(s.x, s.y, (255, 250, 235), 44, 1100, 0.55)
                w.particles.sparks(s.x, s.y, (255, 196, 110), 26, 700, 0.45)
                w.particles.add(s.x, s.y, 0, 0, 0.18, 46, (230, 240, 255), "glow", 0)
                play.hz.rings.append([s.x, s.y, 0.0])
                w.hitstop = max(w.hitstop, 0.05)
                w.shake.kick(0.2)
                app.audio.play("shuriken")
                break
    return False


def tick_hazards(play, dt):
    """Once a frame (not during hit-stop). Timers run on the game clock, so Time Stop holds them."""
    hz, w = play.hz, play.w
    gdt = dt * w.power_scale
    play.blade_frozen = max(0.0, play.blade_frozen - gdt)
    if hz.flip_t > 0:
        hz.flip_t -= gdt
        if hz.flip_t <= 0:
            hz.flip_t = 0.0
            flip(play, False)
    hz.punch = max(0.0, hz.punch - dt * 2.2)
    hz.red = max(0.0, hz.red - dt * 3.0)
    for r in hz.rings:
        r[2] += dt
    hz.rings = [r for r in hz.rings if r[2] < 0.3]
    mdt = dt * w.time_scale()  # world time: slow-mo slows it, Time Stop holds it
    mx, my = play.app.mouse
    for s in hz.shurikens:
        s.update(mdt)
        if mdt > 0 and not s.parried and not s.struck and s.near(mx, my):  # a shuriken held by Time Stop can't strike
            s.struck = True
            play.lose_life(s.x, "shuriken")
            hz.red = 1.0
            w.shake.kick(0.7)
            w.particles.sparks(s.x, s.y, (255, 120, 90), 24, 600, 0.4)
            s.vx, s.vy = s.vx * 0.6, s.vy * 0.6
    hz.shurikens = [s for s in hz.shurikens if not s.gone]
    hz.mist_t -= gdt
    if hz.mist_t <= 0:  # ice bombs breathe a little cold vapour
        hz.mist_t = 0.06
        for b in w.bodies:
            if b.alive and b.hazard == "ice":
                w.particles.add(b.x + random.uniform(-b.r, b.r) * 0.6, b.y + random.uniform(-b.r, b.r) * 0.6,
                                random.uniform(-30, 30), random.uniform(-50, 10), random.uniform(0.4, 0.7),
                                random.uniform(14, 24), shade(ICE, 0.6), "glow", -0.15)


def blade_colors(scene):
    """The blade's colours when something overrides the player's: frozen (pale ice), else the running power's."""
    if getattr(scene, "blade_frozen", 0) > 0:
        return ICE_BLADE
    return getattr(getattr(scene, "power", None), "blade", None)


# Holds the shuriken's shadow image, built the first time it is needed and then reused.
_SHADOW = {}


def draw(play, L, add):
    """World layer: auras on the special bodies and the shurikens with their trails."""
    art, t = play.app.art, play.w.t
    for b in play.w.bodies:
        if not b.alive:
            continue
        if b.kind == "golden":  # a warm aura and a ring that tightens with every hit
            g = glow(art, b.r * 1.9, GOLD, 0.22 + 0.06 * math.sin(t * 7))
            add.blit(g, g.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
            rr = b.r * (1.85 - 0.17 * (GOLD_HITS - b.hp))
            pygame.draw.circle(add, shade(GOLD, 0.8), (b.x, b.y), rr, 2)
            pygame.draw.circle(add, shade(GOLD, 0.3), (b.x, b.y), rr + 4, 1)
        elif b.kind == "chaos":
            g = glow(art, b.r * 2.0, VIOLET, 0.4 + 0.15 * math.sin(t * 5))
            add.blit(g, g.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
        elif b.hazard == "ice":
            g = glow(art, b.r * 1.8, ICE, 0.3)
            add.blit(g, g.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
    img = art.shuriken
    if "s" not in _SHADOW:
        _SHADOW["s"] = make_shadow(img)
    for s in play.hz.shurikens:
        draw_shadow(L, _SHADOW["s"], s.x, s.y, s.ang, 1.0)
        n = len(s.trail)
        for i, (x, y, a) in enumerate(s.trail):  # a faint smear of where it just was
            ghost = pygame.transform.rotate(img, a)
            ghost.set_alpha(int(70 * (i + 1) / (n + 1)))
            L.blit(ghost, ghost.get_rect(center=(round(x), round(y))))
        if s.trail:
            x0, y0, _ = s.trail[0]
            pygame.draw.line(add, (40, 52, 66), (x0, y0), (s.x, s.y), 3)
        im = pygame.transform.rotozoom(img, s.ang, 1.0)
        L.blit(im, im.get_rect(center=(round(s.x), round(s.y))))
        g = glow(art, 30, STEEL, 0.18)  # a glint off the steel for the bloom
        add.blit(g, g.get_rect(center=(s.x, s.y)), special_flags=pygame.BLEND_RGB_ADD)
    for x, y, age in play.hz.rings:  # the parry's metallic ring
        k = 1 - age / 0.3
        pygame.draw.circle(add, shade((150, 170, 190), k), (x, y), 12 + 90 * (1 - k * k), max(1, int(3 * k)))


def draw_grades(play, screen):
    """Over the world, under the HUD: frost while the blade is frozen, the chaos violet, a shuriken hit's red."""
    app, hz = play.app, play.hz
    if play.blade_frozen > 0:
        k = min(1.0, play.blade_frozen / 0.4)
        screen.fill(tuple(int(255 - (255 - c) * 0.5 * k) for c in (200, 222, 245)), special_flags=pygame.BLEND_RGB_MULT)
        app.art.frost.set_alpha(int(255 * k))
        screen.blit(app.art.frost, (0, 0))
    k = (0.35 if hz.flip_t > 0 else 0.0) + 0.65 * hz.punch ** 2
    if k > 0:  # violet grade: held faintly while upside down, pulsing in on the flip and back
        screen.fill(tuple(int(255 - (255 - c) * min(1.0, k)) for c in (225, 205, 255)), special_flags=pygame.BLEND_RGB_MULT)
    if hz.red > 0:
        screen.fill((int(110 * hz.red ** 2), 0, 0), special_flags=pygame.BLEND_RGB_ADD)
        screen.fill(tuple(int(255 - (255 - c) * hz.red) for c in (255, 170, 160)), special_flags=pygame.BLEND_RGB_MULT)
