"""Juice: particles, stains, blade trail, screen shake, popups and hanko stamps."""
import math
import random
from collections import deque

import pygame

from .settings import W, H, GRAVITY, WASHI, GOLD


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def tint(c, k):
    """Mix toward white by k (0 = c, 1 = white)."""
    return tuple(int(v + (255 - v) * k) for v in c)


_GLOW = {}


def glow(art, radius, color, k):
    """Additive soft glow (RGB on black) at brightness k. Finer steps than art.soft, so a big aura shows no
    rings; radius and k are quantised so the cache stays small."""
    radius = max(2, int(radius) // 3 * 3)
    k = round(max(0.0, min(1.0, k)) * 16) / 16
    key = (radius, color, k)
    if key not in _GLOW:
        d = radius * 2 + 2
        s = pygame.Surface((d, d))
        steps = max(8, min(40, radius))
        for i in range(steps):
            t = i / (steps - 1)
            pygame.draw.circle(s, shade(color, k * t * t), (d / 2, d / 2), radius * (1 - t * 0.95))
        _GLOW[key] = s
    return _GLOW[key]


def catmull_rom(pts, sub=4):
    """Uniform Catmull-Rom through every control point, `sub` samples per segment.

    Points are tuples of any length (x, y, t...); every component is interpolated. Output[i * sub] == pts[i].
    """
    n = len(pts)
    if n < 2:
        return list(pts)
    out = []
    dims = range(len(pts[0]))
    for i in range(n - 1):
        p0, p1, p2 = pts[max(0, i - 1)], pts[i], pts[i + 1]
        p3 = pts[min(n - 1, i + 2)]
        for s in range(sub):
            u = s / sub
            u2, u3 = u * u, u * u * u
            out.append(tuple(0.5 * (2 * p1[d] + (p2[d] - p0[d]) * u + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * u2
                                    + (3 * p1[d] - p0[d] - 3 * p2[d] + p3[d]) * u3) for d in dims))
    out.append(tuple(pts[-1]))
    return out


_RAYS = {}


def ray_burst(radius, color):
    """Six soft light rays on black (for additive blending), fading out from the centre."""
    key = (radius, color)
    if key not in _RAYS:
        d = radius * 2 + 2
        s = pygame.Surface((d, d))
        c = d / 2
        for k in range(6):
            a = k * math.tau / 6
            for i in range(8):  # stacked wedges: dim and wide outside, bright and thin in the middle
                t = i / 7
                h = 0.16 * (1 - t) + 0.025
                col = shade(color, 0.15 + 0.85 * t * t)
                pygame.draw.polygon(s, col, [(c, c), (c + math.cos(a - h) * radius, c + math.sin(a - h) * radius),
                                             (c + math.cos(a + h) * radius, c + math.sin(a + h) * radius)])
        fall = pygame.Surface((d, d))
        for i in range(24):  # radial falloff, multiplied in; dim at the very centre so rays don't stripe the fruit
            t = i / 23
            v = int(255 * t ** 1.6 * min(1.0, (1 - t) / 0.28 + 0.15))
            pygame.draw.circle(fall, (v, v, v), (c, c), radius * (1 - t * 0.97))
        s.blit(fall, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        _RAYS[key] = s
    return _RAYS[key]


class P:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size", "color", "kind", "grav", "rot", "vr", "c2", "shape")

    def __init__(self, x, y, vx, vy, life, size, color, kind, grav=1.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.size, self.color, self.kind, self.grav = size, color, kind, grav
        self.rot, self.vr = random.uniform(0, 360), random.uniform(-200, 200)
        self.c2 = self.shape = None


class Particles:
    CAP = 1400

    def __init__(self, art):
        self.art = art
        self.items = []
        self.blur = 1.0  # slow-mo time scale: streaks shorten in slow-mo, like real motion blur

    def add(self, *a, **k):
        if len(self.items) < self.CAP:
            p = P(*a, **k)
            self.items.append(p)
            return p
        return None

    def drop(self, x, y, vx, vy, life, size, color):
        p = self.add(x, y, vx, vy, life, size, color, "drop")
        if p:
            p.c2 = tint(color, 0.55)  # wet highlight along the droplet

    def juice(self, x, y, color, nx, ny, n=35, spread=30):
        """Juice leaves the whole cut face, flung mostly along the normal: heavy round drops, many fine ones,
        a brief translucent sheet along the cut and a wet emissive mist."""
        ux, uy = ny, -nx  # along the cut
        for side in (1, -1):  # the sheet of juice torn off the cut face; gone in ~0.15 s
            p = self.add(x, y, 0, 0, 0.15, spread * 2.2, color, "sheet", 0.0)
            if p:
                p.shape = (ux, uy, nx * side, ny * side)
        for i in range(n + 10):
            side = random.choice((-1, 1))
            big = i < 10  # a few heavy drops (5-10 px heads); the rest is fine spray
            sp = 80 + (300 * random.random() ** 1.4 if big else 520 * random.random())
            a = math.atan2(ny * side, nx * side) + random.uniform(-0.8, 0.8)
            o = random.uniform(-1, 1) * spread
            vx, vy = math.cos(a) * sp, math.sin(a) * sp - 120
            lead = random.uniform(0.0, 0.05)  # staggered release: juice keeps coming off the face, not in one row
            self.drop(x + ux * o + vx * lead, y + uy * o + vy * lead, vx, vy, random.uniform(0.55, 1.0),
                      random.uniform(2.6, 5.0) if big else random.uniform(1.3, 2.6), shade(color, random.uniform(0.72, 1.05)))
        for side in (1, -1):  # two curved sprays: a fan of droplets with a smooth speed profile reads as one sheet
            a0 = math.atan2(ny * side, nx * side) + random.uniform(-0.25, 0.25)
            life = random.uniform(0.45, 0.6)
            for i in range(12):
                u = i / 11 - 0.5
                sp = 380 + 260 * math.cos(math.pi * u) + random.uniform(-30, 30)
                a = a0 + u * 1.1
                o = u * spread * 1.6
                self.drop(x + ux * o, y + uy * o, math.cos(a) * sp, math.sin(a) * sp - 160, life,
                          1.4 + 2.2 * math.cos(math.pi * u), color)
        for _ in range(10):  # mist on the emissive layer: the bloom turns it into a wet glow
            a = random.uniform(0, math.tau)
            sp = random.uniform(90, 220)
            self.add(x + ux * random.uniform(-1, 1) * spread, y + uy * random.uniform(-1, 1) * spread,
                     math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.35, 0.55), random.uniform(16, 30), color, "glow", 0.0)

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
            self.drop(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.25, 0.5), random.uniform(2, 4), color)

    def shards(self, x, y, n=10):
        """Dark casing fragments of a bomb: tumbling polygons with gravity and a cooling hot edge."""
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(350, 900)
            p = self.add(x, y, math.cos(a) * sp, math.sin(a) * sp - 250, random.uniform(0.9, 1.4), random.uniform(6, 13),
                         (255, 120, 40), "shard", 1.0)
            if p:
                p.vr = random.uniform(-720, 720)
                m = random.randint(4, 6)
                p.shape = [(random.uniform(0.45, 1.0), k * math.tau / m + random.uniform(-0.3, 0.3)) for k in range(m)]

    def embers(self, x, y, n=40, speed=650):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.15, 1) * speed
            self.add(x, y, math.cos(a) * sp, math.sin(a) * sp - 120, random.uniform(0.7, 1.6), random.uniform(1.5, 3),
                     random.choice(((255, 150, 50), (255, 190, 90), (255, 110, 30))), "ember", 0.35)

    def mote(self, x=None, y=None):
        """Dust hanging in the lantern light: tiny, slow, twinkling."""
        x = random.uniform(0, W) if x is None else x
        y = random.uniform(0, H) if y is None else y
        p = self.add(x, y, random.uniform(-8, 8), random.uniform(-10, 4), random.uniform(7, 13), random.choice((1, 1, 2)),
                     random.choice(((255, 214, 160), (230, 200, 170), (255, 190, 130))), "mote", 0.0)
        if p:
            p.vr = random.uniform(1.5, 4.0)  # twinkle rate

    def lantern_ember(self):
        p = self.add(random.uniform(W * 0.05, W * 0.95), H + 10, random.uniform(-20, 20), random.uniform(-110, -60),
                     random.uniform(4, 7), 2, (255, 140, 50), "ember", -0.01)
        if p:
            p.vr = random.uniform(2, 5)

    def update(self, dt):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            k = p.kind
            p.vy += GRAVITY * p.grav * dt
            if k == "smoke":
                p.vx *= 0.96
                p.vy *= 0.96
                p.size += 18 * dt
            elif k == "drop":
                d = 1 - 0.8 * dt  # a little air drag so sprays curl over instead of flying straight
                p.vx *= d
                p.vy *= d
            elif k == "ember":
                d = 1 - 1.5 * dt
                p.vx = p.vx * d + math.sin(p.life * 3 + p.rot) * 40 * dt
                p.vy *= d
            elif k == "mote":
                p.vx += math.sin(p.life * 0.7 + p.rot) * 6 * dt
                p.vy += math.cos(p.life * 0.5 + p.rot) * 4 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if k != "mote" and k != "ember":
                p.rot += p.vr * dt
            if p.y < H + 60:
                alive.append(p)
        self.items = alive

    def draw(self, surf, add):
        line, circle = pygame.draw.line, pygame.draw.circle
        for p in self.items:
            k = p.kind
            t = p.life / p.max
            if k == "drop":
                r = p.size * (0.4 + 0.6 * t)
                vx, vy = p.vx, p.vy
                sp = math.hypot(vx, vy) or 1
                dx, dy = vx / sp, vy / sp
                L = max(2.0, sp * 0.018 * self.blur)
                tx, ty = p.x - dx * L, p.y - dy * L
                if r < 1.2:
                    line(surf, p.color, (tx, ty), (p.x, p.y), 2)
                    continue
                if r >= 2.2:  # heavy drop: round head, tail tapering to a point along the velocity, specular
                    tl = L + r * 1.2
                    pygame.draw.polygon(surf, p.color, [(p.x - dy * r, p.y + dx * r), (p.x - dx * tl, p.y - dy * tl),
                                                        (p.x + dy * r, p.y - dx * r)])
                    circle(surf, p.color, (p.x, p.y), r)
                    circle(surf, p.c2, (p.x - r * 0.3, p.y - r * 0.35), r * 0.45)  # lit side of the bead
                    circle(surf, tint(p.color, 0.8), (p.x - r * 0.38, p.y - r * 0.42), max(1.0, r * 0.16))
                    continue
                # velocity-stretched capsule: round head, thinner tail, light core line along it
                line(surf, p.color, (tx, ty), (p.x, p.y), max(2, int(r * 1.7)))
                circle(surf, p.color, (p.x, p.y), r)
                circle(surf, p.color, (tx, ty), r * 0.6)
                line(surf, p.c2, (tx, ty), (p.x - vx / sp * r * 0.4, p.y - vy / sp * r * 0.4), max(1, int(r * 0.5)))
            elif k == "mote":
                tw = 0.55 + 0.45 * math.sin(p.life * p.vr + p.rot)
                fade = min(1.0, t * 4, (1 - t) * 4)
                add.fill(shade(p.color, 0.5 * tw * fade), (p.x, p.y, p.size, p.size))
            elif k == "spark":
                c = shade(p.color, t)
                line(add, c, (p.x, p.y), (p.x - p.vx * 0.03, p.y - p.vy * 0.03), max(1, int(p.size)))
            elif k == "ember":
                fl = (0.7 + 0.3 * math.sin(p.life * 23 + p.rot)) * min(1.0, t * 2.5)
                g = glow(self.art, 9, p.color, fl * 0.45)
                add.blit(g, g.get_rect(center=(p.x, p.y)), special_flags=pygame.BLEND_RGB_ADD)
                add.fill(tint(shade(p.color, fl), 0.3 * fl), (p.x - 1, p.y - 1, p.size, p.size))
            elif k == "glow":
                # peaks mid-life, once it has drifted off the fruit, so the fruit itself doesn't light up
                g = glow(self.art, p.size, p.color, 0.45 * t * min(1.0, (1 - t) * 2.5))
                add.blit(g, g.get_rect(center=(p.x, p.y)), special_flags=pygame.BLEND_RGB_ADD)
            elif k == "shard":
                a = math.radians(p.rot)
                pts = [(p.x + math.cos(a + aa) * rr * p.size, p.y + math.sin(a + aa) * rr * p.size) for rr, aa in p.shape]
                pygame.draw.polygon(surf, (34, 32, 36), pts)
                glint = 45 + int(70 * abs(math.cos(a * 2)))  # one facet catching the lantern light as it tumbles
                line(surf, (glint, glint - 4, glint - 10), pts[0], pts[1], 2)
                heat = t * t
                if heat > 0.05:  # the torn edge is still hot and cools as it flies
                    line(add, shade(p.color, heat * 0.7), pts[1], pts[2], 2)
            elif k == "sheet":
                # translucent fan of juice torn off the cut face: grows outward from the cut line, fades fast
                ux, uy, nx, ny = p.shape
                age = p.max - p.life
                h, d = p.size / 2, 6 + 520 * age
                pts = [(p.x - ux * h, p.y - uy * h)]
                for i in range(1, 8):
                    u = i / 8 * 2 - 1
                    reach = d * (1 - u * u) ** 0.5
                    pts.append((p.x + ux * h * u * (1 + age * 3) + nx * reach, p.y + uy * h * u * (1 + age * 3) + ny * reach))
                pts.append((p.x + ux * h, p.y + uy * h))
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
                tmp = pygame.Surface((int(max(xs)) - x0 + 2, int(max(ys)) - y0 + 2), pygame.SRCALPHA)
                pygame.draw.polygon(tmp, (*p.color, int(110 * t)), [(qx - x0, qy - y0) for qx, qy in pts])
                surf.blit(tmp, (x0, y0))
            elif k == "smoke":
                img = self.art.soft(p.size, p.color)
                img.set_alpha(int(255 * t))
                surf.blit(img, img.get_rect(center=(p.x, p.y)))


