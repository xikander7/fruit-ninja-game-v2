"""The heart of the desktop game: saving, the screens and the main loop.

World draws the dojo background, Menu / Play / GameOver are the screens you move between,
Wipe is the cut-in-two transition, and App owns the window and runs the frame loop.
load_save / write_save keep your best scores in a small JSON file in your home folder.
"""
import json
import math
import os
import random

import pygame

from .art import Art, Fonts, FRUITS, REGULAR, WEIGHTS, SPECIALS, _font
from .audio import Audio
from .entities import Body, Half, seg_hits_circle, rotate_vec
from .hud import label, brush_x, chevron, hairline_ring, draw_play_hud, draw_grades
from .powers import KEYS as POWER_KEYS, KI_PER_COMBO, KiMeter, on_cut, tick_power, use_power
from .fever import Fever, on_cut as fever_cut, tick_fever, fever_fx
from .boss import BossDirector, slice_boss, tick_boss
from .hazards import Hazards, roll_hazard, launch_hazard, on_hit as hazard_hit, slice_hazards, tick_hazards, throw_shuriken, blade_colors, draw as draw_hazards
from .title import TitleIntro
from .fx import Particles, Stains, Trail, Shake, Popups, Stamp, ray_burst, glow, shade, blurred
from .settings import CAPTION, W, H, FPS, GRAVITY, SAVE_PATH, WASHI, GOLD, HANKO, MUTED, LACQUER, BLADES, MODES, MODE_FEATURES

# Blade input tuning. The mouse is the blade: a cursor moving faster than SLICE_SPEED slices, a slow drift does not.
SLICE_SPEED = 300  # px/s: just moving the cursor slices; a slow drift doesn't
MAX_JUMP = 350  # px in one motion event
# The UI layer is cleared to alpha 1, not 0. pygame blends onto a pixel with any alpha as dst + (src - dst) * a, which
# over black is premultiplied colour, but copies straight colour onto a fully clear pixel; the 1 keeps every pixel
# premultiplied, so text over its own shadow composites exactly as it did drawn straight onto the frame.
UI_CLEAR = (0, 0, 0, 1)


# ---------------- save data ----------------

def load_save():
    """Read the player's saved progress (best scores, chosen blade, mute setting) from disk. Anything missing or corrupt falls back to defaults, so a bad file never stops the game."""
    data = {"best": {m: 0 for m in MODES}, "blade": "Moonlight", "muted": False, "total_sliced": 0}
    try:
        raw = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
        for m in MODES:
            v = raw.get("best", {}).get(m, 0)
            data["best"][m] = int(v) if isinstance(v, (int, float)) and v >= 0 else 0
        if raw.get("blade") in BLADES:
            data["blade"] = raw["blade"]
        data["muted"] = bool(raw.get("muted", False))
        data["total_sliced"] = max(0, int(raw.get("total_sliced", 0)))
    except Exception:  # missing or corrupt save: start fresh
        pass
    return data


def write_save(data):
    """Never raises: losing a save must never crash the game."""
    try:
        tmp = SAVE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, SAVE_PATH)  # atomic: a crash never leaves half a file
    except (OSError, ValueError):
        pass


# ---------------- world: everything that lives on the dojo wall ----------------

