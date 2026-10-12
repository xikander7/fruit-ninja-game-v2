"""Juice: particles, stains, blade trail, screen shake, popups and hanko stamps."""
import math
import random
from collections import deque

import pygame

from .settings import W, H, GRAVITY, WASHI, GOLD


class P:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size", "color", "kind", "grav", "rot", "vr")

    def __init__(self, x, y, vx, vy, life, size, color, kind, grav=1.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.size, self.color, self.kind, self.grav = size, color, kind, grav
        self.rot, self.vr = random.uniform(0, 360), random.uniform(-200, 200)


class Particles:
    CAP = 1400

    def __init__(self, art):
        self.art = art
        self.items = []

    def add(self, *a, **k):
        if len(self.items) < self.CAP:
            self.items.append(P(*a, **k))

    def juice(self, x, y, color, nx, ny, n=22):
        for _ in range(n):
            side = random.choice((-1, 1))
            sp = random.uniform(120, 520)
            a = math.atan2(ny * side, nx * side) + random.uniform(-0.9, 0.9)
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp - 120, random.uniform(0.4, 0.9), random.uniform(2, 6), color, "drop")
        for _ in range(n // 3):  # mist
            a = random.uniform(0, math.tau)
            self.add(x, y, math.cos(a) * 80, math.sin(a) * 80, 0.35, random.uniform(10, 22), color, "glow", 0.0)

    def sparks(self, x, y, color, n=30, speed=700, life=0.6):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.2, 1) * speed
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.3, 1) * life, random.uniform(1.5, 3.5), color, "spark", 0.5)

    def smoke(self, x, y, n=18):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(30, 220)
            g = random.randint(40, 80)
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp - 40, random.uniform(0.8, 1.6), random.uniform(18, 46), (g, g - 6, g - 10), "smoke", -0.05)

    def ink(self, x, y, color, n=16):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(150, 480)
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.25, 0.5), random.uniform(2, 5), color, "drop", 0.3)

    def petal(self):
        self.add(random.uniform(-50, W), -20, random.uniform(20, 70), random.uniform(30, 70), 14, random.uniform(5, 8), (255, 190, 210), "petal", 0.0)

    def update(self, dt):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += GRAVITY * p.grav * dt
            if p.kind == "smoke":
                p.vx *= 0.96
                p.vy *= 0.96
                p.size += 18 * dt
            elif p.kind == "petal":
                p.vx += math.sin(p.life * 2 + p.rot) * 30 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.vr * dt
            if p.y < H + 60:
                alive.append(p)
        self.items = alive

    def draw(self, surf, add):
        for p in self.items:
            t = p.life / p.max
            if p.kind == "drop":
                pygame.draw.circle(surf, p.color, (p.x, p.y), max(1, p.size * (0.4 + 0.6 * t)))
            elif p.kind == "smoke":
                img = self.art.soft(p.size, p.color)
                img.set_alpha(int(255 * t))
                surf.blit(img, img.get_rect(center=(p.x, p.y)))
            elif p.kind == "petal":
                r = pygame.Rect(0, 0, p.size * 1.8, p.size * abs(math.sin(math.radians(p.rot))) + 2)
                r.center = (p.x, p.y)
                pygame.draw.ellipse(surf, p.color, r)
            elif p.kind == "spark":
                c = tuple(int(v * t) for v in p.color)
                pygame.draw.line(add, c, (p.x, p.y), (p.x - p.vx * 0.03, p.y - p.vy * 0.03), max(1, int(p.size)))
            elif p.kind == "glow":
                img = self.art.soft(p.size, tuple(int(v * t * 0.5) for v in p.color), False)
                add.blit(img, img.get_rect(center=(p.x, p.y)), special_flags=pygame.BLEND_RGB_ADD)


class Stains:
    """Juice splashes that stick to the dojo wall and slowly fade."""

    def __init__(self, art):
        self.art = art
        self.items = []

    def add(self, kind, x, y):
        img = random.choice(self.art.stains[kind])
        img = pygame.transform.rotate(img, random.choice((0, 0, 8, -8)))
        self.items.append([img, x, y, 0.0])
        if len(self.items) > 30:
            self.items.pop(0)

    def update(self, dt):
        for s in self.items:
            s[3] += dt
        self.items = [s for s in self.items if s[3] < 7]

    def draw(self, surf):
        for img, x, y, age in self.items:
            img.set_alpha(int(255 * min(1, (7 - age) / 3)))
            surf.blit(img, img.get_rect(center=(x, y)))


