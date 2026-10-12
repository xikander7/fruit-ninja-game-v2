import json
import math
import os
import random

import pygame

from .art import Art, Fonts, FRUITS, REGULAR, WEIGHTS, SPECIALS, _font
from .audio import Audio
from .entities import Body, Half, seg_hits_circle, rotate_vec
from .fx import Particles, Stains, Trail, Shake, Popups, Stamp, ray_burst, glow, shade
from .settings import W, H, FPS, GRAVITY, SAVE_PATH, WASHI, GOLD, HANKO, MUTED, LACQUER, BLADES, MODES

SLICE_SPEED = 300  # px/s — just moving the cursor slices; a slow drift doesn't
MAX_JUMP = 350  # px in one motion event
# The UI layer is cleared to alpha 1, not 0. pygame blends onto a pixel with any alpha as dst + (src - dst) * a, which
# over black is premultiplied colour, but copies straight colour onto a fully clear pixel; the 1 keeps every pixel
# premultiplied, so text over its own shadow composites exactly as it did drawn straight onto the frame.
UI_CLEAR = (0, 0, 0, 1)


# ---------------- save data ----------------

def load_save():
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
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # missing or corrupt save: start fresh
    return data


def write_save(data):
    try:
        tmp = SAVE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, SAVE_PATH)  # atomic: a crash never leaves half a file
    except OSError:
        pass


def label(surf, fonts, font, s, color, pos, anchor="center", tracking=0, shadow=True, alpha=255):
    """Cached text with a soft shadow, so it reads over the photoreal wall without a hard outline."""
    img = fonts.text(font, s, color, tracking)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = fonts.shadow(font, s, tracking)
        sh.set_alpha(int(alpha * 0.9))
        surf.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
    img.set_alpha(alpha)
    surf.blit(img, r)
    return r