_STAIN_CACHE = {}


def wet_stain(color, r, variant):
    """A juice splash: translucent tinted blob with a darker rim where the juice pools, a few specular glints.
    Drawn at 2x and smoothed down so the edge is soft. Drips are grown live by Stains."""
    key = (color, r, variant)
    if key not in _STAIN_CACHE:
        rng = random.Random(hash(key) & 0xFFFF)
        k = 2  # supersample
        size = int(r * 5)
        s = pygame.Surface((size * k, int(r * 6.2) * k), pygame.SRCALPHA)
        c = size / 2
        blobs = [(c, c, r * 0.72)]
        for _ in range(rng.randint(8, 12)):
            a, d = rng.uniform(0, math.tau), rng.uniform(0.35, 0.85) * r
            blobs.append((c + math.cos(a) * d, c + math.sin(a) * d, rng.uniform(0.18, 0.36) * r))
        for _ in range(rng.randint(14, 22)):  # small lobes break up the edge so it isn't a ring of bubbles
            a, d = rng.uniform(0, math.tau), rng.uniform(0.8, 1.2) * r
            blobs.append((c + math.cos(a) * d, c + math.sin(a) * d, rng.uniform(0.04, 0.12) * r))
        flecks = []
        for _ in range(rng.randint(14, 24)):  # fine spatter thrown further out
            a, d = rng.uniform(0, math.tau), rng.uniform(1.25, 2.2) * r
            flecks.append((c + math.cos(a) * d, c + math.sin(a) * d, rng.uniform(0.025, 0.07) * r))
        rim, body = (*shade(color, 0.4), 225), (*shade(color, 0.85), 120)
        for x, y, br in blobs + flecks:
            pygame.draw.circle(s, rim, (x * k, y * k), (br + max(1.5, br * 0.16)) * k)
        for x, y, br in blobs:
            pygame.draw.circle(s, body, (x * k, y * k), br * k)
        for x, y, br in rng.sample(blobs[:12], rng.randint(2, 4)):  # glints up-left: the lanterns are above
            pygame.draw.circle(s, (255, 248, 235, 120), ((x - br * 0.35) * k, (y - br * 0.4) * k), max(1.2, br * 0.13) * k)
            pygame.draw.circle(s, (255, 255, 255, 230), ((x - br * 0.37) * k, (y - br * 0.42) * k), max(0.8, br * 0.06) * k)
        s = pygame.transform.smoothscale(s, (size, int(r * 6.2)))
        drips = []
        for _ in range(rng.randint(2, 4)):
            x = c + rng.uniform(-0.55, 0.55) * r
            drips.append((x, c + r * 0.3, rng.uniform(0.6, 1.8) * r, rng.uniform(0.06, 0.11) * r))
        _STAIN_CACHE[key] = (s, drips)
    return _STAIN_CACHE[key]


