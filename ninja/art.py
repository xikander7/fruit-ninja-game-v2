"""Art: photoreal sprites from assets/sprites when present, else procedural drawing painted at startup."""
import math
import os
import random
from dataclasses import dataclass

import pygame

from .settings import W, H, WASHI, HANKO, LACQUER, CEDAR

SPRITE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sprites")
SS = 2  # supersample factor, smoothscaled down for anti-aliasing


@dataclass
class FruitType:
    name: str
    r: int
    skin: tuple
    skin2: tuple
    rim: tuple
    flesh: tuple
    juice: tuple
    points: int = 1
    shape: str = "round"
    special: str = ""  # "", "freeze", "frenzy", "double"


FRUITS = {
    "watermelon": FruitType("watermelon", 56, (38, 110, 44), (110, 175, 70), (225, 240, 200), (232, 48, 62), (225, 35, 55)),
    "coconut": FruitType("coconut", 44, (100, 64, 38), (70, 44, 26), (245, 245, 238), (250, 250, 246), (240, 240, 235)),
    "orange": FruitType("orange", 40, (255, 135, 20), (230, 105, 10), (255, 236, 190), (255, 165, 45), (255, 150, 30)),
    "peach": FruitType("peach", 38, (255, 170, 95), (220, 60, 60), (255, 220, 160), (255, 190, 80), (255, 170, 60)),
    "apple": FruitType("apple", 38, (205, 28, 38), (255, 200, 90), (255, 248, 222), (250, 238, 196), (255, 240, 200)),
    "dragonfruit": FruitType("dragonfruit", 40, (225, 30, 120), (120, 190, 60), (255, 120, 190), (252, 250, 248), (250, 120, 190), 3, "dragon"),
    "lemon": FruitType("lemon", 34, (255, 222, 40), (230, 190, 20), (255, 250, 210), (250, 238, 120), (250, 235, 90), 1, "lemon"),
    "kiwi": FruitType("kiwi", 34, (125, 88, 48), (95, 64, 34), (150, 205, 70), (120, 190, 40), (140, 210, 60), 1, "oval"),
    "plum": FruitType("plum", 31, (110, 32, 92), (70, 20, 60), (255, 215, 100), (240, 200, 60), (170, 50, 120), 1, "oval"),
    "strawberry": FruitType("strawberry", 30, (230, 30, 45), (60, 150, 50), (255, 160, 170), (255, 110, 125), (240, 40, 60), 1, "berry"),
    "banana": FruitType("banana", 44, (255, 220, 60), (120, 80, 30), (255, 245, 200), (255, 245, 205), (255, 240, 180), 1, "banana"),
    "freeze": FruitType("freeze", 44, (150, 215, 255), (40, 80, 140), (230, 245, 255), (220, 240, 255), (160, 220, 255), 1, "banana", "freeze"),
    "frenzy": FruitType("frenzy", 44, (255, 110, 50), (140, 30, 10), (255, 220, 180), (255, 200, 150), (255, 120, 50), 1, "banana", "frenzy"),
    "double": FruitType("double", 44, (255, 205, 50), (150, 100, 0), (255, 245, 200), (255, 238, 170), (255, 210, 60), 1, "banana", "double"),
}
REGULAR = ["watermelon", "coconut", "orange", "peach", "apple", "lemon", "kiwi", "plum", "strawberry", "banana", "dragonfruit"]
WEIGHTS = [10, 6, 12, 9, 12, 9, 9, 8, 9, 6, 3]
SPECIALS = ["freeze", "frenzy", "double"]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade_of(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _font(names, size, bold=False):
    return pygame.font.SysFont(names, size, bold=bold)


class Fonts:
    def __init__(self):
        disp = "bahnschrift,segoeuiblack,arialblack,dejavusans"
        self.huge = _font(disp, 112, True)
        self.big = _font(disp, 64, True)
        self.mid = _font(disp, 36, True)
        self.small = _font(disp, 22, True)
        self.util = _font("consolas,dejavusansmono,couriernew", 18)
        self.kanji = "yugothic,msgothic,notosanscjkjp,notosanscjk,malgungothic"


# ---------- shape masks (white = inside) ----------

def _shape_mask(ft, size):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    r = ft.r * SS
    white = (255, 255, 255, 255)
    if ft.shape == "round":
        pygame.draw.circle(s, white, (c, c), r)
        if ft.name == "apple":  # dimple at the stem
            pygame.draw.circle(s, (0, 0, 0, 0), (c, c - r * 1.02), r * 0.2)
    elif ft.shape == "oval":
        pygame.draw.ellipse(s, white, pygame.Rect(0, 0, r * 2.2, r * 1.9).move(c - r * 1.1, c - r * 0.95))
    elif ft.shape == "lemon":
        pygame.draw.ellipse(s, white, pygame.Rect(0, 0, r * 2.3, r * 1.85).move(c - r * 1.15, c - r * 0.925))
        pygame.draw.circle(s, white, (c - r * 1.15, c), r * 0.22)
        pygame.draw.circle(s, white, (c + r * 1.15, c), r * 0.22)
    elif ft.shape == "dragon":
        pygame.draw.ellipse(s, white, pygame.Rect(0, 0, r * 1.9, r * 2.25).move(c - r * 0.95, c - r * 1.125))
    elif ft.shape == "berry":
        pygame.draw.circle(s, white, (c, c - r * 0.25), r * 0.95)
        pygame.draw.polygon(s, white, [(c - r * 0.93, c - r * 0.1), (c + r * 0.93, c - r * 0.1), (c, c + r * 1.15)])
        pygame.draw.circle(s, white, (c, c + r * 0.55), r * 0.55)
    elif ft.shape == "banana":
        for (x, y, rad, col) in _banana_circles(c, r):
            pygame.draw.circle(s, col, (x, y), rad)
    return s


def _banana_circles(c, r):
    # crescent = big circle minus offset circle
    return [(c, c - r * 0.35, r * 1.05, (255, 255, 255, 255)), (c, c - r * 1.0, r * 1.15, (0, 0, 0, 0))]


def _banana_tips(c, r):
    # intersection of the two crescent circles, in circle-1-local coords (circle 2 sits d above)
    r1, r2, d = r * 1.05, r * 1.15, r * 0.65
    y = (r2 * r2 - r1 * r1 - d * d) / (2 * d)
    x = math.sqrt(max(0.0, r1 * r1 - y * y))
    cy = c - r * 0.35 + y
    return (c - x, cy), (c + x, cy)


def _sphere_shade(size, strength=1.0):
    s = pygame.Surface((size, size))
    s.fill((255, 255, 255))
    c = size / 2
    n = 36
    for i in range(n):
        t = i / (n - 1)
        rad = c * (1.0 - 0.92 * t)
        off = -0.32 * c * t
        v = int(255 - (140 * (1 - t) ** 1.7) * strength)
        pygame.draw.circle(s, (v, v, v), (c + off, c + off), rad)
    return s


def _highlight(size, cx, cy, rad, peak=120):
    s = pygame.Surface((size, size))
    n = 20
    for i in range(n):
        t = i / (n - 1)
        v = int(peak * t * t)
        pygame.draw.circle(s, (v, v, v), (cx, cy), max(1, rad * (1 - t * 0.9)))
    return s


# ---------- skin details ----------

def _details(ft, s, c, r, rng):
    if ft.name == "watermelon":
        for k in range(-5, 6):
            pts = []
            for j in range(26):
                y = c - r * 1.1 + j * r * 2.2 / 25
                yy = (y - c) / r
                bend = math.sqrt(max(0, 1 - yy * yy))
                x = c + k * r * 0.22 * (0.4 + bend * 0.75) + math.sin(j * 1.3 + k) * r * 0.04
                pts.append((x, y))
            pygame.draw.lines(s, ft.skin2, False, pts, int(r * 0.11))
    elif ft.name in ("orange", "lemon"):
        for _ in range(int(r * 6)):
            a, d = rng.uniform(0, math.tau), r * math.sqrt(rng.random()) * 1.2
            pygame.draw.circle(s, ft.skin2, (c + math.cos(a) * d, c + math.sin(a) * d), rng.uniform(1, 2.2) * SS / 2)
    elif ft.name == "coconut":
        for _ in range(int(r * 3)):
            a, d = rng.uniform(0, math.tau), r * math.sqrt(rng.random())
            x, y = c + math.cos(a) * d, c + math.sin(a) * d
            ang = rng.uniform(0, math.tau)
            L = rng.uniform(4, 12) * SS
            pygame.draw.line(s, shade_of(ft.skin, rng.uniform(0.55, 1.3)), (x, y), (x + math.cos(ang) * L, y + math.sin(ang) * L), SS)
        for k in range(3):
            a = -math.pi / 2 + (k - 1) * 0.5
            pygame.draw.circle(s, (45, 28, 16), (c + math.cos(a) * r * 0.32, c - r * 0.4 + math.sin(a) * r * 0.05), r * 0.09)
    elif ft.name == "kiwi":
        for _ in range(int(r * 10)):
            a, d = rng.uniform(0, math.tau), r * 1.1 * math.sqrt(rng.random())
            pygame.draw.circle(s, shade_of(ft.skin, rng.uniform(0.7, 1.25)), (c + math.cos(a) * d, c + math.sin(a) * d), SS)
    elif ft.name == "peach":
        blush = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        for i in range(14):
            pygame.draw.circle(blush, (*ft.skin2, 22), (c + r * 0.35, c + r * 0.15), r * (1.1 - i * 0.06))
        s.blit(blush, (0, 0))
    elif ft.name == "apple":
        for _ in range(26):
            x = c + rng.uniform(-0.8, 0.8) * r
            pygame.draw.line(s, lerp(ft.skin, ft.skin2, rng.uniform(0.2, 0.45)), (x, c - r * 0.3), (x + rng.uniform(-6, 6), c + r * 0.8), SS)
    elif ft.name == "plum":
        pass
    elif ft.name == "strawberry":
        for row in range(7):
            for col in range(7):
                x = c + (col - 3 + (row % 2) * 0.5) * r * 0.3
                y = c - r * 0.7 + row * r * 0.27
                pygame.draw.ellipse(s, (255, 225, 120), pygame.Rect(x - SS * 1.5, y - SS * 2.5, SS * 3, SS * 5))
    elif ft.shape == "dragon":
        for _ in range(10):
            a = rng.uniform(0, math.tau)
            x, y = c + math.cos(a) * r * 0.55, c + math.sin(a) * r * 0.7
            pygame.draw.ellipse(s, shade_of(ft.skin, 1.15), pygame.Rect(x - r * 0.2, y - r * 0.12, r * 0.4, r * 0.24))
    elif ft.shape == "banana" and not ft.special:
        pts = [(c - r * 0.8, c + r * 0.25), (c, c + r * 0.62), (c + r * 0.8, c + r * 0.25)]
        pygame.draw.lines(s, shade_of(ft.skin, 0.85), False, pts, SS * 2)


def _after_mask(ft, s, c, r, rng):
    """Bits that stick out past the shape: stems, leaves, scales."""
    if ft.name == "apple":
        pygame.draw.line(s, (90, 55, 25), (c, c - r * 0.85), (c + r * 0.12, c - r * 1.25), int(SS * 3.5))
        leaf = pygame.Rect(0, 0, r * 0.55, r * 0.26)
        leaf.center = (c + r * 0.38, c - r * 1.12)
        pygame.draw.ellipse(s, (70, 160, 50), leaf)
    elif ft.name == "orange":
        pygame.draw.circle(s, (80, 120, 30), (c + r * 0.05, c - r * 0.88), r * 0.1)
    elif ft.name == "strawberry":
        for k in range(6):
            a = -math.pi / 2 + (k - 2.5) * 0.45
            tip = (c + math.cos(a) * r * 0.75, c - r * 1.05 + math.sin(a) * r * 0.35 + r * 0.3)
            pygame.draw.polygon(s, (60, 150, 50), [(c - r * 0.12, c - r * 1.0), (c + r * 0.12, c - r * 1.0), tip])
        pygame.draw.line(s, (50, 120, 40), (c, c - r * 1.05), (c + r * 0.05, c - r * 1.3), SS * 3)
    elif ft.shape == "dragon":
        for k in range(9):
            a = k / 9 * math.tau + 0.3
            bx, by = c + math.cos(a) * r * 0.85, c + math.sin(a) * r * 1.0
            tx, ty = c + math.cos(a + 0.35) * r * 1.22, c + math.sin(a + 0.35) * r * 1.3
            pygame.draw.polygon(s, ft.skin, [(bx - math.sin(a) * r * 0.18, by + math.cos(a) * r * 0.18), (bx + math.sin(a) * r * 0.18, by - math.cos(a) * r * 0.18), (tx, ty)])
            pygame.draw.line(s, ft.skin2, ((bx + tx) / 2, (by + ty) / 2), (tx, ty), SS * 3)
    elif ft.shape == "banana":
        a, b = _banana_tips(c, r)
        pygame.draw.circle(s, (70, 45, 20), a, r * 0.09)
        pygame.draw.line(s, (110, 80, 30), b, (b[0] + r * 0.1, b[1] - r * 0.22), int(SS * 5))
    elif ft.name == "watermelon":
        pygame.draw.circle(s, (120, 150, 60), (c, c - r * 0.97), r * 0.06)


def _face(ft, d):
    """The cut cross-section as a full disc of diameter d (supersampled)."""
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    c = d / 2
    r = d / 2
    rng = random.Random(ft.name + "face")
    pygame.draw.circle(s, ft.skin if ft.shape != "banana" else shade_of(ft.skin, 0.9), (c, c), r)
    pygame.draw.circle(s, ft.rim, (c, c), r * 0.9)
    pygame.draw.circle(s, ft.flesh, (c, c), r * 0.83)
    n = ft.name
    if n == "watermelon":
        pygame.draw.circle(s, (38, 110, 44), (c, c), r, int(r * 0.07))
        for k in range(14):
            a = k / 14 * math.tau + rng.uniform(-0.1, 0.1)
            dd = r * (0.42 if k % 2 else 0.6)
            x, y = c + math.cos(a) * dd, c + math.sin(a) * dd
            seed = pygame.Surface((int(r * 0.09), int(r * 0.17)), pygame.SRCALPHA)
            pygame.draw.ellipse(seed, (30, 20, 20), seed.get_rect())
            seed = pygame.transform.rotate(seed, -math.degrees(a) + 90)
            s.blit(seed, seed.get_rect(center=(x, y)))
    elif n in ("orange", "lemon"):
        for k in range(10):
            a = k / 10 * math.tau
            pygame.draw.line(s, ft.rim, (c, c), (c + math.cos(a) * r * 0.83, c + math.sin(a) * r * 0.83), max(2, int(r * 0.05)))
        for k in range(10):
            a = (k + 0.5) / 10 * math.tau
            pygame.draw.circle(s, shade_of(ft.flesh, 1.12), (c + math.cos(a) * r * 0.5, c + math.sin(a) * r * 0.5), r * 0.12)
        pygame.draw.circle(s, ft.rim, (c, c), r * 0.1)
    elif n == "apple":
        for k in range(5):
            a = k / 5 * math.tau - math.pi / 2
            pygame.draw.line(s, (220, 205, 160), (c, c), (c + math.cos(a) * r * 0.32, c + math.sin(a) * r * 0.32), max(2, int(r * 0.04)))
            pe = pygame.Rect(0, 0, r * 0.1, r * 0.18)
            pe.center = (c + math.cos(a) * r * 0.22, c + math.sin(a) * r * 0.22)
            pygame.draw.ellipse(s, (90, 50, 25), pe)
    elif n == "kiwi":
        for k in range(40):
            a = k / 40 * math.tau
            pygame.draw.line(s, shade_of(ft.flesh, 1.18), (c, c), (c + math.cos(a) * r * 0.8, c + math.sin(a) * r * 0.8), 2)
        for k in range(26):
            a = k / 26 * math.tau
            pygame.draw.circle(s, (25, 20, 15), (c + math.cos(a) * r * 0.36, c + math.sin(a) * r * 0.36), r * 0.035)
        pygame.draw.ellipse(s, (235, 242, 200), pygame.Rect(0, 0, r * 0.5, r * 0.36).move(c - r * 0.25, c - r * 0.18))
    elif n == "coconut":
        pygame.draw.circle(s, ft.skin, (c, c), r, int(r * 0.14))
        pygame.draw.circle(s, (215, 230, 235), (c, c), r * 0.6)
    elif n == "peach":
        pygame.draw.circle(s, shade_of(ft.flesh, 0.9), (c, c), r * 0.55)
        pygame.draw.ellipse(s, (150, 60, 40), pygame.Rect(0, 0, r * 0.45, r * 0.6).move(c - r * 0.225, c - r * 0.3))
    elif n == "plum":
        pygame.draw.ellipse(s, (170, 90, 40), pygame.Rect(0, 0, r * 0.35, r * 0.5).move(c - r * 0.175, c - r * 0.25))
    elif n == "strawberry":
        pygame.draw.ellipse(s, (255, 225, 225), pygame.Rect(0, 0, r * 0.45, r * 1.1).move(c - r * 0.225, c - r * 0.55))
    elif n == "dragonfruit":
        for _ in range(110):
            a, dd = rng.uniform(0, math.tau), r * 0.78 * math.sqrt(rng.random())
            pygame.draw.circle(s, (20, 20, 20), (c + math.cos(a) * dd, c + math.sin(a) * dd), max(1.5, r * 0.025))
    elif ft.shape == "banana":
        for k in range(3):
            a = k / 3 * math.tau
            pygame.draw.circle(s, (150, 110, 60), (c + math.cos(a) * r * 0.15, c + math.sin(a) * r * 0.15), r * 0.05)
    # wet sheen
    sheen = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.ellipse(sheen, (255, 255, 255, 40), pygame.Rect(0, 0, r * 0.9, r * 0.5).move(c - r * 0.6, c - r * 0.55))
    s.blit(sheen, (0, 0))
    return s


def _down(s):
    w, h = s.get_size()
    return pygame.transform.smoothscale(s, (max(1, w // SS), max(1, h // SS)))


def load_sprite(name, ext="png"):
    """Loaded sprite surface, or None when the file is missing (callers fall back to procedural art)."""
    path = os.path.join(SPRITE_DIR, f"{name}.{ext}")
    if not os.path.isfile(path):
        return None
    img = pygame.image.load(path)
    return img.convert_alpha() if ext == "png" else img.convert()


def _disc(img, d):
    out = pygame.Surface((d, d), pygame.SRCALPHA)
    out.blit(pygame.transform.smoothscale(img, (d, d)), (0, 0))
    mask = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (d / 2, d / 2), d / 2)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


class FruitArt:
    """whole, half (cut face at the bottom edge, outward = up), face disc, shadow."""

    def __init__(self, ft):
        self.ft = ft
        if self._load_sprites(ft):
            return
        rng = random.Random(ft.name)
        r = ft.r * SS
        size = int(ft.r * 2.9) * SS
        c = size / 2
        skin = pygame.Surface((size, size), pygame.SRCALPHA)
        skin.fill((*ft.skin, 255))
        _details(ft, skin, c, r, rng)
        shade = pygame.transform.smoothscale(_sphere_shade(int(r * 2.2)), (int(r * 2.2), int(r * 2.2)))
        full_shade = pygame.Surface((size, size))
        full_shade.fill((255, 255, 255))
        full_shade.blit(shade, shade.get_rect(center=(c, c)))
        skin.blit(full_shade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        hi = _highlight(size, c - r * 0.38, c - r * 0.42, r * 0.42, 150 if ft.name != "coconut" else 60)
        skin.blit(hi, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        mask = _shape_mask(ft, size)
        skin.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        outline = pygame.mask.from_surface(mask, 127).outline(2)
        if len(outline) > 2:
            pygame.draw.lines(skin, shade_of(ft.skin, 0.45), True, outline, int(SS * 2.5))
        _after_mask(ft, skin, c, r, rng)
        self.whole = _down(skin)
        self.face = _down(_face(ft, int(r * 2)))

        # half: top half of the whole + the squashed face along the cut
        wh = self.whole
        ww, hh = wh.get_size()
        fw = int(ft.r * 2 * (1.12 if ft.shape in ("lemon", "oval") else 1.0))
        fh = max(6, int(ft.r * 0.62))
        if ft.shape == "banana":
            # cut across the crescent's middle: keep the left part, face is a small upright oval
            top = wh.subsurface((0, 0, ww // 2, hh)).copy()
            body_y = hh / 2 - ft.r * 0.35 + ft.r * 0.78
            face = pygame.transform.smoothscale(self.face, (int(ft.r * 0.26), int(ft.r * 0.56)))
            half = pygame.Surface((ww // 2 + face.get_width() // 2, hh), pygame.SRCALPHA)
            half.blit(top, (0, 0))
            half.blit(face, face.get_rect(center=(ww // 2, body_y)))
            self.half_local = 180  # outward direction of this half in degrees (math convention)
        else:
            top = wh.subsurface((0, 0, ww, hh // 2)).copy()
            face = pygame.transform.smoothscale(self.face, (fw, fh))
            half = pygame.Surface((ww, hh // 2 + fh // 2), pygame.SRCALPHA)
            half.blit(top, (0, 0))
            half.blit(face, face.get_rect(center=(ww // 2, hh // 2)))
            self.half_local = 90
        self.half = half
        self.shadow = make_shadow(self.whole)
        self.half_shadow = make_shadow(self.half)

    def _load_sprites(self, ft):
        whole = load_sprite(ft.name)
        if ft.special:  # specials reuse the banana half, tinted with their juice colour
            half = load_sprite("banana_half")
            if half is not None:
                half = half.copy()
                half.fill((*ft.juice, 255), special_flags=pygame.BLEND_RGB_MULT)
        else:
            half = load_sprite(ft.name + "_half")
        if whole is None or half is None:
            return False
        self.whole, self.half = whole, half
        # every generated half has the cut face up and the rind dome down -> outward is 270 deg
        self.half_local = 270
        if ft.name == "watermelon":
            hw, hh = half.get_size()
            crop = half.subsurface((0, 0, hw, max(1, int(hh * 0.45)))).copy()
            self.face = _disc(crop, ft.r * 2)
        else:
            self.face = _down(_face(ft, int(ft.r * SS * 2)))
        self.shadow = make_shadow(self.whole)
        self.half_shadow = make_shadow(self.half)
        return True


def make_shadow(img, alpha=90):
    sil = img.copy()
    sil.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MIN)  # rgb -> 0, keep alpha
    w, h = sil.get_size()
    small = pygame.transform.smoothscale(sil, (max(1, w // 4), max(1, h // 4)))
    blur = pygame.transform.smoothscale(small, (w, h))
    blur.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)  # baked in: rotozoom drops set_alpha
    return blur


def load_bomb():
    """(sprite, fuse tip offset from centre, shadow) or None. The tip is the topmost opaque pixel."""
    img = load_sprite("bomb")
    if img is None:
        return None
    mask = pygame.mask.from_surface(img, 8)
    w, h = img.get_size()
    for y in range(h):
        xs = [x for x in range(w) if mask.get_at((x, y))]
        if xs:
            tip = (sum(xs) / len(xs) - w / 2, y - h / 2)
            return img, tip, make_shadow(img)
    return None


def make_bomb(r=38):
    R = r * SS
    size = int(r * 3.0) * SS
    c = size / 2
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    s.fill((48, 46, 56, 255))
    shade = _sphere_shade(int(R * 2.2), 1.1)
    full = pygame.Surface((size, size))
    full.fill((255, 255, 255))
    full.blit(shade, shade.get_rect(center=(c, c)))
    s.blit(full, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    s.blit(_highlight(size, c - R * 0.4, c - R * 0.42, R * 0.38, 170), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), R)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # hanko-red warning seal ring on the iron
    pygame.draw.circle(s, (170, 35, 30), (c + R * 0.05, c + R * 0.12), R * 0.48, SS * 3)
    pygame.draw.line(s, (170, 35, 30), (c - R * 0.25, c - R * 0.13), (c + R * 0.35, c + R * 0.37), SS * 4)
    pygame.draw.line(s, (170, 35, 30), (c + R * 0.35, c - R * 0.13), (c - R * 0.25, c + R * 0.37), SS * 4)
    cap = pygame.Rect(0, 0, R * 0.42, R * 0.3)
    cap.center = (c + R * 0.55, c - R * 0.78)
    pygame.draw.rect(s, (120, 120, 130), cap, border_radius=SS * 3)
    pygame.draw.rect(s, (70, 70, 78), cap, SS * 2, border_radius=SS * 3)
    fuse = [(cap.centerx, cap.top), (cap.centerx + R * 0.15, cap.top - R * 0.25), (cap.centerx + R * 0.38, cap.top - R * 0.32)]
    pygame.draw.lines(s, (180, 150, 100), False, fuse, SS * 4)
    img = _down(s)
    tip = ((fuse[-1][0] - c) / SS, (fuse[-1][1] - c) / SS)  # offset from centre, unrotated
    return img, tip, make_shadow(img)


def make_stain(color, r, rng):
    size = int(r * 5)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2
    col = (*color, 150)
    pygame.draw.circle(s, col, (c, c), r * 0.75)
    for _ in range(rng.randint(10, 16)):
        a, d = rng.uniform(0, math.tau), rng.uniform(0.4, 1.1) * r
        pygame.draw.circle(s, col, (c + math.cos(a) * d, c + math.sin(a) * d), rng.uniform(0.2, 0.45) * r)
    for _ in range(rng.randint(10, 20)):
        a, d = rng.uniform(0, math.tau), rng.uniform(1.2, 2.3) * r
        pygame.draw.circle(s, col, (c + math.cos(a) * d, c + math.sin(a) * d), rng.uniform(0.04, 0.13) * r)
    for _ in range(rng.randint(2, 4)):  # drips running down the wall
        x = c + rng.uniform(-0.6, 0.6) * r
        L = rng.uniform(0.6, 1.6) * r
        wdt = rng.uniform(0.07, 0.14) * r
        pygame.draw.rect(s, col, pygame.Rect(x - wdt / 2, c, wdt, L))
        pygame.draw.circle(s, col, (x, c + L), wdt * 0.9)
    return s


def _vignette(bg):
    vig = pygame.Surface((W, H))
    vig.fill((95, 95, 95))
    for i in range(30):
        t = i / 29
        v = int(95 + 160 * t ** 0.6)
        rect = pygame.Rect(0, 0, W * 1.5 * (1 - t * 0.55), H * 1.6 * (1 - t * 0.55))
        rect.center = (W / 2, H * 0.42)
        pygame.draw.ellipse(vig, (v, v, v), rect)
    bg.blit(vig, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


def load_background():
    """Photo wall darkened so it sits behind the fruit, plus the vignette; None if the file is missing."""
    bg = load_sprite("background", "jpg")
    if bg is None:
        return None
    bg.fill((165, 150, 140), special_flags=pygame.BLEND_RGB_MULT)
    _vignette(bg)
    return bg


def make_background(seed=7):
    rng = random.Random(seed)
    bg = pygame.Surface((W, H))
    x = 0
    while x < W:
        pw = rng.randint(150, 230)
        base = lerp(CEDAR, (70, 40, 26), rng.random())
        pygame.draw.rect(bg, base, (x, 0, pw, H))
        for _ in range(28):  # grain
            gx = x + rng.uniform(4, pw - 4)
            amp, ph, fr = rng.uniform(2, 9), rng.uniform(0, 6), rng.uniform(0.004, 0.012)
            col = shade_of(base, rng.uniform(0.8, 1.12))
            pts = [(gx + math.sin(y * fr + ph) * amp, y) for y in range(0, H + 20, 20)]
            pygame.draw.lines(bg, col, False, pts, rng.choice((1, 1, 2)))
        if rng.random() < 0.6:  # knot
            kx, ky = x + rng.uniform(25, pw - 25), rng.uniform(60, H - 60)
            for i in range(6):
                pygame.draw.ellipse(bg, shade_of(base, 0.75 + i * 0.04), pygame.Rect(0, 0, 40 - i * 6, 22 - i * 3).move(kx - 20 + i * 3, ky - 11 + i * 1.5), 2)
        pygame.draw.line(bg, (28, 16, 11), (x, 0), (x, H), 4)
        pygame.draw.line(bg, shade_of(base, 1.2), (x + 4, 0), (x + 4, H), 1)
        for ny in (70, H - 70):
            pygame.draw.circle(bg, (40, 30, 26), (x + pw / 2, ny), 5)
            pygame.draw.circle(bg, (120, 105, 90), (x + pw / 2 - 1, ny - 1), 2)
        x += pw
    # lantern light from above + vignette
    light = pygame.Surface((W, H))
    for i in range(40):
        t = i / 39
        v = int(70 * t * t)
        rect = pygame.Rect(0, 0, W * 1.6 * (1 - t * 0.8), H * 1.5 * (1 - t * 0.8))
        rect.center = (W / 2, H * 0.02)
        pygame.draw.ellipse(light, (v, int(v * 0.75), int(v * 0.45)), rect)
    bg.blit(light, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    _vignette(bg)
    return bg


def make_seal(fonts, glyph, size, rng=None):
    """A hanko stamp on a torn washi slip — the game's signature mark."""
    rng = rng or random.Random(glyph)
    pad = int(size * 0.18)
    tot = size + pad * 2
    s = pygame.Surface((tot, tot), pygame.SRCALPHA)
    # torn paper slip
    pts = []
    for side in range(4):
        for k in range(9):
            t = k / 9
            corners = [(pad * 0.4, pad * 0.4), (tot - pad * 0.4, pad * 0.4), (tot - pad * 0.4, tot - pad * 0.4), (pad * 0.4, tot - pad * 0.4)]
            a, b = corners[side], corners[(side + 1) % 4]
            pts.append((a[0] + (b[0] - a[0]) * t + rng.uniform(-3, 3), a[1] + (b[1] - a[1]) * t + rng.uniform(-3, 3)))
    pygame.draw.polygon(s, (*WASHI, 245), pts)
    for _ in range(int(size * 0.8)):  # paper fibres
        x, y = rng.uniform(pad, tot - pad), rng.uniform(pad, tot - pad)
        pygame.draw.line(s, (220, 205, 175, 120), (x, y), (x + rng.uniform(-6, 6), y + rng.uniform(-3, 3)), 1)
    # stamp
    stamp = pygame.Surface((size, size), pygame.SRCALPHA)
    br = int(size * 0.08)
    pygame.draw.rect(stamp, HANKO, stamp.get_rect().inflate(-br, -br), int(size * 0.07), border_radius=int(size * 0.14))
    font = pygame.font.SysFont(fonts.kanji, int(size * 0.66), bold=True)
    g = font.render(glyph, True, HANKO)
    stamp.blit(g, g.get_rect(center=(size / 2, size / 2 + size * 0.02)))
    for _ in range(int(size * 1.6)):  # ink erosion
        pygame.draw.circle(stamp, (0, 0, 0, 0), (rng.uniform(0, size), rng.uniform(0, size)), rng.uniform(0.6, 2.2))
    s.blit(stamp, (pad, pad))
    return s


def make_soft(radius, color, alpha=True):
    d = radius * 2 + 2
    if alpha:
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        for i in range(12):
            t = i / 11
            pygame.draw.circle(s, (*color, int(40 * t + 10)), (d / 2, d / 2), radius * (1 - t * 0.85))
    else:
        s = pygame.Surface((d, d))
        for i in range(12):
            t = i / 11
            pygame.draw.circle(s, lerp((0, 0, 0), color, t * t), (d / 2, d / 2), radius * (1 - t * 0.9))
    return s


def make_frost():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(24):
        t = i / 23
        pygame.draw.rect(s, (190, 230, 255, int(12 * (1 - t))), pygame.Rect(0, 0, W, H).inflate(-t * 260, -t * 200), int(14))
    rng = random.Random(3)
    for _ in range(90):  # ice crystals at the edges
        side = rng.randint(0, 3)
        x = rng.uniform(0, W) if side < 2 else (rng.uniform(0, 60) if side == 2 else W - rng.uniform(0, 60))
        y = rng.uniform(0, 60) if side == 0 else (H - rng.uniform(0, 60) if side == 1 else rng.uniform(0, H))
        L = rng.uniform(6, 18)
        for k in range(3):
            a = k * math.pi / 3 + rng.uniform(0, 1)
            pygame.draw.line(s, (220, 245, 255, 150), (x - math.cos(a) * L, y - math.sin(a) * L), (x + math.cos(a) * L, y + math.sin(a) * L), 1)
    return s


class Art:
    def __init__(self):
        self.fonts = Fonts()
        self.fruits = {k: FruitArt(ft) for k, ft in FRUITS.items()}
        self.bomb, self.bomb_tip, self.bomb_shadow = load_bomb() or make_bomb()
        self.bg = load_background() or make_background()
        rng = random.Random(11)
        self.stains = {k: [make_stain(ft.juice, ft.r, rng) for _ in range(3)] for k, ft in FRUITS.items()}
        self.frost = make_frost()
        self._seals = {}
        self._soft = {}

    def seal(self, glyph, size=120):
        key = (glyph, size)
        if key not in self._seals:
            self._seals[key] = make_seal(self.fonts, glyph, size)
        return self._seals[key]

    def soft(self, radius, color, alpha=True):
        radius = max(2, int(radius) // 3 * 3)
        key = (radius, color, alpha)
        if key not in self._soft:
            self._soft[key] = make_soft(radius, color, alpha)
        return self._soft[key]