def lerp_rgb(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def emit(app, screen, img, pos):
    """Draw something that glows: into the emissive layer for the GPU bloom, straight onto the frame on the CPU
    path (there the glow layer has already been composited by the time UI is drawn)."""
    app.add.blit(img, pos, special_flags=pygame.BLEND_RGB_ADD)
    if app.gpu is None:
        screen.blit(img, pos, special_flags=pygame.BLEND_RGB_ADD)


def blurred(surf, tint):
    """A frosted backdrop: downscale x8, smooth, upscale, then darken so type sits cleanly on top."""
    small = pygame.transform.smoothscale(surf, (W // 8, H // 8))
    small = pygame.transform.gaussian_blur(small, 2)
    out = pygame.transform.smoothscale(small, (W, H))
    out.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
    return out


_BRUSH = {}


def brush_x(size, color, outline=False):
    """A strike mark painted as two brush strokes: blunt where the brush lands, tapering to a point as it lifts.
    Supersampled 3x for clean edges; cached per (size, colour, outline)."""
    key = (size, color, outline)
    if key in _BRUSH:
        return _BRUSH[key]
    ss = 3
    d = size * ss
    m = pygame.Surface((d, d), pygame.SRCALPHA)
    p = d * 0.1
    for x0, y0, x1, y1, bow, wmax in ((p, p * 1.3, d - p, d - p * 0.8, 0.05, 0.17), (d - p * 1.2, p, p * 1.1, d - p * 1.1, -0.04, 0.14)):
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        left, right = [], []
        for i in range(21):
            t = i / 20
            w = d * wmax * (0.65 + 0.35 * min(1.0, t / 0.18)) * max(0.03, 1 - t ** 1.8) / 2
            cx = x0 + ux * L * t + nx * bow * L * math.sin(math.pi * t)
            cy = y0 + uy * L * t + ny * bow * L * math.sin(math.pi * t)
            left.append((cx + nx * w, cy + ny * w))
            right.append((cx - nx * w, cy - ny * w))
        pygame.draw.polygon(m, (*color, 255), left + right[::-1])
    if outline:  # trace the union of both strokes, so the crossing doesn't show inside an empty mark
        pts = pygame.mask.from_surface(m).outline()
        m = pygame.Surface((d, d), pygame.SRCALPHA)
        if len(pts) > 2:
            pygame.draw.lines(m, (*color, 255), True, pts, ss + 1)
    img = pygame.transform.smoothscale(m, (size, size))
    _BRUSH[key] = img
    return img


_CHEVRONS = {}


def chevron(step, color):
    """A thin < or > (step -1 / 1), anti-aliased by drawing 4x and smoothscaling (aalines only antialias over an
    opaque surface, and the UI layer is transparent)."""
    key = (step, color)
    if key not in _CHEVRONS:
        k = 4
        s = pygame.Surface((12 * k, 18 * k), pygame.SRCALPHA)
        pts = [((6 - 3 * step) * k, 2 * k), ((6 + 4 * step) * k, 9 * k), ((6 - 3 * step) * k, 16 * k)]
        pygame.draw.lines(s, (*color, 255), False, pts, k * 3 // 2)  # 1.5 px: the weight aalines read at
        _CHEVRONS[key] = pygame.transform.smoothscale(s, (12, 18))
    return _CHEVRONS[key]


_RINGS = {}


def hairline_ring(r):
    """A 1 px anti-aliased gold circle (cached: one per radius)."""
    if r not in _RINGS:
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.aacircle(s, GOLD, (r + 2, r + 2), r, 1)
        _RINGS[r] = s
    return _RINGS[r]


# ---------------- world: everything that lives on the dojo wall ----------------

class World:
    PUNCH = 0.25  # s for a combo zoom punch to ease back
    SLOW_HOLD, SLOW_EASE = 0.4, 0.15  # slow-mo: held at full strength, then eased back to real time
    SHOCK = 0.6  # s for a bomb shockwave to cross the screen

    def __init__(self, app, bg=None):
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
        self.mote_t = 0.0
        self.ember_t = random.uniform(1.0, 3.0)
        for _ in range(40):  # the dojo already has dust hanging in the lamplight
            self.particles.mote()

    def throw(self, kind, x, y, vx, vy, static=False):
        b = Body(self.art, kind, x, y, vx, vy, static)
        self.bodies.append(b)
        return b

    def cut(self, b, ax, ay, bx, by):
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
        self.particles.splash(b.x, b.y, b.ft.juice, nx, ny, b.r)  # first, so the droplets draw over it
        self.particles.juice(b.x, b.y, b.ft.juice, nx, ny, spread=b.r * 1.1)  # the whole chord of the cut
        self.stains.add(b.ft.juice, b.r, b.x, b.y)
        self.slashes.append([b.x, b.y, dx, dy, b.r * 1.6, 0.0])
        self.app.audio.play("splat", 0.8)

    def explode(self, b):
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
        self.punch = [zoom, 0.0]

    def slow(self):
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
        return 1.0 - 0.7 * self.slow_k()  # 0.3 at full slow-mo

    def stamp(self, glyph, caption, x, y, size=120, color=WASHI, bonus=None, hold=False):
        self.stamps.append(Stamp(self.art, glyph, caption, x, y, size, color, bonus, hold))

    def update(self, dt, real_dt):
        # camera/post effects run on real time so they play out even through hit-stop and slow-mo
        self.t += real_dt
        self.shake.update(real_dt)
        self.flash = max(0.0, self.flash - real_dt * 6.0)  # a sharp pop; a slow fade reads as fog
        self.slowmo = max(0.0, self.slowmo - real_dt)
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
        for b in self.bodies:
            b.update(dt)
        for h in self.halves:
            h.update(dt)
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
        self.world, self.kind = world, kind
        self.x, self.y = x, y
        self.glyph, self.title, self.sub, self.sub2 = glyph, title, sub, sub2
        self.ring = ring
        self.body = world.throw(kind, x, y, 0, 0, static=True)
        self.t = random.uniform(0, 6)
        self.cut_at = None
        self.hover = 0.0

    def update(self, dt, segments, mouse=None):
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
    def handle(self, e):
        pass

    def update(self, dt):
        pass

    def draw(self, screen):
        pass

    def focus_lost(self):
        pass

    def fx_params(self):
        return {}  # neutral post-processing


# ---------------- menu ----------------

class Menu(Scene):
    SETTLE = 1.2  # s for the background to drift from 1.04x to rest
    SWEEP_AT, SWEEP = 0.25, 0.7  # the katana light crossing the title

    def __init__(self, app):
        self.app = app
        self.w = World(app)
        best = app.save["best"]
        self.buttons = []
        for (mode, kind), x in zip((("classic", "watermelon"), ("arcade", "dragonfruit"), ("zen", "peach")), (W * 0.25, W * 0.5, W * 0.75)):
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
        f = app.art.fonts
        self.title = f.text(f.title, "Fruit Ninja", WASHI, 2)
        self.title_sh = f.shadow(f.title, "Fruit Ninja", 2)
        self.title_rect = self.title.get_rect(center=(W / 2, 122))
        # the same letters, warm white on black: the part under the sweep is added to the glow layer as a glint
        self.title_glint = pygame.Surface(self.title.get_size())
        self.title_glint.blit(f.text(f.title, "Fruit Ninja", (255, 240, 214), 2), (0, 0))
        self.streak = self.make_streak(self.title.get_height() + 70)
        self.band = self.make_band(120)

    @staticmethod
    def make_streak(h):
        """A slanted blade of light: a hot core with a soft falloff, fading out at both tips."""
        w = 48
        s = pygame.Surface((w, h))
        for dx in range(-w // 2, w // 2):
            k = math.exp(-(dx / 3.0) ** 2) + 0.35 * math.exp(-(dx / 11.0) ** 2)
            pygame.draw.line(s, shade((255, 236, 205), min(1.0, k)), (w // 2 + dx, 0), (w // 2 + dx, h))
        fade = pygame.Surface((w, h))
        for y in range(h):
            fade.fill(shade((255, 255, 255), math.sin(math.pi * y / (h - 1)) ** 0.8), (0, y, w, 1))
        s.blit(fade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        return pygame.transform.rotate(s.convert_alpha(), -14)  # alpha: the rotated corners come out clear, not grey

    @staticmethod
    def make_band(w):
        """Horizontal falloff multiplied into the title glint, so only the letters right at the streak catch light."""
        s = pygame.Surface((w, 1))
        for x in range(w):
            s.set_at((x, 0), shade((255, 255, 255), math.exp(-((x - w / 2) / (w / 6)) ** 2)))
        return s

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
        top = max(self.app.save["best"].values())
        return [n for n, b in BLADES.items() if top >= b[3]]

    def cycle_blade(self, step):
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
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.app.running = False
            elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and not self.chosen:
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
        self.t += dt
        mx, my = self.app.mouse
        tx, ty = -(mx / W - 0.5) * 20, -(my / H - 0.5) * 20  # +-10 px, against the cursor like a deeper layer
        k = min(1.0, dt * 3)
        self.par[0] += (tx - self.par[0]) * k
        self.par[1] += (ty - self.par[1]) * k
        self.set_bg()
        self.w.update(dt, dt)
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
        return self.w.fx_params()

    def draw_title(self, screen, ui):
        """The title is art on the wall (its glint lives in the glow layer); the subtitle is UI."""
        f = self.app.art.fonts
        r = self.title_rect
        u = (self.t - self.SWEEP_AT) / self.SWEEP
        if u <= 0:
            return
        e = 1 - (1 - min(u, 1.0)) ** 2  # the cut decelerates slightly as it leaves the last letter
        sx = r.left - 40 + (r.width + 80) * e  # streak position; letters to its left are revealed
        w = int(min(r.width, max(0, sx - r.left))) if u < 1 else r.width
        if w > 0:
            self.title_sh.set_alpha(230)
            screen.blit(self.title_sh, (r.left - 6, r.top - 3), (0, 0, w + 6, self.title_sh.get_height()))
            self.title.set_alpha(255)
            screen.blit(self.title, r, (0, 0, w, r.height))
        glow = max(0.0, 1 - max(0.0, u - 1) / 0.25)  # the light lingers a moment after the cut, then is gone
        if glow > 0:
            st = self.streak
            if glow < 1:
                st = st.copy()
                st.fill(shade((255, 255, 255), glow), special_flags=pygame.BLEND_RGB_MULT)
            emit(self.app, screen, st, st.get_rect(center=(sx, r.centery)).topleft)
            bw = self.band.get_width()
            x0 = int(sx - r.left - bw / 2)
            clip = pygame.Rect(x0, 0, bw, r.height).clip(self.title_glint.get_rect())
            if clip.w > 0:
                g = self.title_glint.subsurface(clip).copy()
                band = pygame.transform.scale(self.band, (bw, r.height))
                g.blit(band, (0, 0), (clip.x - x0, 0, clip.w, r.height), special_flags=pygame.BLEND_RGB_MULT)
                if glow < 1:
                    g.fill(shade((255, 255, 255), glow), special_flags=pygame.BLEND_RGB_MULT)
                emit(self.app, screen, g, (r.left + clip.x, r.top))
        # subtitle settles in once the title is cut
        a = int(255 * max(0.0, min(1.0, (u - 0.9) / 0.5)))
        if a:
            sub = label(ui, f, f.mono15, "NIGHT DOJO", GOLD, (W / 2, r.bottom + 14), tracking=7, alpha=a)
            line = pygame.Surface((44, 1), pygame.SRCALPHA)  # per-pixel alpha: a faded opaque surface blits opaque
            line.fill((*GOLD, a // 2))
            ui.blit(line, (sub.left - 62, sub.centery))
            ui.blit(line, (sub.right + 18, sub.centery))

    def draw(self, screen):
        f = self.app.art.fonts
        ui = self.app.ui
        self.w.draw(screen)
        self.draw_title(screen, ui)
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
        label(ui, f, f.mono13, "1 2 3 quick start  ·  ← → blade  ·  M mute  ·  F11 fullscreen  ·  Esc quit",
              MUTED, (W - 48, y + 28), "midright")
        self.w.draw_overlay(screen)


# ---------------- play ----------------

class Play(Scene):
    def __init__(self, app, mode):
        self.app, self.mode = app, mode
        self.w = World(app)
        self.score = 0
        self.best_prev = app.save["best"][mode]
        self.strikes = 0
        self.strike_pop = [0.0, 0.0, 0.0]
        self.misses = []  # red X where a fruit dropped
        self.time = {"classic": None, "arcade": 60.0, "zen": 90.0}[mode]
        self.elapsed = 0.0
        self.spawn_t = 1.3
        self.queue = []
        self.combo, self.combo_t, self.combo_pos = 0, 0.0, (0, 0)
        self.freeze = self.frenzy = self.double = 0.0
        self.frenzy_spawn = 0.0
        self.special_cd = 7.0
        self.next_life = 100
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
        r = 38 if kind == "bomb" else FRUITS[kind].r
        x0 = x if x is not None else random.uniform(W * 0.12, W * 0.88)
        y0 = H + r + 10
        apex = random.uniform(H * 0.07, H * 0.42)
        vy = -math.sqrt(2 * GRAVITY * (y0 - apex))
        t = -vy / GRAVITY
        xa = min(max(x0 + random.uniform(-W * 0.25, W * 0.25), W * 0.18), W * 0.82)
        self.w.throw(kind, x0, y0, (xa - x0) / t, vy)
        self.app.audio.play("throw", 0.5)

    def wave(self):
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
        e = self.elapsed
        return {"classic": max(0.85, 2.2 - e * 0.016), "arcade": max(0.6, 1.4 - e * 0.012), "zen": max(0.9, 1.7 - e * 0.008)}[self.mode]

    # --- scoring ---
    def add_score(self, n):
        self.score += n
        if self.mode == "classic":
            while self.score >= self.next_life:
                self.next_life += 100
                if self.strikes > 0:
                    self.strikes -= 1
                    self.w.popups.add("+1 life", W - 120, 112, GOLD, True)
                    self.app.audio.play("life")

    def hit(self, b, seg):
        w = self.w
        if b.bomb:
            w.explode(b)
            self.stats["bombs"] += 1
            if self.mode == "classic":
                self.state, self.state_t = "dying", 0.0
                self.app.audio.fuse(False)
            else:
                self.score = max(0, self.score - 10)
                w.popups.add("-10", b.x, b.y - 40, HANKO, True)
            return
        w.cut(b, *seg)
        mult = 2 if self.double > 0 else 1
        pts = b.ft.points * mult
        if self.mode == "arcade" and not b.special and random.random() < 0.06:
            pts += 10
            w.popups.add("Critical +10", b.x, b.y - 50, GOLD, True)
            w.particles.sparks(b.x, b.y, GOLD, 30, 600)
            w.hitstop = max(w.hitstop, 0.06)
        else:
            w.popups.add(f"+{pts}", b.x, b.y - 30, GOLD if mult > 1 else WASHI)
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
        for seg in self.app.segments:
            for b in self.w.bodies:
                if b.alive and seg_hits_circle(*seg, b.x, b.y, b.r * 1.05):
                    self.hit(b, seg)
                    if self.state != "play":
                        return

    def finish_combo(self):
        if self.combo >= 3:
            bonus = self.combo * (2 if self.double > 0 else 1)
            self.add_score(bonus)
            self.w.stamp("連", f"{self.combo} fruit combo", *self.combo_pos, 100 + min(60, self.combo * 6), bonus=f"+{bonus}")
            self.w.hitstop = max(self.w.hitstop, 0.05)
            self.app.audio.play("combo")
        self.stats["best_combo"] = max(self.stats["best_combo"], self.combo)
        self.combo = 0

    def strike(self, b):
        self.stats["missed"] += 1
        if self.mode != "classic" or self.state != "play":
            return
        self.strike_pop[self.strikes] = 0.35
        self.strikes += 1
        self.misses.append([min(max(b.x, 40), W - 40), 0.0])
        self.w.shake.kick(0.3)
        self.app.audio.play("miss")
        if self.strikes >= 3:
            self.state, self.state_t = "dying", 0.0

    # --- loop ---
    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_p):
                self.paused = not self.paused
            elif self.paused and e.key == pygame.K_q:
                self.app.audio.fuse(False)
                self.app.go(lambda: Menu(self.app))
        elif e.type == pygame.MOUSEBUTTONDOWN and self.paused and e.button == 1:
            self.paused = False

    def focus_lost(self):
        if self.state == "play":
            self.paused = True

    def fx_params(self):
        if self.paused:
            return {}
        p = self.w.fx_params()
        if self.freeze > 0:  # the cold grade also drains a little colour on the GPU
            p["saturation"] *= 1 - 0.2 * min(1.0, self.freeze / 0.6)
        return p

    def update(self, dt):
        if self.paused:
            self.app.audio.fuse(False)
            return
        self.pause_bg = None
        w = self.w
        # game clock: only freeze slows the timer, spawning and difficulty ramp; slow-mo only slows the world
        wdt = dt * (0.4 if self.freeze > 0 else 1.0)
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
            self.freeze, self.frenzy, self.double = (max(0.0, v - dt) for v in (self.freeze, self.frenzy, self.double))
            self.special_cd -= dt
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
            if self.spawn_t <= 0 and not self.queue:
                self.wave()
                self.spawn_t = self.interval()
            if self.frenzy > 0:
                self.frenzy_spawn -= dt
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
        for b in w.bodies:
            if b.alive and b.gone():
                b.alive = False
                if not b.bomb and not b.special and b.entered:
                    self.strike(b)
        w.bodies = [b for b in w.bodies if b.alive]
        # bomb fuses fizz
        bombs = [b for b in w.bodies if b.bomb]
        for b in bombs:
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
        self.state = "over"
        if self.combo:
            self.finish_combo()
        save = self.app.save
        save["best"][self.mode] = max(save["best"][self.mode], self.score)
        save["total_sliced"] += self.stats["sliced"]
        write_save(save)
        self.app.audio.fuse(False)
        snap = self.app.snapshot()
        self.app.go(lambda: GameOver(self.app, self, snap))

    def draw_world_extra(self, L, add):
        for x, age in self.misses:  # a red brush mark where the fruit fell
            k = min(1.0, age / 0.12)
            a = int(255 * min(1.0, (1.2 - age) / 0.4))
            img = brush_x(44, HANKO)
            if k < 1:
                img = pygame.transform.smoothscale_by(img, 1.5 - 0.5 * k)
            img.set_alpha(a)
            L.blit(img, img.get_rect(center=(x, H - 46)))

    def draw_hud(self, screen):
        """`screen` is the UI layer: above the post-processing, so the camera never moves, fringes or dims it."""
        f = self.app.art.fonts
        # score: left, gold, the number rolls toward the real value
        label(screen, f, f.mono12, "SCORE", MUTED, (42, 34), "midleft", tracking=4)
        sr = label(screen, f, f.score, str(round(self.shown)), GOLD, (38, 44), "topleft")
        best = max(self.best_prev, self.score)
        label(screen, f, f.mono13, f"Best {best}", MUTED, (42, sr.bottom + 6), "midleft")
        if self.mode == "classic":  # strikes: three brush marks, empty until missed
            for i in range(3):
                cx = W - 66 - (2 - i) * 52
                if i < self.strikes:
                    img = brush_x(40, HANKO)
                    p = self.strike_pop[i]
                    if p > 0:  # lands big and settles, like the brush hitting paper
                        img = pygame.transform.smoothscale_by(img, 1 + p * 1.6)
                    img.set_alpha(255)
                else:
                    img = brush_x(40, WASHI, outline=True)
                    img.set_alpha(64)  # 25 %
                screen.blit(img, img.get_rect(center=(cx, 62)))
            y = 112
        else:
            label(screen, f, f.mono12, "TIME", MUTED, (W - 42, 34), "midright", tracking=4)
            t = max(0.0, self.time)
            col = HANKO if t <= 5 else GOLD if t <= 10 else WASHI
            s = f"{int(t) // 60}:{int(t) % 60:02d}" if t > 0 or self.state != "play" else "0:00"
            img = f.text(f.timer, s, col)
            sh = f.shadow(f.timer, s)
            r = img.get_rect(topright=(W - 38, 44))
            if t <= 5 and self.state == "play":  # each second lands with a pulse
                p = (math.ceil(t) - t) ** 3 if t > 0 else 0
                k = 1 + 0.14 * p
                img = pygame.transform.smoothscale_by(img, k)
                sh = pygame.transform.smoothscale_by(sh, k)
                r = img.get_rect(midright=r.midright)
            sh.set_alpha(230)
            screen.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
            img.set_alpha(255)
            screen.blit(img, r)
            y = r.bottom + 18
        # power-up chips: what's active and how long it has left
        for val, total, name, col in ((self.freeze, 6.0, "FREEZE", FRUITS["freeze"].juice),
                                      (self.frenzy, 4.5, "FRENZY", FRUITS["frenzy"].juice),
                                      (self.double, 8.0, "DOUBLE ×2", FRUITS["double"].juice)):
            if val > 0:
                label(screen, f, f.mono12, name, col, (W - 42, y), "midright", tracking=3)
                track = pygame.Surface((140, 2), pygame.SRCALPHA)
                track.fill((*WASHI, 40))
                screen.blit(track, (W - 42 - 140, y + 14))
                fill = int(140 * val / total)
                if fill > 0:
                    screen.fill(col, (W - 42 - fill, y + 14, fill, 2))
                y += 38

    def draw_pause(self, screen):
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
        w = self.w
        if self.paused and self.pause_bg is not None:
            self.draw_pause(screen)
            return
        w.draw(screen, self.draw_world_extra)
        # power-up grades go under the HUD, never over its text
        if self.freeze > 0:  # a cold grade that fades in and out with the effect
            k = min(1.0, self.freeze / 0.6)
            screen.fill(lerp_rgb((255, 255, 255), (190, 214, 240), k), special_flags=pygame.BLEND_RGB_MULT)
            self.app.art.frost.set_alpha(int(255 * k))
            screen.blit(self.app.art.frost, (0, 0))
        if self.frenzy > 0:  # embers at the edges, breathing slowly
            k = min(1.0, self.frenzy / 0.5)
            ember = self.app.art.ember
            gain = 1.0 if self.app.gpu is None else 0.4  # bloom and additive composite amplify it on the GPU
            ember.set_alpha(int(255 * gain * k * (0.75 + 0.25 * math.sin(w.t * 5))))
            # it is light, not paint: on the GPU it goes to the glow layer so the bloom carries it
            (screen if self.app.gpu is None else self.app.add).blit(ember, (0, 0))
        self.draw_hud(self.app.ui)
        w.draw_overlay(screen)
        if self.paused:
            self.draw_pause(screen)


# ---------------- game over ----------------

class GameOver(Scene):
    COUNT_AT, COUNT = 0.45, 1.3  # the score counts up once the 終 seal has landed

    def __init__(self, app, play, snap):
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
        if e.type == pygame.KEYDOWN and not self.choice:
            if e.key in (pygame.K_RETURN, pygame.K_r, pygame.K_SPACE):
                self.retry.cut()  # the same answer a swipe gets: the fruit splits and its seal lands
                self.choose("retry")
            elif e.key == pygame.K_ESCAPE:
                self.menu.cut()
                self.choose("menu")

    def choose(self, c):
        self.choice, self.choice_t = c, 0.0

    def update(self, dt):
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
        return self.w.fx_params()

    def draw(self, screen):
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
    DUR = 0.5

    def __init__(self, snap):
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
        self.t += dt
        return self.t < self.DUR

    def draw(self, screen, add=None, cpu=True, ui=None):
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
    def __init__(self):
        pygame.init()
        self.fullscreen = False
        self.open_window()
        pygame.display.set_caption("Fruit Ninja · Night Dojo")
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
        snap = self.snapshot()
        self.scene = make_scene()
        self.wipe = Wipe(snap)
        self.audio.play("swoosh", 0.9)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 1 / 20)
            self.step(dt, pygame.event.get())
            self.present(self.scene.fx_params())
        pygame.quit()

    def step(self, dt, events):
        self.now += dt
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
                    pygame.display.toggle_fullscreen()
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
        colors = BLADES[self.save["blade"]][:3]
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