class Stains:
    """Wet juice splashes on the dojo wall: drips run down for 1.2 s, then the stain fades over 8 s."""

    GROW, FADE = 1.2, 8.0

    def __init__(self, art):
        self.art = art
        self.items = []

    def add(self, color, r, x, y):
        img, drips = wet_stain(color, r, random.randrange(3))
        self.items.append([img.copy(), drips, x, y, 0.0, (*shade(color, 0.6), 170)])
        if len(self.items) > 30:
            self.items.pop(0)

    def update(self, dt):
        for s in self.items:
            s[4] += dt
        self.items = [s for s in self.items if s[4] < self.GROW + self.FADE]

    def draw(self, surf):
        for img, drips, x, y, age, col in self.items:
            if age < self.GROW + 0.05:  # drips only grow, so redrawing them on the copy each frame is idempotent
                e = 1 - (1 - min(1.0, age / self.GROW)) ** 3
                for dx, dy, L, wd in drips:
                    end = dy + L * e
                    tip = wd * (1 - 0.35 * e)  # a running drip thins as it goes, then beads at the end
                    pygame.draw.polygon(img, col, [(dx - wd, dy), (dx + wd, dy), (dx + tip, end), (dx - tip, end)])
                    pygame.draw.circle(img, col, (dx, end), tip * 1.35)
            k = 0.0 if age < self.GROW else (age - self.GROW) / self.FADE
            img.set_alpha(int(255 * (1 - k * k)))
            w = img.get_width()
            surf.blit(img, (round(x - w / 2), round(y - w / 2)))


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

    def runs(self):
        runs, cur = [], []
        for p in self.pts:
            if p is None:
                runs.append(cur)
                cur = []
            else:
                cur.append(p)
        runs.append(cur)
        return [r for r in runs if len(r) >= 2]

    def draw(self, add, colors, now, outer=False):
        """Smoothed ribbon on the emissive layer: blade-coloured body, white core. Bloom does the glow on the GPU;
        `outer` adds a thin coloured halo for the CPU path, which has no bloom."""
        layers = ([(colors[0], 18)] if outer else []) + [(colors[1], 12), ((255, 255, 255), 4.5)]
        for run in self.runs():
            run = catmull_rom(run, 4)
            n = len(run)
            for color, width in layers:
                left, right = [], []
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
                hw = math.dist(left[-1], right[-1]) / 2
                if hw >= 1:  # round the leading edge instead of a hard square end
                    pygame.draw.circle(add, color, run[-1][:2], hw)


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
    """Floating score numbers: Barlow numerals with a soft shadow, rising and fading."""

    def __init__(self, fonts):
        self.fonts = fonts
        self.items = []

    def add(self, text, x, y, color=WASHI, big=False):
        f = self.fonts
        font = f.bonus if big else f.pop
        self.items.append([f.text(font, text, color), f.shadow(font, text), x, y, 0.0])

    def update(self, dt):
        for p in self.items:
            p[3] -= 60 * dt
            p[4] += dt
        self.items = [p for p in self.items if p[4] < 0.9]

    def draw(self, surf):
        for img, sh, x, y, age in self.items:
            a = int(255 * min(1, age / 0.05, (0.9 - age) / 0.4))
            k = 1 + max(0, 0.12 - age) * 2.5  # a short pop in
            for im, dy in ((sh, 3), (img, 0)):
                s = pygame.transform.rotozoom(im, 0, k) if k > 1.001 else im
                s.set_alpha(a)
                surf.blit(s, s.get_rect(center=(x, y + dy)))


