"""Boss fruit (Ninja Path): a Durian or a Pineapple King rises out of the dark, hovers for a few seconds and takes
30 hits to bring down.

`Boss` is the fruit itself (motion, hits, cracks, the defeat split) and `BossDirector` decides when one appears.
Play keeps thin hooks: `slice_boss` from `Play.slice`, `tick_boss` once a frame, `BossDirector.draw` in its world
layer and `draw_boss_bar` (hud.py). The boss is never in `World.bodies`, so Shadow Clones and Dragon Fire never
target it, and Time Stop leaves it alone: the world (boss included) is frozen and slicing is blocked while time is
held, and the resolution only cuts the fruit the path marked.
"""
import math
import random

import pygame

from .art import BOSS_R, REGULAR, WEIGHTS, make_shadow
from .entities import seg_hits_circle
from .fever import on_cut as fever_cut
from .fx import glow, shade
from .settings import W, H, GRAVITY

# Boss tuning. HP = hits to defeat it. The boss moves through phases: RISE (comes up from below), HOVER (floats, can be hit), ESCAPE (flies off) - times in seconds.
HP = 30
RISE, HOVER, ESCAPE = 1.2, 8.0, 1.0  # s per phase
COOLDOWN = 0.06  # s between hits
DEATH = 1.4  # s for the split halves to fly clear
CRACK_AT = (20, 10)  # hp at which each set of cracks opens
# Which bosses appear (in turn), their on-screen titles, and a few per-boss look settings.
NAMES = ("durian", "pineapple")
TITLES = {"durian": "Durian", "pineapple": "Pineapple King"}
FLESH = {"durian": (238, 206, 116), "pineapple": (255, 214, 86)}  # juice, chips, the glow inside the cracks
CROWN = {"durian": 0.2, "pineapple": 0.42}  # share of the sprite height above the body (stem, leaves): no cracks there
SPARK = (255, 228, 184)  # hard rind: hot, pale sparks, like steel on stone
# Bonus points for the kill, then timings (seconds) for the little hit counter and the victory stamp.
BONUS = 50
TALLY_HOLD, TALLY_FADE = 0.6, 0.3  # s the hit counter stays after the last hit, then fades
STAMP_DELAY = 0.25  # s after the kill: the 討 seal lands once the fruit burst has spread


def ease_out(u):
    """Turn 0-to-1 progress into a motion that starts fast and settles gently."""
    return 1 - (1 - u) ** 3


class BossHalf:
    """One side of the split boss: tumbling away under gravity, fading as it goes."""

    def __init__(self, img, x, y, vx, vy, spin):
        """Start one half with its picture, position, velocity (vx, vy) and spin speed."""
        self.img, self.x, self.y, self.vx, self.vy, self.spin, self.ang = img, x, y, vx, vy, spin, 0.0

    def update(self, dt):
        """Fall under gravity (a bit lighter than normal) while drifting sideways and spinning."""
        self.vy += GRAVITY * 0.85 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ang += self.spin * dt


