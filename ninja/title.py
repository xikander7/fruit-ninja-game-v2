"""The menu's title intro: a watermelon is tossed up, cut at its apex, and "Hanifa" is signed in its juice.

Plays once per Menu entry (~1.6 s), skippable; afterwards the name holds with a slow light sweep now and then.
The name is art on the wall (drawn into the world layer, so the juice droplets fly over it and the post-fx grade
it); the subtitle and the seal are UI."""
import math

import pygame

from .art import FRUITS, Fonts, _font
from .fx import shade, stamp_scale
from .hud import label
from .settings import W, H, WASHI, GOLD, HANKO, BLADES, TITLE, SUBTITLE

TOSS = 0.42  # s: the melon rises from below the screen to its apex, where the blade meets it
SLASH = 0.32  # s the blade streak takes to draw across and burn out
REVEAL_AT, REVEAL = 0.5, 0.5  # the name is signed left to right
SWASH_AT, SWASH = 0.86, 0.26  # the brush underline
SUB_AT, SUB = 0.98, 0.38  # "THE FRUIT NINJA" slides in
SEAL_AT = 1.22  # the hanko lands
DONE = 1.6  # settled
SETTLE = 0.9  # s for the wet juice under the name to dry back
SWEEP_FIRST, SWEEP_EVERY, SWEEP = 2.0, 6.0, 0.9  # idle light sweep
CY = 118  # the name's centre line
APEX = 124
SLANT = 0.17  # signature lean (horizontal px per px of height)
EDGE = 36  # px of feathered edge on the brush's leading front


def slanted(img, k=SLANT):
    """Shear a surface to the right (pygame has no shear: one row at a time, once)."""
    w, h = img.get_size()
    out = pygame.Surface((w + int(h * k) + 1, h), pygame.SRCALPHA if img.get_flags() & pygame.SRCALPHA else 0)
    for y in range(h):
        out.blit(img, (int((h - y) * k), y), (0, y, w, 1))
    return out


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


def make_band(w):
    """Horizontal falloff multiplied into the name's glint, so only the letters right at the streak catch light."""
    s = pygame.Surface((w, 1))
    for x in range(w):
        s.set_at((x, 0), shade((255, 255, 255), math.exp(-((x - w / 2) / (w / 6)) ** 2)))
    return s


def make_swash(w, color):
    """A tapered brush underline with a gentle sag, drawn at 2x and smoothed for clean edges."""
    S = 2
    h = 26
    s = pygame.Surface((w * S, h * S), pygame.SRCALPHA)
    n = w // 2
    for i in range(n + 1):
        u = i / n
        r = (1.0 + 5.2 * math.sin(math.pi * u ** 0.8) ** 0.7) * S  # thick early, a long thin tail like a lifted brush
        x = (6 + u * (w - 12)) * S
        y = (h / 2 + 5 * math.sin(math.pi * u) - 4 * u) * S
        pygame.draw.circle(s, color, (x, y), r)
    return pygame.transform.smoothscale(s, (w, h))