def stamp_scale(age):
    """Seal drop: 1.8 -> 1.0 in 0.11 s, accelerating like a hand pressing down, then a 0.92 undershoot as the
    stone bites, settling back to 1.0."""
    if age < 0.11:
        u = age / 0.11
        return 1.8 - 0.8 * u * u
    if age < 0.16:
        u = (age - 0.11) / 0.05
        return 1.0 - 0.08 * (1 - (1 - u) ** 2)
    if age < 0.28:
        u = (age - 0.16) / 0.12
        return 0.92 + 0.08 * u * u * (3 - 2 * u)
    return 1.0


class Stamp:
    """A hanko seal that slams onto the screen over its own ink bleed. The game's signature beat."""

    DUR = 1.4
    LAND = 0.11

    def __init__(self, art, glyph, caption, x, y, size=120, color=WASHI, bonus=None, hold=False):
        f = art.fonts
        self.seal = art.seal(glyph, size)
        self.blot = art.blot(size)
        self.cap = f.text(f.caption, caption, color, 2) if caption else None
        self.cap_sh = f.shadow(f.caption, caption, 2) if caption else None
        self.bonus = f.text(f.bonus, bonus, GOLD) if bonus else None
        self.bonus_sh = f.shadow(f.bonus, bonus) if bonus else None
        cw = (self.cap.get_width() if self.cap else 0) + (self.bonus.get_width() + 14 if self.bonus else 0)
        mx = max(size * 0.8, cw / 2 + 24)
        self.x = min(max(x, mx), W - mx)
        self.y = min(max(y, size * 0.75), H - size * 0.5 - 80)
        self.size = size
        self.rot = random.uniform(-6, 6)
        self.age = 0.0
        self.landed = False
        self.hold = hold  # stays on screen (results) instead of fading after DUR
        self._still = None  # the settled seal, rotated once instead of every frame

    def scale(self):
        return stamp_scale(self.age)

    def update(self, dt):
        self.age += dt
        return self.hold or self.age < self.DUR

    def draw(self, surf):
        a = self.age
        fade = 1.0 if self.hold else min(1.0, (self.DUR - a) / 0.35)
        if a >= self.LAND:  # the ink bleeds out from under the stone on impact
            u = min(1.0, (a - self.LAND) / 0.12)
            k = 0.82 + 0.18 * (1 - (1 - u) ** 3)
            b = pygame.transform.rotozoom(self.blot, self.rot * 0.5, k)
            b.set_alpha(int(153 * fade))  # 60 %
            surf.blit(b, b.get_rect(center=(self.x, self.y)))
        k = self.scale()
        if k == 1.0:
            if self._still is None:
                self._still = pygame.transform.rotozoom(self.seal, self.rot, 1.0)
            img = self._still
        else:
            img = pygame.transform.rotozoom(self.seal, self.rot, k)
        img.set_alpha(int(255 * min(1.0, a / 0.05, fade)))
        surf.blit(img, img.get_rect(center=(self.x, self.y)))
        if self.cap and a > 0.14:
            u = min(1.0, (a - 0.14) / 0.2)
            alpha = int(255 * min(u, fade))
            y = self.y + self.size * 0.5 + 34 + 8 * (1 - u) ** 2
            w = self.cap.get_width() + (self.bonus.get_width() + 14 if self.bonus else 0)
            x = self.x - w / 2
            for im, sh in ((self.cap, self.cap_sh), (self.bonus, self.bonus_sh)):
                if im is None:
                    continue
                r = im.get_rect(midleft=(x, y))
                sh.set_alpha(alpha)
                surf.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
                im.set_alpha(alpha)
                surf.blit(im, r)
                x = r.right + 14