class Boss:
    """The boss fruit: a state machine that moves through the phases "rise" -> "hover" -> "escape", or to "dead" if its HP runs out."""
    def __init__(self, art, name, x=None):
        """Create a boss of kind `name`. It starts below the screen, ready to rise. `art` can be None (used by tests with no graphics)."""
        self.art, self.name = art, name
        self.title, self.flesh = TITLES[name], FLESH[name]
        self.hp, self.r = HP, BOSS_R
        self.shown = float(HP)  # HUD: a pale damage trail easing down to hp
        side = random.choice((-1, 1))
        self.x0 = x if x is not None else W / 2 - side * random.uniform(0, W * 0.12)
        self.side = side  # sways toward the centre, never off screen
        self.y0, self.start = H * 0.44, H + BOSS_R * 1.5
        self.x, self.y, self.ang, self.scale = self.x0, self.start, 0.0, 1.0
        self.phase, self.t, self.done = "rise", 0.0, False
        self.esc = (self.x, self.y, 0.0)  # where (and at what angle) the escape starts
        self.last_hit = -1.0
        self.hit_age, self.hit_dir = 9.0, (1.0, 0.0)  # recoil wobble after a hit
        self.flash = 0.0
        self.halves, self.cut, self.burst = [], None, False
        self.seal = None  # the defeat stamp's bonus text, until it lands
        self.tally, self.tally_t = 0, 9.0  # points from the current run of hits (one counter, not a popup each)
        self.dead_t = 0.0
        self._img = {}  # stage -> (sprite with cracks, emissive crack glow or None)

    # --- life ---
    @property
    def stage(self):
        """How damaged it looks: 0 = whole, 1 or 2 = more cracks, based on how many CRACK_AT limits HP has dropped below."""
        return sum(self.hp <= h for h in CRACK_AT)

    def hit(self, now, dx=1.0, dy=0.0):
        """One hit from a slice moving along (dx, dy); False while cooling down or out of reach."""
        if self.phase not in ("rise", "hover") or now - self.last_hit < COOLDOWN:
            return False
        self.last_hit = now
        self.hp -= 1
        L = math.hypot(dx, dy) or 1
        self.hit_dir, self.hit_age, self.flash = (dx / L, dy / L), 0.0, 1.0
        if self.hp <= 0:
            self.hp, self.phase, self.dead_t = 0, "dead", 0.0
            self.split(dx / L, dy / L)
        return True

    def flee(self):
        """The run is over: leave the stage, untouchable."""
        if self.phase in ("rise", "hover"):
            self.phase, self.t, self.esc = "escape", 0.0, (self.x, self.y, self.ang)

    def update(self, dt):
        """Advance the boss one frame: ease the health trail, then move it according to its current phase."""
        self.shown = max(float(self.hp), self.shown - dt * 6 * max(1.0, self.shown - self.hp))
        self.flash = max(0.0, self.flash - dt * 10)
        self.hit_age += dt
        self.tally_t += dt
        if self.tally and self.tally_t >= TALLY_HOLD + TALLY_FADE:
            self.tally = 0  # faded out: the next hit starts a fresh count
        if self.phase == "dead":
            self.dead_t += dt
            for h in self.halves:
                h.update(dt)
            self.done = self.dead_t >= DEATH
            return
        self.t += dt
        if self.phase == "rise" and self.t >= RISE:
            self.phase, self.t = "hover", self.t - RISE
        if self.phase == "hover" and self.t >= HOVER:
            self.phase, self.t, self.esc = "escape", self.t - HOVER, (*self.hover_pos(HOVER), self.hover_ang(HOVER))
        if self.phase == "escape" and self.t >= ESCAPE:
            self.done = True
        if self.phase == "rise":  # heavy: fast off the floor, settling into place
            e = ease_out(self.t / RISE)
            self.x, self.y = self.x0, self.start + (self.y0 - self.start) * e
            self.ang, self.scale = 7 * (1 - e) * self.side, 0.94 + 0.06 * e
        elif self.phase == "hover":
            (self.x, self.y), self.ang, self.scale = self.hover_pos(self.t), self.hover_ang(self.t), 1.0
        else:  # gathers itself, then is gone over the top
            u = min(1.0, self.t / ESCAPE)
            ex, ey, ea = self.esc
            self.x, self.y = ex, ey - (ey + self.r * 2.2) * u ** 2.2
            self.ang, self.scale = ea - 10 * u * self.side, 1.0 - 0.08 * u

    def hover_pos(self, h):
        """Where the boss floats `h` seconds into its hover: a slow sideways sway plus a small bob."""
        # 1 - cos: the bob and sway start from rest, so the rise flows into the hover without a kink
        return (self.x0 + self.side * 70 * (1 - math.cos(h * 0.8)), self.y0 + 16 * (1 - math.cos(h * 1.7)))

    def hover_ang(self, h):
        """How much it tilts `h` seconds into its hover (a gentle rock back and forth)."""
        return 4.5 * math.sin(h * 1.1)

    # --- art ---
    def images(self):
        """(sprite with this stage's cracks, the cracks' emissive glow); every stage is built on the first call, so
        the cracks opening mid-fight never cost a frame."""
        if not self._img:
            base = self.art.boss[self.name]
            self.shadow = make_shadow(base, 110)
            white = base.copy()
            white.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
            self.white = pygame.Surface(base.get_size())
            self.white.blit(white, (0, 0))  # white x coverage, on black: ready to add as light
            self.inside = pygame.mask.from_surface(base, 200)
            w, h = base.get_size()
            self.inside.erase(pygame.mask.Mask((w, int(h * CROWN[self.name])), fill=True), (0, 0))  # rind only
            rng = random.Random(self.name)  # the same cracks every time
            self.cracks = [self.make_crack(rng, base, 0.55 + 0.25 * i) for i in range(6)]
            self._img[0] = (base, None)
            for st in (1, 2):
                self._img[st] = self.cracked(base, self.cracks[:3 * st])
        return self._img[self.stage]

    def make_crack(self, rng, base, reach):
        """A jagged fissure from the rind toward the middle, with a short branch: [main polyline, branch]."""
        w, h = base.get_size()
        cx, cy = w / 2, h / 2
        for _ in range(40):
            a = rng.uniform(0, math.tau)
            px, py = cx + math.cos(a) * w * 0.4, cy + math.sin(a) * h * 0.4
            while math.hypot(px - cx, py - cy) > 10 and not self.inside.get_at((int(px), int(py))):
                px, py = px + (cx - px) * 0.06, py + (cy - py) * 0.06
            if self.inside.get_at((int(px), int(py))):
                break
        heading = math.atan2(cy - py, cx - px) + rng.uniform(-0.5, 0.5)
        main = [(px, py)]
        length = self.r * reach * rng.uniform(0.8, 1.15)
        while length > 0:
            heading += rng.uniform(-0.55, 0.55)
            step = rng.uniform(8, 15)
            px, py = px + math.cos(heading) * step, py + math.sin(heading) * step
            if not (0 <= px < w and 0 <= py < h) or not self.inside.get_at((int(px), int(py))):
                break
            main.append((px, py))
            length -= step
        lines = [main]
        if len(main) > 4:
            bx, by = main[rng.randrange(1, len(main) - 2)]
            heading2 = heading + rng.choice((-1, 1)) * rng.uniform(0.6, 1.0)
            branch = [(bx, by)]
            for _ in range(rng.randint(2, 4)):
                heading2 += rng.uniform(-0.5, 0.5)
                bx, by = bx + math.cos(heading2) * rng.uniform(7, 12), by + math.sin(heading2) * rng.uniform(7, 12)
                if not (0 <= bx < w and 0 <= by < h) or not self.inside.get_at((int(bx), int(by))):
                    break
                branch.append((bx, by))
            lines.append(branch)
        return lines

    def cracked(self, base, cracks):
        """Dark fissures (tapering, with a pale lip catching the light) and their glow: the flesh showing through."""
        img = base.copy()
        dark = pygame.Surface(base.get_size(), pygame.SRCALPHA)
        lit = pygame.Surface(base.get_size())
        for crack in cracks:
            for k, line in enumerate(crack):
                n = len(line)
                for i, (a, b) in enumerate(zip(line, line[1:])):
                    taper = 1 - i / max(1, n - 1)
                    wd = max(1, round((7 if k == 0 else 4) * (0.3 + 0.7 * taper)))
                    pygame.draw.line(dark, (255, 238, 210, 45), (a[0] - 1, a[1] - 1), (b[0] - 1, b[1] - 1), wd)
                    pygame.draw.line(dark, (22, 12, 6, 235), a, b, wd)
                    if wd >= 3:  # the flesh glows only deep in the wider fissures; their edges stay dark
                        pygame.draw.line(lit, shade(self.flesh, 0.55), a, b, max(1, wd - 4))
        cover = base.copy()
        cover.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
        dark.blit(cover, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)  # never past the rind
        img.blit(dark, (0, 0))
        soft = pygame.transform.gaussian_blur(lit, 2)
        soft.blit(lit, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        soft.blit(self.white, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        return img, soft

    def split(self, dx, dy):
        """The killing cut: the boss (as it looks now) in two halves along the slash, flung apart."""
        self.cut = (self.x, self.y, dx, dy)
        if self.art is None:
            return
        img = pygame.transform.rotozoom(self.images()[0], self.ang, self.scale)
        w, h = img.get_size()
        cx, cy, nx, ny, big = w / 2, h / 2, -dy, dx, w + h
        for side in (1, -1):
            half = img.copy()
            sx, sy = nx * side, ny * side
            other = [(cx + dx * big, cy + dy * big), (cx - dx * big, cy - dy * big),
                     (cx - dx * big - sx * big, cy - dy * big - sy * big), (cx + dx * big - sx * big, cy + dy * big - sy * big)]
            pygame.draw.polygon(half, (0, 0, 0, 0), other)
            edge = pygame.Surface((w, h), pygame.SRCALPHA)  # the cut face: wet flesh along the chord
            a, b = (cx - dx * big, cy - dy * big), (cx + dx * big, cy + dy * big)
            pygame.draw.line(edge, (*shade(self.flesh, 0.8), 255), a, b, 9)
            pygame.draw.line(edge, (*self.flesh, 255), a, b, 4)
            cover = half.copy()
            cover.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
            edge.blit(cover, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            half.blit(edge, (0, 0))
            self.halves.append(BossHalf(half, self.x + sx * 8, self.y + sy * 8, sx * random.uniform(340, 420) + dx * 120,
                                        sy * 340 - 300, side * random.uniform(90, 160)))

    def draw(self, L, add):
        """Draw the boss with a hit recoil wobble, its shadow, crack glow and a white flash on impact. `L` is the world layer; `add` is the glow layer that brightens what it overlays."""
        if self.art is None:
            return
        if self.phase == "dead":
            self.draw_death(L, add)
            return
        img, lit = self.images()
        a = self.hit_age
        rec = 12 * math.exp(-a * 14) * math.cos(a * 42)  # knocked along the slash, ringing back
        ang = self.ang + 5 * math.exp(-a * 10) * math.sin(a * 36) * (1 if self.hit_dir[0] >= 0 else -1)
        x, y = self.x + self.hit_dir[0] * rec, self.y + self.hit_dir[1] * rec
        s = self.scale * (1 - 0.035 * math.exp(-a * 16))
        sh = pygame.transform.rotate(self.shadow, ang)
        L.blit(sh, sh.get_rect(center=(round(x + 22), round(y + 34))))
        im = pygame.transform.rotozoom(img, ang, s)
        pos = im.get_rect(center=(round(x), round(y)))
        L.blit(im, pos)
        # light layers are soft and additive: an unsmoothed rotate is ~7x cheaper than rotozoom and looks the same
        turn = (lambda im: pygame.transform.rotate(im, ang)) if s > 0.99 else (lambda im: pygame.transform.rotozoom(im, ang, s))
        if lit is not None:
            g = turn(lit)
            add.blit(g, g.get_rect(center=pos.center), special_flags=pygame.BLEND_RGB_ADD)
        if self.flash > 0.02:  # the hit lands as light on the rind
            f = turn(self.white)
            k = int(70 * self.flash ** 2)  # the bloom carries it further: a glint, not a white-out
            f.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
            add.blit(f, f.get_rect(center=pos.center), special_flags=pygame.BLEND_RGB_ADD)

    def draw_death(self, L, add):
        """Draw the two halves flying apart and the bright slash of light across the fruit."""
        fade = max(0.0, min(1.0, (DEATH - self.dead_t) / 0.4))
        for h in self.halves:
            im = pygame.transform.rotate(h.img, h.ang)
            im.set_alpha(int(255 * fade))
            L.blit(im, im.get_rect(center=(round(h.x), round(h.y))))
        u = self.dead_t / 0.3
        if self.cut and u < 1:  # the killing stroke: a long blade of light across the whole fruit
            x, y, dx, dy = self.cut
            k, reach = (1 - u) ** 2, self.r * (2.2 + 1.2 * ease_out(u))
            a, b = (x - dx * reach, y - dy * reach), (x + dx * reach, y + dy * reach)
            g = glow(self.art, self.r * 1.4, self.flesh, 0.5 * k)
            add.blit(g, g.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
            for col, wd in (((255, 190, 120), 9), ((255, 250, 236), 2.5)):  # a lens of light: widest mid-fruit
                ex, ey = -dy * wd * k, dx * wd * k
                pygame.draw.polygon(add, shade(col, k), (a, (x + ex, y + ey), b, (x - ex, y - ey)))


class BossDirector:
    """First boss at `first_at` s of game time, the next `every` s after the previous one ends; Durian first."""

    def __init__(self, first_at=45.0, every=45.0):
        """Schedule the first boss and the gap between bosses (both in seconds of game time)."""
        self.next_at, self.every = first_at, every
        self.active, self.leaving = None, None
        self.count = 0
        self.closed = False  # the run is over: no more bosses, and the waves stay paused

    @property
    def pause_waves(self):
        """True while a boss is up or the run is over, so normal fruit waves hold off."""
        return self.closed or self.active is not None

    def update(self, game_time, play):
        """Called every frame: when the countdown is up and no boss is out, spawn the next one (alternating Durian and Pineapple King)."""
        if self.active is not None and self.active.done:
            self.active, self.next_at = None, game_time + self.every
        if self.closed or self.active is not None or game_time < self.next_at:
            return None
        name = NAMES[self.count % len(NAMES)]
        self.count += 1
        self.active = Boss(play.app.art if play else None, name)
        if play is not None:
            w = play.w
            w.stamp("鬼", self.active.title, W / 2, H * 0.8, 120)  # below the boss, clear of its rise
            w.shake.kick(0.35)
            play.app.audio.play("boss_roar")
        return self.active

    def close(self):
        """The run has ended with the boss still up: it leaves (no longer hittable) and nothing returns."""
        self.closed = True
        if self.active is not None:
            self.active.flee()
            self.leaving, self.active = self.active, None

    def draw(self, L, add):
        """Draw whichever bosses are on stage."""
        for b in (self.leaving, self.active):
            if b is not None and not b.done:
                b.draw(L, add)


# These functions are called from the Play screen (game.py) so the boss code stays in this file.
# ---------------- Play hooks ----------------

def tick_boss(play, dt):
    """Once a frame (outside hit-stop), `dt` in world time: Time Stop holds the boss and its timers."""
    d = play.boss
    if d is None:
        return
    if play.state in ("dying", "ending", "over"):
        d.close()
    elif play.state == "play":
        d.update(play.elapsed, play)
    for b in (d.active, d.leaving):
        if b is not None:
            b.update(dt)
            if b.burst:
                burst(play, b)
            if b.seal and b.dead_t >= STAMP_DELAY:
                seal(play, b)
    if d.leaving is not None and d.leaving.done:
        d.leaving = None


def slice_boss(play):
    """Each slice segment crossing the boss is one hit (at most one per COOLDOWN)."""
    d = play.boss
    b = d.active if d else None
    if b is None or play.state != "play" or (play.power and play.power.blocks_slicing):
        return
    for seg in play.app.segments:
        ax, ay, bx, by = seg
        if seg_hits_circle(ax, ay, bx, by, b.x, b.y, b.r) and b.hit(play.app.now, bx - ax, by - ay):
            strike(play, b, seg)
            if b.phase == "dead":
                defeat(play, b)
                return


def closest(seg, x, y):
    """The point on line segment `seg` nearest to (x, y) - where the blade touched the boss."""
    ax, ay, bx, by = seg
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
    return ax + dx * t, ay + dy * t


def strike(play, b, seg):
    """Effects and score for one hit on the boss: sparks, flesh chips, screen shake, Fever chain and a sound."""
    w = play.w
    fever_cut(play)  # each hit grows the chain, like a cut
    pts = play.fever.points(1) if play.fever else 1
    play.add_score(pts)
    px, py = closest(seg, b.x, b.y)
    b.tally, b.tally_t = b.tally + pts, 0.0  # shown by the HUD as one growing "+N" by the boss
    w.hitstop = max(w.hitstop, 0.03)
    w.shake.kick(0.15)
    w.cut_heat += 0.5
    lod = min(1.0, w.HEAT_LOD / max(1.0, w.cut_heat))
    dx, dy = b.hit_dir
    w.particles.sparks(px, py, SPARK, round(11 * lod), 720, 0.35)
    w.particles.sparks(px, py, (255, 176, 90), round(4 * lod), 420, 0.3)
    w.particles.juice(px, py, b.flesh, -dy, dx, n=10, spread=18, lod=lod * 0.6)  # chips of flesh off the rind
    w.particles.add(px, py, 0, 0, 0.12, 40, SPARK, "glow", 0.0)  # the contact itself, a pop of light
    if b.hp in CRACK_AT:  # the rind gives: a heavier jolt as the cracks open
        w.shake.kick(0.2)
        w.particles.juice(b.x, b.y, b.flesh, -dy, dx, n=24, spread=b.r * 0.5, lod=lod)
    play.app.audio.play("boss_hit")


def defeat(play, b):
    """The boss has just died: big flash, shake and juice splash, bonus score, and queue the fruit burst and victory stamp."""
    w = play.w
    x, y, dx, dy = b.cut
    w.flash = max(w.flash, 0.6)
    w.hitstop = max(w.hitstop, 0.12)
    w.shake.kick(0.6)
    w.zoom_punch(1.035)
    w.shocks.append([x, y, 0.0])
    w.particles.splash(x, y, b.flesh, -dy, dx, b.r * 0.7)
    for o in (-0.6, 0.0, 0.6):  # juice off the whole length of the cut
        w.particles.juice(x + dx * b.r * o, y + dy * b.r * o, b.flesh, -dy, dx, n=24, spread=30)
    w.particles.sparks(x, y, SPARK, 40, 1000, 0.6)
    w.stains.add(b.flesh, b.r, x, y)
    b.burst = True  # the fruit burst comes as the hit-stop lets go (tick_boss), not into the blade still in the cut
    bonus = play.fever.points(BONUS) if play.fever else BONUS
    play.add_score(bonus)
    b.seal = f"+{bonus}"  # the stamp waits for the burst to clear (tick_boss)
    play.app.audio.play("boss_roar")


def seal(play, b):
    """討 where the boss was: by now the burst has flown out past the rim and the halves have parted, so the middle is
    the one clear spot (below it, the falling lower half crosses the seal). Stamp clamps itself on screen."""
    x, y = b.cut[:2]
    play.w.stamp("討", "Boss down", x, y - 20, 140, bonus=b.seal)
    b.seal = None


def burst(play, b):
    """The boss bursts into 12 regular fruit flung outward: cuttable, and never a lost life."""
    b.burst = False
    x, y = b.cut[:2]
    for i in range(12):
        a = -math.pi / 2 + (i - 5.5) / 12 * math.pi * 1.7 + random.uniform(-0.1, 0.1)
        sp = random.uniform(560, 900)
        f = play.w.throw(random.choices(REGULAR, WEIGHTS)[0], x + math.cos(a) * b.r * 0.6, y + math.sin(a) * b.r * 0.6,
                         math.cos(a) * sp, math.sin(a) * sp - 180)
        f.rain = True