def feather(w, h):
    """White with alpha falling 255 -> 0 left to right: RGBA-multiplied onto the brush front to soften it."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in range(w):
        s.fill((255, 255, 255, int(255 * (1 - x / (w - 1)) ** 1.4)), (x, 0, 1, h))
    return s


def ease_out(u, p=3):
    u = min(1.0, max(0.0, u))
    return 1 - (1 - u) ** p


class TitleIntro:
    def __init__(self, app, world):
        self.app, self.w = app, world
        self.t = 0.0
        self.cut = False
        self.sealed = False
        f = app.art.fonts
        font = _font(Fonts.DISPLAY[0], 150, Fonts.DISPLAY[1], Fonts.DISPLAY[2])
        self.juice = FRUITS["watermelon"].juice
        self.ink = slanted(font.render(TITLE, True, WASHI).convert_alpha())
        red = slanted(font.render(TITLE, True, self.juice).convert_alpha())
        wet = pygame.Surface((red.get_width() + 12, red.get_height() + 12), pygame.SRCALPHA)
        for dx, dy in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (-2, 2), (2, -2), (-2, -2)):
            wet.blit(red, (6 + dx, 6 + dy))
        self.wet = pygame.transform.gaussian_blur(wet, 2)
        sh = pygame.Surface(wet.get_size(), pygame.SRCALPHA)
        sh.blit(slanted(font.render(TITLE, True, (0, 0, 0)).convert_alpha()), (6, 6))
        self.shadow = pygame.transform.gaussian_blur(sh, 5)
        self.glint = pygame.Surface(self.ink.get_size())
        self.glint.blit(slanted(font.render(TITLE, True, (255, 240, 214)).convert_alpha()), (0, 0))
        self.rect = self.ink.get_rect(center=(W / 2, CY))
        self.swash = make_swash(int(self.rect.width * 0.86), shade(HANKO, 1.05))
        self.feather = feather(EDGE, self.wet.get_height())
        self.streak = make_streak(self.rect.height + 70)
        self.band = make_band(120)
        self.sub_font = _font(Fonts.MONO[0], 17, Fonts.MONO[1], Fonts.MONO[2])
        self.seal = app.art.seal("忍", 44)
        self.blade = BLADES[app.save["blade"]][:3]
        app.audio.play("throw", 0.8)
        self.melon = world.throw("watermelon", W / 2, 0, 0, 0)
        self.melon.flight = 2 * TOSS  # swells toward the camera at the apex; the halves carry the arc on
        self.melon.spin = 260
        self.place_melon()

    @property
    def done(self):
        return self.t >= DONE

    def skip(self):
        if self.done:
            return
        self.t = DONE
        if self.melon.alive:  # skipped before the cut: the melon just isn't there any more
            self.melon.alive = False
            if self.melon in self.w.bodies:
                self.w.bodies.remove(self.melon)
        self.sealed = True

    def place_melon(self):
        """The toss is scripted, not simulated: an eased rise lands it exactly on the apex at the cut."""
        b = self.melon
        u = min(1.0, self.t / TOSS)
        y0 = H + 90
        b.x, b.y = W / 2, y0 + (APEX - y0) * ease_out(u, 2)
        b.vx, b.vy = 0.0, -2 * (y0 - APEX) / TOSS * (1 - u)  # d/dt of the curve: drives the motion blur

    def update(self, dt):
        self.t += dt
        w = self.w
        if not self.cut and self.melon.alive:
            if self.t < TOSS:
                self.place_melon()
            else:
                self.cut = True
                self.place_melon()
                ax, ay, bx, by = self.slash_line()
                n = len(w.halves)
                w.cut(self.melon, ax, ay, bx, by)
                for h in w.halves[n:]:  # a hero cut: the halves part harder than a menu fruit's
                    h.vx *= 2.4
                    h.vy -= 260
                if self.melon in w.bodies:
                    w.bodies.remove(self.melon)
                w.particles.sparks(W / 2, APEX, self.blade[1], 26, 650, 0.45)
                w.zoom_punch(1.035)
                w.shake.kick(0.35)
                w.flash = max(w.flash, 0.22)
                self.app.audio.play("swoosh", 1.0)
        if not self.sealed and self.t >= SEAL_AT:
            self.sealed = True
            x, y = self.seal_pos()
            w.particles.ink(x, y, HANKO, 14)
            self.app.audio.play("stamp", 0.6)

    @staticmethod
    def slash_line():
        return W / 2 - 300, APEX + 120, W / 2 + 300, APEX - 120

    def seal_pos(self):
        return self.rect.right + 4, self.rect.bottom - 30

    # ---------------- drawing ----------------

    def draw_world(self, L, add):
        """World-layer part (passed to World.draw as `extra`): the blade streak and the signed name."""
        t = self.t
        if self.cut and t < TOSS + SLASH:
            self.draw_slash(add, (t - TOSS) / SLASH)
        u = (t - REVEAL_AT) / REVEAL
        if u <= 0:
            return
        r = self.rect
        front = (r.width + EDGE * 2) * ease_out(u, 2) - EDGE  # px of the name signed so far
        settle = ease_out((t - REVEAL_AT - REVEAL * 0.6) / SETTLE, 2)
        # wet juice underneath, leading the brush a little, then drying back to a thin red edge
        off = (6 - 4 * settle, 8 - 5 * settle)
        self.blit_front(L, self.shadow, (r.left - 6 + 3, r.top - 6 + 6), front + 10, 200)
        self.blit_front(L, self.wet, (r.left - 6 + off[0], r.top - 6 + off[1]), front + 22, int(255 - 120 * settle))
        self.blit_front(L, self.ink, r.topleft, front, 255)
        if u < 1.15:  # the brush tip glows as it travels
            k = max(0.0, 1 - max(0.0, u - 1) / 0.15)
            st = self.streak
            if k < 1:
                st = st.copy()
                st.fill(shade((255, 255, 255), k), special_flags=pygame.BLEND_RGB_MULT)
            add.blit(st, st.get_rect(center=(r.left + front, r.centery)), special_flags=pygame.BLEND_RGB_ADD)
        s = (t - SWASH_AT) / SWASH
        if s > 0:
            sw = self.swash
            ww = int(sw.get_width() * ease_out(s, 2))
            if ww > 0:
                L.blit(sw, (r.left + r.width * 0.06, r.bottom - 34), (0, 0, ww, sw.get_height()))
        if self.done:
            self.draw_sweep(add)

    def blit_front(self, L, img, pos, front, alpha):
        """Blit the part of `img` left of the brush front, its last EDGE px feathered."""
        wdt = int(min(img.get_width(), front))
        if wdt <= 0:
            return
        piece = img.subsurface((0, 0, wdt, img.get_height())).copy()
        if wdt < img.get_width():
            piece.blit(self.feather, (wdt - EDGE, 0), (0, 0, EDGE, img.get_height()), special_flags=pygame.BLEND_RGBA_MULT)
        if alpha < 255:
            piece.set_alpha(alpha)
        L.blit(piece, pos)

    def draw_slash(self, add, u):
        """The blade's streak: a lens of light drawn across in the first third, then burning out."""
        ax, ay, bx, by = self.slash_line()
        grow = ease_out(u / 0.3, 2)
        fade = 1.0 if u < 0.3 else (1 - (u - 0.3) / 0.7) ** 1.5
        ex, ey = ax + (bx - ax) * grow, ay + (by - ay) * grow
        dx, dy = ex - ax, ey - ay
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        mx, my = (ax + ex) / 2, (ay + ey) / 2
        for col, wdt in zip(self.blade, (16, 7, 2.5)):
            c = shade(col, fade)
            pygame.draw.polygon(add, c, [(ax, ay), (mx + nx * wdt, my + ny * wdt), (ex, ey), (mx - nx * wdt, my - ny * wdt)])

    def draw_sweep(self, add):
        """Idle: a slow katana light crosses the name every SWEEP_EVERY s."""
        p = self.t - DONE - SWEEP_FIRST
        if p < 0:
            return
        u = (p % SWEEP_EVERY) / SWEEP
        if u > 1:
            return
        r = self.rect
        k = math.sin(math.pi * u)  # fades in and out at the ends
        sx = r.left - 40 + (r.width + 80) * u
        st = self.streak.copy()
        st.fill(shade((255, 255, 255), 0.55 * k), special_flags=pygame.BLEND_RGB_MULT)
        add.blit(st, st.get_rect(center=(sx, r.centery)), special_flags=pygame.BLEND_RGB_ADD)
        bw = self.band.get_width()
        x0 = int(sx - r.left - bw / 2)
        clip = pygame.Rect(x0, 0, bw, r.height).clip(self.glint.get_rect())
        if clip.w > 0:
            g = self.glint.subsurface(clip).copy()
            band = pygame.transform.scale(self.band, (bw, r.height))
            g.blit(band, (0, 0), (clip.x - x0, 0, clip.w, r.height), special_flags=pygame.BLEND_RGB_MULT)
            g.fill(shade((255, 255, 255), 0.7 * k), special_flags=pygame.BLEND_RGB_MULT)
            add.blit(g, (r.left + clip.x, r.top), special_flags=pygame.BLEND_RGB_ADD)

    def draw_ui(self, ui):
        """UI part: the subtitle slides in under the name, then the seal is pressed."""
        f = self.app.art.fonts
        u = (self.t - SUB_AT) / SUB
        if u > 0:
            e = ease_out(u)
            a = int(255 * min(1.0, u * 1.6))
            sub = label(ui, f, self.sub_font, SUBTITLE, GOLD, (W / 2 + 46 * (1 - e), self.rect.bottom + 6), tracking=8, alpha=a)
            line = pygame.Surface((int(54 * e) or 1, 1), pygame.SRCALPHA)  # per-pixel alpha: a faded opaque surface blits opaque
            line.fill((*GOLD, a // 2))
            ui.blit(line, (sub.left - 18 - line.get_width(), sub.centery))
            ui.blit(line, (sub.right + 18, sub.centery))
        if self.t >= SEAL_AT:
            age = self.t - SEAL_AT
            img = pygame.transform.rotozoom(self.seal, -8, stamp_scale(age))
            ui.blit(img, img.get_rect(center=self.seal_pos()))