class World:
    """Everything that lives on the dojo wall: flying fruit and bombs, cut halves, particles, stains, popups, stamps and the camera effects (shake, zoom, slow-mo, shockwaves).
    Both the menu and the game own one World.
    """
    # "Heat" counts recent cuts; when a lot happen at once (a power or fruit rain), each cut gets lighter effects (LOD = level of detail) so the game stays smooth.
    # MAX_HALVES caps how many cut halves exist at once.
    HEAT_TAU, HEAT_LOD, MAX_HALVES = 0.5, 6.0, 28  # cut-effect LOD: a storm of cuts gets lighter juice per cut
    PUNCH = 0.25  # s for a combo zoom punch to ease back
    SLOW_HOLD, SLOW_EASE = 0.4, 0.15  # slow-mo: held at full strength, then eased back to real time
    SHOCK = 0.6  # s for a bomb shockwave to cross the screen

    def __init__(self, app, bg=None):
        """Create an empty world: no fruit, fresh effect systems, and a few specks of dust already floating in the lamplight."""
        self.app, self.art = app, app.art
        self.bg = bg or self.art.bg
        self.bodies, self.halves = [], []
        self.particles = Particles(self.art)
        self.stains = Stains(self.art)
        self.popups = Popups(self.art.fonts)
        self.stamps = []
        self.shake = Shake()
        self.layer = pygame.Surface((W, H))
        self.slashes, self.rings = [], []
        self.flash = 0.0
        self.hitstop = 0.0
        self.punch = [1.0, self.PUNCH]  # (peak zoom, age)
        self.slowmo = 0.0  # real seconds of slow-mo left
        self.shocks = []  # [x, y, age]
        self.t = 0.0
        self.gflip = 1.0  # gravity sign: -1 while a chaos fruit has turned the dojo upside down
        self.power_scale = 1.0  # 0 while Time Stop holds the world still
        self.cut_heat = 0.0  # ~ cuts in the last HEAT_TAU s (decays exponentially on real time)
        self.mote_t = 0.0
        self.ember_t = random.uniform(1.0, 3.0)
        for _ in range(40):  # the dojo already has dust hanging in the lamplight
            self.particles.mote()

    def throw(self, kind, x, y, vx, vy, static=False):
        """Add a new fruit or bomb of the given kind at (x, y) moving at (vx, vy) pixels per second, and return it."""
        b = Body(self.art, kind, x, y, vx, vy, static)
        self.bodies.append(b)
        return b

    def cut(self, b, ax, ay, bx, by):
        """Slice body `b` with a blade stroke from (ax, ay) to (bx, by): spawn two halves that fly apart sideways, plus juice, a stain and a sound.
        The maths: (dx, dy) is the stroke direction, and (nx, ny) is perpendicular to it, which is the way the halves separate.
        """
        b.alive = False
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1
        dx, dy = dx / L, dy / L
        nx, ny = -dy, dx
        fa = self.art.fruits[b.kind]
        for side in (1, -1):
            sx, sy = nx * side, ny * side
            vx = (0 if b.static else b.vx * 0.6) + sx * 170 + dx * 60
            vy = (0 if b.static else b.vy * 0.6) + sy * 170 - 120
            self.halves.append(Half(fa, b.x + sx * b.r * 0.3, b.y + sy * b.r * 0.3, vx, vy, math.degrees(math.atan2(-sy, sx)), b))
        del self.halves[:-self.MAX_HALVES]  # the oldest are falling away anyway
        self.cut_heat += 1  # 1 at normal cut rates; powers and fruit rain can cut dozens a second
        lod = min(1.0, self.HEAT_LOD / self.cut_heat)
        if lod >= 1 or random.random() < lod:
            self.particles.splash(b.x, b.y, b.ft.juice, nx, ny, b.r)  # first, so the droplets draw over it
        self.particles.juice(b.x, b.y, b.ft.juice, nx, ny, spread=b.r * 1.1, lod=lod)  # the whole chord of the cut
        if lod >= 0.5:
            self.stains.add(b.ft.juice, b.r, b.x, b.y)
        self.slashes.append([b.x, b.y, dx, dy, b.r * 1.6, 0.0])
        self.app.audio.play("splat", 0.8)

    def explode(self, b):
        """Blow up a bomb with a flash, shockwave, sparks, smoke, shards and a big screen shake."""
        b.alive = False
        self.rings.append([b.x, b.y, 0.0])
        self.shocks.append([b.x, b.y, 0.0])
        self.flash = 0.8
        self.hitstop = 0.12
        self.particles.sparks(b.x, b.y, (255, 190, 90), 50, 1100, 0.7)
        self.particles.sparks(b.x, b.y, (255, 255, 230), 20, 500, 0.35)
        self.particles.smoke(b.x, b.y, 22)
        self.particles.shards(b.x, b.y, 10)
        self.particles.embers(b.x, b.y, 40)
        self.shake.kick(1.0)
        self.app.audio.play("explode")

    def zoom_punch(self, zoom):
        """Briefly zoom the camera in to `zoom` (e.g. 1.02 = 2%), which then eases back by itself."""
        self.punch = [zoom, 0.0]

    def slow(self):
        """Start a short slow-motion moment."""
        self.slowmo = self.SLOW_HOLD + self.SLOW_EASE

    def slow_k(self):
        """1 while slow-mo is at full strength, easing to 0 as it ends."""
        if self.slowmo <= 0:
            return 0.0
        if self.slowmo >= self.SLOW_EASE:
            return 1.0
        u = self.slowmo / self.SLOW_EASE
        return u * u * (3 - 2 * u)

    def time_scale(self):
        """How fast the world's time runs right now: 1 normal, down to 0.3 in slow-mo, 0 while Time Stop holds everything."""
        return (1.0 - 0.7 * self.slow_k()) * self.power_scale  # 0.3 at full slow-mo

    def stamp(self, glyph, caption, x, y, size=120, color=WASHI, bonus=None, hold=False):
        """Slam a red seal (a kanji character with a caption) onto the screen, e.g. "Fever"."""
        self.stamps.append(Stamp(self.art, glyph, caption, x, y, size, color, bonus, hold))

    def update(self, dt, real_dt):
        """Advance the world one frame. `real_dt` is true elapsed time (camera effects use it); `dt` is game time, which can be slowed, frozen or stopped by hit-stop."""
        # camera/post effects run on real time so they play out even through hit-stop and slow-mo
        self.t += real_dt
        self.shake.update(real_dt)
        self.flash = max(0.0, self.flash - real_dt * 6.0)  # a sharp pop; a slow fade reads as fog
        self.slowmo = max(0.0, self.slowmo - real_dt)
        self.cut_heat *= math.exp(-real_dt / self.HEAT_TAU)
        self.punch[1] += real_dt
        for s in self.shocks:
            s[2] += real_dt
        self.shocks = [s for s in self.shocks if s[2] < self.SHOCK]
        for st in self.stamps:
            if not st.landed and st.age >= 0.11:
                st.landed = True
                self.particles.ink(st.x, st.y, HANKO, 18)
                self.shake.kick(0.22)
                self.app.audio.play("stamp", 0.7)
        self.stamps = [s for s in self.stamps if s.update(real_dt)]
        self.popups.update(real_dt)
        if self.hitstop > 0:
            self.hitstop -= real_dt
            return
        g = GRAVITY * self.gflip
        for b in self.bodies:
            b.update(dt, g)
        for h in self.halves:
            h.update(dt, g)
        self.halves = [h for h in self.halves if not h.gone()]
        self.particles.update(dt)
        self.particles.blur = self.time_scale()  # slow-mo shortens streaks; freeze doesn't
        self.stains.update(dt)
        for s in self.slashes:
            s[5] += dt
        self.slashes = [s for s in self.slashes if s[5] < 0.16]
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < self.SHOCK]
        self.mote_t -= dt
        if self.mote_t <= 0:
            self.mote_t = random.uniform(0.15, 0.35)
            self.particles.mote()
        self.ember_t -= dt
        if self.ember_t <= 0:  # rare spark drifting up from the lanterns below
            self.ember_t = random.uniform(2.5, 6.0)
            self.particles.lantern_ember()

    def draw(self, screen, extra=None):
        """Draw the world in layers: wall, stains, shadows, halves, whole fruit, `extra` (scene-specific drawing), particles, slash flashes and shockwave rings.
        Glowing things go on `app.add`, a separate layer that gets added on top (and bloomed on the GPU).
        """
        add = self.app.add  # cleared once per frame by App
        L = self.layer
        L.blit(self.bg, (0, 0))
        self.stains.draw(L)
        for h in self.halves:
            h.draw_shadow(L)
        for b in self.bodies:
            if b.alive:
                b.draw_shadow(L)
        for h in self.halves:
            h.draw(L)
        for b in self.bodies:
            if b.alive:
                if b.special:  # aura + slowly turning light rays, all emissive so the bloom picks them up
                    col = b.ft.juice
                    pulse = 0.8 + 0.2 * math.sin(self.t * 6)
                    rays = pygame.transform.rotate(ray_burst(int(b.r * 3.4), shade(col, 0.6)), self.t * 22)
                    add.blit(rays, rays.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
                    g = glow(self.art, b.r * 1.9, col, 0.55 * pulse)
                    add.blit(g, g.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
                b.draw(L)
        if extra:
            extra(L, add)
        self.particles.draw(L, add)
        for x, y, dx, dy, r, age in self.slashes:
            k = 1 - age / 0.16
            c = (int(200 * k), int(200 * k), int(190 * k))
            pygame.draw.line(add, c, (x - dx * r * 1.4, y - dy * r * 1.4), (x + dx * r * 1.4, y + dy * r * 1.4), max(1, int(4 * k)))
        for x, y, age in self.rings:  # the shockwave's visible front: same radius as the GPU distortion ring
            k = age / self.SHOCK
            # on the GPU the distortion carries the wave, so its glowing front stays faint
            c = shade((255, 190, 120), (0.55 if self.app.gpu is None else 0.2) * (1 - k) ** 2)
            pygame.draw.circle(add, c, (x, y), 20 + k * 0.6 * H, max(1, int(10 * (1 - k))))
        ox, oy = self.shake.offset()
        rox, roy = round(ox), round(oy)
        if self.app.gpu is None:  # the GPU path composites (and blooms) the glow layer itself
            L.blit(add, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        elif rox or roy:  # shake the world's glow with the world (the blade, drawn later by App, stays put)
            add.scroll(rox, roy)
            add.fill((0, 0, 0), (0 if rox > 0 else W + rox, 0, abs(rox), H))
            add.fill((0, 0, 0), (0, 0 if roy > 0 else H + roy, W, abs(roy)))
        if rox or roy:
            screen.fill(LACQUER)
        screen.blit(L, (rox, roy))

    def draw_overlay(self, screen):
        """Draw stamps and popups on the UI layer, above all post-processing."""
        ui = self.app.ui  # stamps and popups are UI: they sit above the post-processing, never warped or graded
        for s in self.stamps:
            s.draw(ui)
        self.popups.draw(ui)
        if self.flash > 0 and self.app.gpu is None:  # on the GPU the flash is a post-fx param
            screen.fill((int(255 * self.flash),) * 3, special_flags=pygame.BLEND_RGB_ADD)

    def fx_params(self):
        """Post-fx for this frame (see PostFX.render); every value decays back to neutral on its own."""
        k = self.slow_k()
        z, age = self.punch
        punch = 1.0 + (z - 1.0) * (1 - age / self.PUNCH) ** 2 if age < self.PUNCH else 1.0
        ox, oy = self.shake.offset()
        shocks, aberration = [], 0.0
        for x, y, age in self.shocks[-2:]:
            u = age / self.SHOCK
            shocks.append(((x + ox) / W, (y + oy) / H, 0.6 * u, 0.04 * (1 - u)))
            aberration = max(aberration, 0.012 * (1 - u))
        return {"zoom": max(punch, 1.0 + 0.03 * k), "shocks": shocks, "aberration": aberration,
                "saturation": 1.0 - 0.35 * k, "flash": self.flash}


class SliceButton:
    """A fruit you cut to choose. Menus in this dojo have no buttons."""

    def __init__(self, world, kind, x, y, glyph, title, sub="", sub2="", ring=80):
        """Create a fruit that hangs in place and acts as a menu choice when you slice it."""
        self.world, self.kind = world, kind
        self.x, self.y = x, y
        self.glyph, self.title, self.sub, self.sub2 = glyph, title, sub, sub2
        self.ring = ring
        self.body = world.throw(kind, x, y, 0, 0, static=True)
        self.t = random.uniform(0, 6)
        self.cut_at = None
        self.hover = 0.0

    def update(self, dt, segments, mouse=None):
        """Bob the fruit gently, glow when the cursor is near, and return True if a blade stroke just cut it."""
        self.t += dt
        near = mouse is not None and math.dist(mouse, (self.x, self.y)) < self.ring + 20
        self.hover = min(1.0, self.hover + dt * 6) if near else max(0.0, self.hover - dt * 4)
        if self.body.alive:
            self.body.y = self.y + math.sin(self.t * 1.8) * 4
            for seg in segments:
                if seg_hits_circle(*seg, self.body.x, self.body.y, self.body.r * 1.25):
                    self.cut(*seg)
                    return True
        return False

    def cut(self, ax=None, ay=None, bx=None, by=None):
        """The fruit is cut and its seal stamped; with no segment (a key press) the cut is a diagonal stroke."""
        if not self.body.alive:
            return
        if ax is None:
            ax, ay, bx, by = self.x - 80, self.y - 60, self.x + 80, self.y + 60
        self.world.cut(self.body, ax, ay, bx, by)
        self.world.stamp(self.glyph, self.title, self.x, self.y - 10, 110)
        self.cut_at = self.t

    def draw(self, surf):
        """Draw the ring, seal and text labels around the fruit."""
        f = self.world.art.fonts
        R = self.ring
        ring = hairline_ring(R)
        if self.cut_at is None:
            ring.set_alpha(int(110 + 145 * self.hover))
            surf.blit(ring, ring.get_rect(center=(self.x, self.y)))
        else:  # the ring opens out and is gone, like a ripple from the cut
            u = min(1.0, (self.t - self.cut_at) / 0.35)
            if u < 1:
                img = pygame.transform.smoothscale_by(ring, 1 + 0.25 * u)
                img.set_alpha(int(255 * (1 - u)))
                surf.blit(img, img.get_rect(center=(self.x, self.y)))
        seal = self.world.art.seal(self.glyph, 40)
        surf.blit(seal, seal.get_rect(center=(self.x - R * 0.74, self.y - R * 0.74)))
        y = self.y + R + 34
        label(surf, f, f.mode, self.title, WASHI, (self.x, y), tracking=1)
        if self.sub:
            label(surf, f, f.mono15, self.sub, MUTED, (self.x, y + 34))
        if self.sub2:
            label(surf, f, f.best, self.sub2, GOLD, (self.x, y + 64))


class Scene:
    """Base class for a screen of the game (menu, play, game over). Each screen overrides the methods it needs; these defaults do nothing."""
    def handle(self, e):
        """Respond to one input event (key press, click...)."""
        pass

    def update(self, dt):
        """Advance this screen by `dt` seconds."""
        pass

    def draw(self, screen):
        """Draw this screen."""
        pass

    def focus_lost(self):
        """Called when the window loses focus (a good moment to pause)."""
        pass

    def fx_params(self):
        """Settings for the GPU screen effects; empty means a plain, unmodified picture."""
        return {}  # neutral post-processing


# ---------------- menu ----------------

class Menu(Scene):
    """The title screen: four fruit to slice to pick a game mode, plus the blade picker."""
    SETTLE = 1.2  # s for the background to drift from 1.04x to rest

    def __init__(self, app):
        """Build the world, the four mode fruit and the title intro. The background is made slightly oversize so it can drift without showing an edge."""
        self.app = app
        self.w = World(app)
        best = app.save["best"]
        self.buttons = []
        for (mode, kind), x in zip((("classic", "watermelon"), ("arcade", "dragonfruit"), ("zen", "peach"), ("path", "golden")),
                                   (W * 0.17, W * 0.39, W * 0.61, W * 0.83)):
            m = MODES[mode]
            b = SliceButton(self.w, kind, x, 388, m["glyph"], m["title"], m["hint"], f"Best {best[mode]}")
            b.mode = mode
            self.buttons.append(b)
        self.chosen = None
        self.t = 0.0
        self.arrow_rects = []
        # background: held slightly oversize so it can drift with the mouse without showing an edge
        self.bg_src = self.w.bg
        self.bg_base = 1.03
        self.bg_rest = pygame.transform.smoothscale_by(self.bg_src, self.bg_base)
        self.par = [0.0, 0.0]
        self.set_bg()
        self.intro = TitleIntro(app, self.w)

    @property
    def intro_done(self):
        """True once the title animation has finished."""
        return self.intro.done

    def set_bg(self):
        """Entry drift (1.04x -> 1.0x of rest scale, eased) then a gentle parallax against the mouse."""
        u = min(1.0, self.t / self.SETTLE)
        if u < 1.0:
            k = 1 + 0.04 * (1 - u) ** 3
            big = pygame.transform.smoothscale_by(self.bg_src, self.bg_base * k)
        else:
            big = self.bg_rest
        bw, bh = big.get_size()
        x = int(min(max((bw - W) / 2 + self.par[0], 0), bw - W))
        y = int(min(max((bh - H) / 2 + self.par[1], 0), bh - H))
        self.w.bg = big.subsurface((x, y, W, H))

    def unlocked(self):
        """Names of the blades unlocked by the player's best score in any mode."""
        top = max(self.app.save["best"].values())
        return [n for n, b in BLADES.items() if top >= b[3]]

    def cycle_blade(self, step):
        """Switch to the next (+1) or previous (-1) unlocked blade, skipping locked ones, and save the choice."""
        names = list(BLADES)
        i = names.index(self.app.save["blade"])
        for _ in range(len(names)):
            i = (i + step) % len(names)
            if names[i] in self.unlocked():
                break
        self.app.save["blade"] = names[i]
        write_save(self.app.save)
        self.app.audio.play("swoosh", 0.6)

    def handle(self, e):
        """Menu input: number keys pick a mode, arrows or mouse wheel change blade, Esc quits."""
        if e.type == pygame.KEYDOWN:
            self.intro.skip()  # any key skips the intro (and still does what it does)
            if e.key == pygame.K_ESCAPE:
                self.app.running = False
            elif pygame.K_1 <= e.key <= pygame.K_4 and not self.chosen:
                b = self.buttons[e.key - pygame.K_1]
                b.cut()
                self.chosen, self.chosen_t = b.mode, 0.0
            elif e.key in (pygame.K_LEFT, pygame.K_a):
                self.cycle_blade(-1)
            elif e.key in (pygame.K_RIGHT, pygame.K_d):
                self.cycle_blade(1)
        elif e.type == pygame.MOUSEWHEEL:
            self.cycle_blade(-1 if e.y > 0 else 1)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for step, r in self.arrow_rects:
                if r.collidepoint(e.pos):
                    self.cycle_blade(step)

    def update(self, dt):
        """Animate the parallax background, run the intro, and watch for a mode fruit being cut; a short delay later the chosen game starts."""
        self.t += dt
        mx, my = self.app.mouse
        tx, ty = -(mx / W - 0.5) * 20, -(my / H - 0.5) * 20  # +-10 px, against the cursor like a deeper layer
        k = min(1.0, dt * 3)
        self.par[0] += (tx - self.par[0]) * k
        self.par[1] += (ty - self.par[1]) * k
        self.set_bg()
        if self.app.speed > 1500:  # a fast swipe skips the intro too
            self.intro.skip()
        self.w.update(dt, dt)
        self.intro.update(dt)
        for b in self.buttons:
            if b.update(dt, self.app.segments, self.app.mouse) and not self.chosen:
                self.chosen, self.chosen_t = b.mode, 0.0
        if self.chosen:
            self.chosen_t += dt
            if self.chosen_t > 0.6:
                mode = self.chosen
                self.chosen = None
                self.app.go(lambda: Play(self.app, mode))

    def fx_params(self):
        """Pass the world's screen effects through to the GPU."""
        return self.w.fx_params()

    def draw(self, screen):
        """Draw the world with the title intro, then the buttons, blade picker and help text on the UI layer."""
        f = self.app.art.fonts
        ui = self.app.ui
        self.w.draw(screen, self.intro.draw_world)
        self.intro.draw_ui(ui)
        for b in self.buttons:
            b.draw(ui)
        # blade picker: small, bottom-left
        name = self.app.save["blade"]
        x0, y = 48, H - 66
        label(ui, f, f.mono12, "BLADE", MUTED, (x0, y - 30), "midleft", tracking=4)
        self.arrow_rects = []
        prev = pygame.Rect(0, 0, 36, 36)
        prev.center = (x0 + 4, y)
        nm = label(ui, f, f.best, name, WASHI, (x0 + 24, y), "midleft")
        nxt = pygame.Rect(0, 0, 36, 36)
        nxt.center = (nm.right + 20, y)
        for step, rr in ((-1, prev), (1, nxt)):
            self.arrow_rects.append((step, rr))
            cx, cy = rr.center
            img = chevron(step, MUTED)
            ui.blit(img, img.get_rect(center=(cx, cy)))
        swatch = pygame.Surface((22, 2))
        swatch.fill(BLADES[name][1])
        ui.blit(swatch, (nxt.right + 4, y - 1))
        if self.app.gpu:  # glow on the GPU only: emit() would draw it onto the CPU frame a second time
            self.app.add.blit(swatch, (nxt.right + 4, y - 1), special_flags=pygame.BLEND_RGB_ADD)
        locked = [(n, b[3]) for n, b in BLADES.items() if n not in self.unlocked()]
        hint = f"Next: {locked[0][0]} at best {locked[0][1]}" if locked else "All blades unlocked"
        label(ui, f, f.mono13, hint, MUTED, (x0, y + 28), "midleft")
        # controls: bottom-right, quiet
        label(ui, f, f.mono13, "Move the cursor fast to slice a fruit", MUTED, (W - 48, y), "midright")
        label(ui, f, f.mono13, "1–4 quick start  ·  ← → blade  ·  M mute  ·  F11 fullscreen" + "  ·  Esc quit",
              MUTED, (W - 48, y + 28), "midright")
        self.w.draw_overlay(screen)


# ---------------- play ----------------

class Play(Scene):
    """The game itself: spawning waves of fruit, slicing, scoring, combos, lives, timers and all the mode-specific rules."""
    def __init__(self, app, mode):
        """Set up a fresh run for `mode`, turning on only the systems that mode uses (powers, fever, boss, hazards)."""
        self.app, self.mode = app, mode
        self.features = MODE_FEATURES[mode]
        self.ki, self.power, self.last_power = KiMeter() if "powers" in self.features else None, None, "timestop"
        self.fever = Fever() if "fever" in self.features else None
        self.boss = BossDirector() if "boss" in self.features else None
        self.hz, self.blade_frozen = Hazards(), 0.0  # blade_frozen: s left of an ice bomb's frozen blade
        self.w = World(app)
        self.score = 0
        self.best_prev = app.save["best"][mode]
        self.strikes = 0
        self.strike_pop = [0.0, 0.0, 0.0]
        self.misses = []  # red X where a fruit dropped
        self.time = {"classic": None, "arcade": 60.0, "zen": 90.0, "path": None}[mode]
        self.elapsed = 0.0
        self.spawn_t = 1.3
        self.queue = []
        self.combo, self.combo_t, self.combo_pos = 0, 0.0, (0, 0)
        self.freeze = self.frenzy = self.double = 0.0
        self.frenzy_spawn = 0.0
        self.special_cd = 7.0
        self.life_every = 150 if mode == "path" else 100  # classic: a strike back per 100; path: a life per 150
        self.next_life = self.life_every
        self.stats = {"sliced": 0, "best_combo": 0, "bombs": 0, "missed": 0}
        self.state, self.state_t = "ready", 0.0
        self.paused = False
        self.pause_bg = None  # blurred snapshot, made on the first paused frame
        self.shown = 0.0  # the score as displayed: rolls toward self.score
        self.last_tick = None
        m = MODES[mode]
        self.w.stamp(m["glyph"], "Ready", W / 2, H / 2 - 20, 150)
        app.audio.play("gong")

    # --- spawning ---
    def launch(self, kind, x=None):
        """Throw one fruit or bomb up from below the screen. The physics picks an upward speed so it peaks at a random height: from v^2 = 2*g*height, so vy = -sqrt(2*g*h)."""
        if launch_hazard(self, kind, x):  # a shuriken flies on its own
            return
        r = 38 if kind in ("bomb", "icebomb") else FRUITS[kind].r
        x0 = x if x is not None else random.uniform(W * 0.12, W * 0.88)
        y0 = H + r + 10
        apex = random.uniform(H * 0.07, H * 0.42)
        vy = -math.sqrt(2 * GRAVITY * (y0 - apex))
        t = -vy / GRAVITY
        xa = min(max(x0 + random.uniform(-W * 0.25, W * 0.25), W * 0.18), W * 0.82)
        self.w.throw(kind, x0, H - y0 if self.w.gflip < 0 else y0, (xa - x0) / t, -vy if self.w.gflip < 0 else vy)  # flipped: from the top
        self.app.audio.play("throw", 0.5)

    def wave(self):
        """Plan the next group of items: how many, which kinds (with some chance of bombs and hazards) and a launch pattern. They go into a queue with delays."""
        e = self.elapsed
        hi = min(6, 1 + int(e / 12) + (1 if self.mode != "classic" else 0))
        n = random.randint(1, hi)
        bomb_p = 0.0 if self.mode == "zen" else (min(0.3, 0.06 + e * 0.0025) if self.mode == "classic" else 0.15)
        kinds = [random.choices(REGULAR, WEIGHTS)[0] for _ in range(n)]
        for i in range(n):
            if random.random() < bomb_p and (i > 0 or (n == 1 and e > 15)):
                kinds[i] = "bomb"
        if all(k == "bomb" for k in kinds):
            kinds[0] = random.choices(REGULAR, WEIGHTS)[0]
        kinds = [roll_hazard(random, e) or k for k in kinds] if "hazards" in self.features else kinds
        if self.mode == "arcade" and self.special_cd <= 0 and random.random() < 0.45:
            kinds[0] = random.choice(SPECIALS)
            self.special_cd = 8.0
        pattern = random.choice(("burst", "stagger", "stagger", "line"))
        xs = sorted(random.uniform(W * 0.12, W * 0.88) for _ in kinds)
        if random.random() < 0.5:
            xs.reverse()
        for i, (k, x) in enumerate(zip(kinds, xs)):
            delay = {"burst": 0.0, "stagger": i * random.uniform(0.18, 0.32), "line": i * 0.11}[pattern]
            self.queue.append([delay, k, x])

    def interval(self):
        """Seconds to wait before the next wave. It gets shorter as the run goes on, so the game speeds up, down to a per-mode minimum."""
        e = self.elapsed
        return {"classic": max(0.85, 2.2 - e * 0.016), "arcade": max(0.6, 1.4 - e * 0.012), "zen": max(0.9, 1.7 - e * 0.008),
                "path": max(0.75, 2.0 - e * 0.014)}[self.mode]

    # --- scoring ---
    def add_score(self, n):
        """Add points. Reaching each score milestone gives back a lost life in classic and path modes."""
        self.score += n
        if self.mode in ("classic", "path"):
            while self.score >= self.next_life:
                self.next_life += self.life_every
                if self.strikes > 0:
                    self.strikes -= 1
                    self.w.popups.add("+1 life", W - 120, 166, GOLD, True)  # rises 54 px: stays clear of the marks
                    self.app.audio.play("life")

    def hit(self, b, seg):
        """The blade just touched body `b` along stroke `seg`: handle hazards, bombs, then scoring, combo counting and power-up fruit."""
        w = self.w
        if hazard_hit(self, b, seg):  # ice bomb, and the golden fruit's first hits
            return
        if b.bomb:
            w.explode(b)
            self.stats["bombs"] += 1
            self.fever and self.fever.reset()
            if self.mode == "classic":
                self.state, self.state_t = "dying", 0.0
                self.app.audio.fuse(False)
            elif self.mode == "path":
                self.lose_life(b.x, "bomb")
            else:
                self.score = max(0, self.score - 10)
                w.popups.add("-10", b.x, b.y - 40, HANKO, True)
            return
        w.cut(b, *seg)
        on_cut(self, b)  # Ki, and Dragon Fire's ignition
        fever_cut(self)  # the chain grows before the cut is scored: the cut that starts Fever already pays x5
        crit = self.mode == "arcade" and not b.special and random.random() < 0.06
        pts = b.points * (2 if self.double > 0 else 1) + 10 * crit
        pts = self.fever.points(pts) if self.fever else pts
        if crit:
            w.popups.add(f"Critical +{self.fever.points(10) if self.fever else 10}", b.x, b.y - 50, GOLD, True)
            w.particles.sparks(b.x, b.y, GOLD, 30, 600)
            w.hitstop = max(w.hitstop, 0.06)
        else:
            w.popups.add(f"+{pts}", b.x, b.y - 30, GOLD if pts > b.ft.points else WASHI)
        self.add_score(pts)
        self.stats["sliced"] += 1
        self.combo += 1
        self.combo_t = 0.28
        if self.combo == 3:  # the camera answers a combo the moment it happens, not when it's tallied
            w.zoom_punch(1.015)
        elif self.combo == 4:
            w.slow()
        self.combo_pos = (b.x, b.y)
        if b.special:
            name, glyph, cap, dur = {"freeze": ("freeze", "凍", "Freeze", 6.0), "frenzy": ("frenzy", "嵐", "Frenzy", 4.5),
                                     "double": ("double", "倍", "Double score", 8.0)}[b.special]
            setattr(self, name, dur)
            w.stamp(glyph, cap, b.x, b.y, 120)
            w.particles.sparks(b.x, b.y, b.ft.juice, 50, 800)
            self.app.audio.play("power")

    def slice(self):
        """Check every blade stroke this frame against every fruit and boss."""
        if slice_hazards(self):  # parries shurikens; True while an ice bomb has frozen the blade
            return
        slice_boss(self)  # the boss is never in w.bodies (no power targets it); its own hits, here
        for seg in () if self.power and self.power.blocks_slicing else self.app.segments:
            for b in self.w.bodies:
                if b.alive and seg_hits_circle(*seg, b.x, b.y, b.r * 1.05):
                    self.hit(b, seg)
                    if self.state != "play":
                        return

    def finish_combo(self):
        """The quick run of cuts has ended: award a bonus if it was 3 or more fruit and show a combo stamp."""
        if self.combo >= 3:
            bonus = self.combo * (2 if self.double > 0 else 1)
            bonus = self.fever.points(bonus) if self.fever else bonus
            self.add_score(bonus)
            if self.ki:
                self.ki.add(KI_PER_COMBO * self.combo)
            self.w.stamp("連", f"{self.combo} fruit combo", *self.combo_pos, 100 + min(60, self.combo * 6), bonus=f"+{bonus}")
            self.w.hitstop = max(self.w.hitstop, 0.05)
            self.app.audio.play("combo")
        self.stats["best_combo"] = max(self.stats["best_combo"], self.combo)
        self.combo = 0

    @property
    def lives(self):
        """Path mode's lives are the classic strike marks counted the other way (None in the other modes)."""
        return 3 - self.strikes if self.mode == "path" else None

    def strike(self, b):
        """A fruit was dropped without being cut: count the miss and, in some modes, lose a life."""
        self.stats["missed"] += 1
        if self.fever and not self.fever.active:  # a drop breaks the chain, but never a running Fever
            self.fever.reset()
        if self.mode in ("classic", "path"):
            self.lose_life(b.x, "drop")

    def lose_life(self, x, reason):
        """A strike (classic) or a lost life (path; `reason` is "drop" or "bomb"): a red brush mark where it happened."""
        if self.state != "play":
            return
        if self.fever and (reason != "drop" or not self.fever.active):
            self.fever.reset()
        self.strike_pop[self.strikes] = 0.35
        self.strikes += 1
        self.misses.append([min(max(x, 40), W - 40), 0.0])
        self.w.shake.kick(0.3)
        self.app.audio.play("miss")
        if self.strikes >= 3:
            self.state, self.state_t = "dying", 0.0

    # --- loop ---
    def handle(self, e):
        """Play input: Esc or P pauses, Q (while paused) quits to the menu, Q/W/E or right-click use a power."""
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_p):
                self.paused = not self.paused
            elif self.paused and e.key == pygame.K_q:
                self.app.audio.quiet()
                self.app.go(lambda: Menu(self.app))
            elif e.key in POWER_KEYS:  # use_power refuses unless playing, unpaused and full
                self.use_power(POWER_KEYS[e.key])
        elif e.type == pygame.MOUSEBUTTONDOWN and self.paused and e.button == 1:
            self.paused = False
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
            self.use_power(self.last_power)

    use_power = use_power
    throw_shuriken = throw_shuriken

    def focus_lost(self):
        """Pause automatically if the player switches to another window mid-run."""
        if self.state == "play":
            self.paused = True

    def fx_params(self):
        """Screen-effect settings for this frame, tweaked by freeze, powers and Fever. Plain while paused."""
        if self.paused:
            return {}
        p = self.w.fx_params()
        if self.freeze > 0:  # the cold grade also drains a little colour on the GPU
            p["saturation"] *= 1 - 0.2 * min(1.0, self.freeze / 0.6)
        if self.power:
            self.power.fx(p)
        fever_fx(self, p)
        return p

    def update(self, dt):
        """The main game tick. Order matters: timers and powers first, then the state machine (ready -> play -> dying/ending -> over), spawning, slicing, then cleanup of fruit that fell."""
        if self.paused:
            self.app.audio.quiet()
            return
        self.pause_bg = None
        w = self.w
        tick_power(self, dt)
        tick_fever(self, dt)
        # game clock: freeze slows (Time Stop stops) the timer, spawning and difficulty ramp; slow-mo only the world
        wdt = dt * (0.4 if self.freeze > 0 else 1.0) * w.power_scale
        w.update(wdt * w.time_scale(), dt)
        # rolling counter: ease toward the real score (also downward after a bomb), snapping once close
        self.shown += (self.score - self.shown) * min(1.0, dt * 12)
        if abs(self.score - self.shown) < 0.5:
            self.shown = float(self.score)
        self.strike_pop = [max(0.0, p - dt) for p in self.strike_pop]
        for m in self.misses:
            m[1] += dt
        self.misses = [m for m in self.misses if m[1] < 1.2]
        self.state_t += dt
        if w.hitstop > 0:
            if self.state == "play":
                self.slice()  # hit-stop freezes the picture, never the blade: a swipe through it still cuts
            return
        if self.state == "ready" and self.state_t > 1.1:
            self.state, self.state_t = "play", 0.0
        if self.state == "play":
            self.elapsed += wdt
            self.freeze, self.frenzy, self.double = (max(0.0, v - dt * w.power_scale) for v in (self.freeze, self.frenzy, self.double))
            self.special_cd -= dt * w.power_scale  # real time, but Time Stop holds it
            if self.time is not None:
                self.time -= wdt
                if 0 < self.time <= 5 and math.ceil(self.time) != self.last_tick:
                    self.last_tick = math.ceil(self.time)
                    self.app.audio.play("tick")
                if self.time <= 0:
                    self.time = 0.0
                    self.state, self.state_t = "ending", 0.0
                    w.stamp("時", "Time's up", W / 2, H / 2 - 20, 150)
                    self.app.audio.play("gong")
            for q in self.queue:
                q[0] -= wdt
                if q[0] <= 0:
                    self.launch(q[1], q[2])
            self.queue = [q for q in self.queue if q[0] > 0]
            self.spawn_t -= wdt
            if self.spawn_t <= 0 and not self.queue and not (self.boss and self.boss.pause_waves):
                self.wave()
                self.spawn_t = self.interval()
            if self.frenzy > 0:
                self.frenzy_spawn -= dt * w.power_scale
                if self.frenzy_spawn <= 0:
                    self.frenzy_spawn = 0.09
                    side = random.choice((-1, 1))
                    kind = random.choices(REGULAR, WEIGHTS)[0]
                    x0 = -40 if side < 0 else W + 40
                    w.throw(kind, x0, random.uniform(H * 0.4, H * 0.85), -side * random.uniform(380, 700), -random.uniform(450, 850))
            self.slice()
            if self.combo:
                self.combo_t -= dt
                if self.combo_t <= 0:
                    self.finish_combo()
        tick_boss(self, wdt * w.time_scale())  # world time: Time Stop and hit-stop hold it
        tick_hazards(self, dt)
        for b in w.bodies:
            if b.alive and b.gone():
                b.alive = False
                if b.costly and not b.rain and b.entered:
                    self.strike(b)
        w.bodies = [b for b in w.bodies if b.alive]
        # bomb fuses fizz
        bombs = [b for b in w.bodies if b.bomb]
        for b in bombs if w.power_scale else ():
            tx, ty = rotate_vec(*self.app.art.bomb_tip, b.ang)
            w.particles.add(b.x + tx, b.y + ty, random.uniform(-90, 90), random.uniform(-160, -20), 0.25, 2, (255, 210, 120), "spark", 0.3)
            if random.random() < 0.5:
                w.particles.add(b.x + tx, b.y + ty, 0, 0, 0.12, 9, (255, 140, 40), "glow", 0)
        self.app.audio.fuse(bool(bombs) and self.state == "play")
        if self.state == "dying" and self.state_t > 1.7:
            self.end()
        elif self.state == "ending" and self.state_t > 2.0:
            self.end()

    def end(self):
        """The run is over: save the best score, then wipe to the game-over screen."""
        self.state = "over"
        if self.combo:
            self.finish_combo()
        save = self.app.save
        save["best"][self.mode] = max(save["best"][self.mode], self.score)
        save["total_sliced"] += self.stats["sliced"]
        write_save(save)
        self.app.audio.quiet()
        snap = self.app.snapshot()
        self.app.go(lambda: GameOver(self.app, self, snap))

    def draw_world_extra(self, L, add):
        """Mode-specific things drawn inside the world layer: red miss marks, the boss, hazards and the running power."""
        for x, age in self.misses:  # a red brush mark where the fruit fell
            k = min(1.0, age / 0.12)
            a = int(255 * min(1.0, (1.2 - age) / 0.4))
            img = brush_x(44, HANKO)
            if k < 1:
                img = pygame.transform.smoothscale_by(img, 1.5 - 0.5 * k)
            img.set_alpha(a)
            L.blit(img, img.get_rect(center=(x, H - 46)))
        self.boss and self.boss.draw(L, add)
        draw_hazards(self, L, add)
        if self.power:
            self.power.draw(L, add, self.app.ui)

    def draw_pause(self, screen):
        """Draw the frosted "Paused" screen."""
        f = self.app.art.fonts
        ui = self.app.ui
        if self.pause_bg is None:  # the world is frozen: blur it (with its HUD) once, not every frame
            snap = screen.copy()
            if self.app.gpu:
                snap.blit(self.app.add, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            snap.blit(ui, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)  # (CPU: flattened only after draw)
            self.pause_bg = blurred(snap, (120, 114, 110))
        screen.blit(self.pause_bg, (0, 0))
        self.app.add.fill((0, 0, 0))  # no glow bleeding through the frosted glass
        ui.fill(UI_CLEAR)  # the HUD is in the blur now
        label(ui, f, f.pause, "Paused", WASHI, (W / 2, H / 2 - 28), tracking=2)
        line = pygame.Surface((64, 1))
        line.fill(GOLD)
        ui.blit(line, (W / 2 - 32, H / 2 + 24))
        label(ui, f, f.mono15, "Click or Esc to resume  ·  Q to quit to menu", MUTED, (W / 2, H / 2 + 58))

    def draw(self, screen):
        """Draw the world, colour grades, HUD and any popups; or the pause screen if paused."""
        w = self.w
        if self.paused and self.pause_bg is not None:
            self.draw_pause(screen)
            return
        w.draw(screen, self.draw_world_extra)
        draw_grades(self, screen)  # power-up and Fever grades go under the HUD, never over its text
        draw_play_hud(self, self.app.ui)
        w.draw_overlay(screen)
        if self.paused:
            self.draw_pause(screen)


# ---------------- game over ----------------

class GameOver(Scene):
    """The results screen: final score counting up, stats, and two fruit to slice for Retry or Menu."""
    COUNT_AT, COUNT = 0.45, 1.3  # the score counts up once the 終 seal has landed

    def __init__(self, app, play, snap):
        """Show the finished run over a blurred snapshot of the last frame."""
        self.app, self.play = app, play
        self.w = World(app, blurred(snap, (100, 92, 88)))
        self.t = 0.0
        self.new_best = play.score > play.best_prev and play.score > 0
        self.retry = SliceButton(self.w, "watermelon", W * 0.38, 548, "再", "Retry", "or press Enter", ring=72)
        self.menu = SliceButton(self.w, "apple", W * 0.62, 548, "戻", "Menu", "or press Esc", ring=72)
        self.choice = None
        self.stamped = 0
        self.shown = 0.0

    def handle(self, e):
        """Keyboard shortcuts: Enter/R/Space to retry, Esc for the menu."""
        if e.type == pygame.KEYDOWN and not self.choice:
            if e.key in (pygame.K_RETURN, pygame.K_r, pygame.K_SPACE):
                self.retry.cut()  # the same answer a swipe gets: the fruit splits and its seal lands
                self.choose("retry")
            elif e.key == pygame.K_ESCAPE:
                self.menu.cut()
                self.choose("menu")

    def choose(self, c):
        """Remember the player's choice; the update loop acts on it after a short delay."""
        self.choice, self.choice_t = c, 0.0

    def update(self, dt):
        """Run the timeline: score count-up, seal stamps, then watch for a choice and switch screens."""
        self.t += dt
        self.w.update(dt, dt)
        u = min(1.0, max(0.0, (self.t - self.COUNT_AT) / self.COUNT))
        self.shown = self.play.score * (1 - (1 - u) ** 3)  # fast at first, easing onto the final number
        if self.stamped == 0 and self.t > 0.2:
            self.stamped = 1
            over = "Time's up" if self.play.time is not None else "Game over"
            self.w.stamp("終", over, W / 2, 104, 88, hold=True)
        if self.stamped == 1 and self.new_best and self.t > self.COUNT_AT + self.COUNT:
            self.stamped = 2
            self.w.stamp("極", "New best", W / 2 + 300, 280, 104, hold=True)
            self.w.particles.sparks(W / 2 + 300, 280, GOLD, 60, 700)
            self.app.audio.play("power")
        if self.t > 0.6 and not self.choice:
            if self.retry.update(dt, self.app.segments, self.app.mouse):
                self.choose("retry")
            elif self.menu.update(dt, self.app.segments, self.app.mouse):
                self.choose("menu")
        if self.choice:
            self.choice_t += dt
            if self.choice_t > 0.55:
                c, self.choice = self.choice, None
                mode = self.play.mode
                self.app.go((lambda: Play(self.app, mode)) if c == "retry" else (lambda: Menu(self.app)))

    def fx_params(self):
        """Pass the world's screen effects through to the GPU."""
        return self.w.fx_params()

    def draw(self, screen):
        """Draw the score, best, stats row and buttons."""
        f = self.app.art.fonts
        self.w.draw(screen)
        ui = self.app.ui  # everything over the blurred wall is UI
        p = self.play
        if self.t > self.COUNT_AT:
            sr = label(ui, f, f.final, str(round(self.shown)), GOLD, (W / 2, 290))
            best = self.app.save["best"][p.mode]
            label(ui, f, f.mono12, f"{MODES[p.mode]['title'].upper()}  ·  BEST {best}", MUTED, (W / 2, sr.bottom + 6),
                  tracking=3)
            # stats row: quiet labels, the numbers in paper white
            parts = [("Sliced", p.stats["sliced"]), ("Best combo", p.stats["best_combo"]), ("Bombs", p.stats["bombs"])]
            imgs = []
            for name, val in parts:
                imgs.append((f.text(f.mono15, name + " ", MUTED), f.text(f.mono15, str(val), WASHI)))
            gap = 40
            total = sum(a.get_width() + b.get_width() for a, b in imgs) + gap * (len(imgs) - 1)
            x, y = W / 2 - total / 2, sr.bottom + 40
            for a, b in imgs:
                for im in (a, b):
                    im.set_alpha(255)
                    ui.blit(im, im.get_rect(midleft=(x, y)))
                    x += im.get_width()
                x += gap
        if self.t > 0.6:
            self.retry.draw(ui)
            self.menu.draw(ui)
        self.w.draw_overlay(screen)


# ---------------- transition: the screen is cut in two ----------------

class Wipe:
    """The screen transition: the old picture is cut in two along a slanted line and the halves slide apart, revealing the new screen."""
    DUR = 0.5

    def __init__(self, snap):
        """Split the old picture `snap` into two cut-out pieces along a slanted line."""
        xt, xb = W * 0.62, W * 0.38
        self.pieces, self.polys = [], []
        for poly in ([(0, 0), (xt, 0), (xb, H), (0, H)], [(xt, 0), (W, 0), (W, H), (xb, H)]):
            s = snap.convert_alpha()
            m = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.polygon(m, (255, 255, 255, 255), poly)
            s.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.pieces.append(s)
            self.polys.append(poly)
        L = math.hypot(xb - xt, H)
        self.n = (H / L, -(xb - xt) / L)  # normal pointing right
        self.line = ((xt, 0), (xb, H))
        self.t = 0.0

    def update(self, dt):
        """Advance the transition; returns False when it is finished."""
        self.t += dt
        return self.t < self.DUR

    def draw(self, screen, add=None, cpu=True, ui=None):
        """Slide the two pieces apart and glow along the cut edge. `add` and `ui` are the glow and HUD layers of the new scene, hidden wherever the old picture still covers them."""
        k = min(1.0, self.t / self.DUR)
        e = 1 - (1 - k) ** 3
        d = e * W * 0.8
        nx, ny = self.n
        offs = ((int(-nx * d), int(-ny * d - e * 40)), (int(nx * d), int(ny * d + e * 40)))
        for piece, poly, (ox, oy) in zip(self.pieces, self.polys, offs):
            screen.blit(piece, (ox, oy))
            # the new scene's glow and UI are separate layers: hide them wherever the old picture still covers it
            moved = [(x + ox, y + oy) for x, y in poly]
            if add is not None:
                pygame.draw.polygon(add, (0, 0, 0), moved)
            if ui is not None:
                pygame.draw.polygon(ui, (0, 0, 0, 0), moved)
        # the cut's edge glows and travels with each half, burning out as they part
        c = (1 - k) ** 1.5
        if c <= 0.02:
            return
        (ax, ay), (bx, by) = self.line
        for ox, oy in offs:
            a, b = (ax + ox, ay + oy), (bx + ox, by + oy)
            if add is not None:
                pygame.draw.line(add, shade((255, 200, 140), 0.35 * c), a, b, 9)
                pygame.draw.line(add, shade((255, 244, 225), c), a, b, 2)
            if cpu or add is None:
                pygame.draw.aaline(screen, shade((255, 240, 220), c), a, b)


# ---------------- app ----------------

class App:
    """The whole program: owns the window, the input state, the current screen (Menu / Play / GameOver) and the main loop."""
    def __init__(self):
        """Start pygame and show a loading message, then load art, sound and the save, and open the menu."""
        pygame.init()
        self.fullscreen = False
        self.open_window()
        pygame.display.set_caption(CAPTION)
        self.add = pygame.Surface((W, H))  # emissive layer: glows only, black = none
        self.ui = pygame.Surface((W, H), pygame.SRCALPHA)  # HUD and overlays, premultiplied: laid over after post-fx
        self.ui.fill(UI_CLEAR)
        self.frame.fill(LACQUER)
        f = _font(Fonts.MONO[0], 15, Fonts.MONO[1])
        img = f.render("Sharpening the blade…", True, MUTED)
        self.frame.blit(img, img.get_rect(center=(W / 2, H / 2)))
        self.present({})
        self.art = Art()
        self.audio = Audio()
        pygame.display.set_icon(self.art.fruits["watermelon"].face)
        self.save = load_save()
        if self.save["muted"]:
            self.audio.muted = True
        self.clock = pygame.time.Clock()
        self.trail = Trail()
        self.now = 0.0
        self.speed = 0.0
        self.mouse = (W / 2, H / 2)
        self.segments = []
        self.last_swoosh = 0.0
        self.running = True
        self.wipe = None
        self.scene = Menu(self)
        pygame.mouse.set_visible(False)
        self.audio.start_music()

    def open_window(self):
        """OpenGL window + PostFX when available; otherwise the v2 SCALED window. Sets self.frame and self.gpu."""
        self.gpu = None
        if os.environ.get("NINJA_NO_GPU") != "1":
            try:
                from .gpu import PostFX  # moderngl may not even be installed
                size, mode = ((0, 0), pygame.FULLSCREEN) if self.fullscreen else ((W, H), pygame.RESIZABLE)
                pygame.display.set_mode(size, pygame.OPENGL | pygame.DOUBLEBUF | mode, vsync=1)
                self.gpu = PostFX()
                self.frame = pygame.Surface((W, H))
                return
            except Exception:  # no GL 3.3, no moderngl, headless driver...: fall back to the CPU path
                self.gpu = None
        flags = pygame.SCALED | pygame.RESIZABLE
        try:
            self.frame = pygame.display.set_mode((W, H), flags, vsync=1)
        except pygame.error:
            self.frame = pygame.display.set_mode((W, H), flags)

    def to_logical(self, pos):
        """Window pixels -> 1280x720 through the letterbox (SCALED did this for us on the CPU path)."""
        from .gpu import to_logical
        return to_logical(pos, pygame.display.get_window_size())

    def present(self, params):
        """Show the finished frame: run the GPU effects if available, then flip the screen buffers."""
        if self.gpu:
            self.gpu.render(self.frame, self.add, params, (0, 0, *pygame.display.get_window_size()), ui=self.ui)
        pygame.display.flip()

    def snapshot(self):
        """The last shown picture, bar post-fx (wipes and the game-over backdrop start from it). On the CPU path the
        frame already holds glow and UI; on the GPU path they are still separate layers, so flatten them on."""
        snap = self.frame.copy()
        if self.gpu:
            snap.blit(self.add, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            snap.blit(self.ui, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        return snap

    def go(self, make_scene):
        """Switch to a new screen (built by calling `make_scene`) with the cut-in-two transition from the last picture."""
        snap = self.snapshot()
        self.scene = make_scene()
        self.wipe = Wipe(snap)
        self.audio.play("swoosh", 0.9)

    def frame_step(self):
        """One frame: timing, input + update + draw, present. The desktop loop calls this."""
        dt = min(self.clock.tick(FPS) / 1000, 1 / 20)
        self.step(dt, pygame.event.get())
        self.present(self.scene.fx_params())

    def run(self):
        """The desktop main loop: step frames until the player quits."""
        while self.running:
            self.frame_step()
        pygame.quit()

    def step(self, dt, events):
        """Advance everything one frame: handle input events, turn mouse movement into blade strokes, update and draw the current screen."""
        self.now += dt
        # Mouse movement this frame becomes a list of points; each pair of neighbouring points is a blade segment tested against the fruit.
        pts = [self.mouse]
        for e in events:
            if self.gpu and e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                e.pos = self.to_logical(e.pos)
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                if self.gpu:  # a GL window can't be toggled in place: recreate it and its GL objects
                    self.gpu.release()
                    self.fullscreen = not self.fullscreen
                    self.open_window()
                else:
                    try:
                        pygame.display.toggle_fullscreen()
                    except pygame.error:
                        pass  # unsupported: stay windowed
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_m:
                self.audio.toggle_mute()
                self.save["muted"] = self.audio.muted
                write_save(self.save)
            elif e.type == pygame.MOUSEMOTION:
                if math.dist(pts[-1], e.pos) > MAX_JUMP:  # cursor re-entered the window: don't cut across the screen
                    pts = [e.pos]
                    self.trail.cut()
                else:
                    pts.append(e.pos)
                self.mouse = e.pos
                self.trail.add(*e.pos, self.now)
            elif e.type == pygame.WINDOWFOCUSLOST:
                self.scene.focus_lost()
            if e.type != pygame.QUIT:
                self.scene.handle(e)
        # Blade speed = distance travelled / time. Only fast motion counts as a slice (above SLICE_SPEED).
        self.segments = []
        self.speed = 0.0
        if len(pts) >= 2 and dt > 0:
            path = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
            self.speed = path / dt
            if self.speed > SLICE_SPEED:
                self.segments = [(*a, *b) for a, b in zip(pts, pts[1:]) if a != b]
            if path / dt > 1500 and self.now - self.last_swoosh > 0.18:
                self.last_swoosh = self.now
                self.audio.play("swoosh", 0.55)
        self.trail.update(self.now)
        w = getattr(self.scene, "w", None)
        if w and self.speed > 1500 and len(pts) >= 2:  # sparks thrown off the blade tip on a fast flick
            (ax, ay), (bx, by) = pts[-2], pts[-1]
            L = math.hypot(bx - ax, by - ay) or 1
            col = BLADES[self.save["blade"]][2]
            for _ in range(2):
                sp = random.uniform(120, 420)
                j = random.uniform(-0.6, 0.6)
                vx, vy = -(bx - ax) / L, -(by - ay) / L
                w.particles.add(bx, by, (vx - vy * j) * sp, (vy + vx * j) * sp, random.uniform(0.15, 0.28),
                                random.uniform(1, 1.8), col, "spark", 0.6)
        # Frame order: update the screen, clear the glow and UI layers, draw the screen, then the transition and the blade on top.
        self.scene.update(dt)
        self.add.fill((0, 0, 0))
        self.ui.fill(UI_CLEAR)
        self.scene.draw(self.frame)
        if self.wipe and not self.wipe.update(dt):
            self.wipe = None
        if self.wipe:
            self.wipe.draw(self.frame, self.add, self.gpu is None, self.ui)
        if self.gpu is None:  # the GPU lays the UI over the graded picture itself
            self.frame.blit(self.ui, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        self.draw_blade()

    def draw_blade(self):
        """Draw the glowing blade trail and the cursor on the glow layer."""
        colors = blade_colors(self.scene) or BLADES[self.save["blade"]][:3]
        xs = [p[0] for p in self.trail.pts if p] + [self.mouse[0]]
        ys = [p[1] for p in self.trail.pts if p] + [self.mouse[1]]
        box = pygame.Rect(min(xs) - 40, min(ys) - 40, max(xs) - min(xs) + 80, max(ys) - min(ys) + 80).clip(self.frame.get_rect())
        if not box.w or not box.h:
            return
        if self.gpu is None:
            self.add.fill((0, 0, 0), box)  # the world's glow is already on the frame; don't add it twice
        self.trail.draw(self.add, colors, self.now, outer=self.gpu is None)
        glow = self.art.soft(16 if self.speed > SLICE_SPEED else 11, colors[1], False)
        self.add.blit(glow, glow.get_rect(center=self.mouse), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(self.add, colors[2], self.mouse, 3)
        if self.gpu is None:
            self.frame.blit(self.add, box, box, special_flags=pygame.BLEND_RGB_ADD)