class Trail:
    LIFE = 0.13

    def __init__(self):
        self.pts = deque()

    def add(self, x, y, t):
        self.pts.append((x, y, t))

    def cut(self):
        self.pts.append(None)  # break between swipes

    def update(self, now):
        while self.pts and (self.pts[0] is None or now - self.pts[0][2] > self.LIFE):
            self.pts.popleft()

    def draw(self, add, colors, now):
        runs, cur = [], []
        for p in self.pts:
            if p is None:
                runs.append(cur)
                cur = []
            else:
                cur.append(p)
        runs.append(cur)
        for run in runs:
            if len(run) < 2:
                continue
            for color, width in ((colors[0], 22), (colors[1], 11), (colors[2], 4.5)):
                left, right = [], []
                n = len(run)
                for i, (x, y, t) in enumerate(run):
                    a = run[max(0, i - 1)]
                    b = run[min(n - 1, i + 1)]
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    L = math.hypot(dx, dy) or 1
                    age = 1 - (now - t) / self.LIFE
                    w = width * max(0.0, age) * (i / (n - 1)) ** 0.6
                    left.append((x - dy / L * w, y + dx / L * w))
                    right.append((x + dy / L * w, y - dx / L * w))
                pygame.draw.polygon(add, color, left + right[::-1])


class Shake:
    def __init__(self):
        self.trauma = 0.0
        self.t = 0.0

    def kick(self, amount):
        self.trauma = min(1.0, self.trauma + amount)

    def update(self, dt):
        self.t += dt
        self.trauma = max(0.0, self.trauma - dt * 1.6)

    def offset(self):
        k = self.trauma ** 2 * 26
        return (k * math.sin(self.t * 71.3) * math.cos(self.t * 13.1), k * math.sin(self.t * 59.7 + 1.3))


class Popups:
    def __init__(self, fonts):
        self.fonts = fonts
        self.items = []

    def add(self, text, x, y, color=WASHI, big=False):
        font = self.fonts.mid if big else self.fonts.small
        img = font.render(text, True, color)
        sh = font.render(text, True, (0, 0, 0))
        self.items.append([img, sh, x, y, 0.0])

    def update(self, dt):
        for p in self.items:
            p[3] -= 60 * dt
            p[4] += dt
        self.items = [p for p in self.items if p[4] < 0.9]

    def draw(self, surf):
        for img, sh, x, y, age in self.items:
            a = int(255 * min(1, (0.9 - age) / 0.4))
            k = 1 + max(0, 0.15 - age) * 3  # pop in
            for im, off in ((sh, 2), (img, 0)):
                s = pygame.transform.rotozoom(im, 0, k) if k > 1.001 else im
                s.set_alpha(a)
                surf.blit(s, s.get_rect(center=(x + off, y + off)))


class Stamp:
    """A hanko seal that slams onto the screen. The game's signature beat."""

    DUR = 1.4

    def __init__(self, art, glyph, caption, x, y, size=120, color=GOLD):
        self.seal = art.seal(glyph, size)
        self.cap = art.fonts.mid.render(caption, True, color) if caption else None
        self.cap_sh = art.fonts.mid.render(caption, True, (0, 0, 0)) if caption else None
        self.x = min(max(x, size), W - size)
        self.y = min(max(y, size), H - size)
        self.rot = random.uniform(-9, 9)
        self.age = 0.0
        self.landed = False

    def scale(self):
        a = self.age
        if a < 0.11:
            return 2.4 - 1.5 * (a / 0.11)  # slam down from above the paper
        if a < 0.2:
            return 0.9 + 0.1 * ((a - 0.11) / 0.09)
        return 1.0

    def update(self, dt):
        self.age += dt
        return self.age < self.DUR

    def draw(self, surf):
        k = self.scale()
        alpha = int(255 * min(1, self.age / 0.06, (self.DUR - self.age) / 0.35))
        img = pygame.transform.rotozoom(self.seal, self.rot, k)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(self.x, self.y)))
        if self.cap and self.age > 0.1:
            for im, off in ((self.cap_sh, 3), (self.cap, 0)):
                im.set_alpha(alpha)
                surf.blit(im, im.get_rect(center=(self.x + off, self.y + self.seal.get_height() * 0.55 + off)))
