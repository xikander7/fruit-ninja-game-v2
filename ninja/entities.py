import math
import random

import pygame

from .art import FRUITS
from .settings import H, GRAVITY

BLUR_SPEED = 900  # px/s: faster than this, a sprite leaves motion-blur ghosts
GHOSTS = ((0.5, 40), (1.0, 18))  # (fraction of a frame back, alpha): a smear, not a second copy


def seg_hits_circle(ax, ay, bx, by, cx, cy, r):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / L2))
    px, py = ax + dx * t, ay + dy * t
    return (cx - px) ** 2 + (cy - py) ** 2 <= r * r


def rotate_vec(x, y, deg):
    """Rotate an offset the same way pygame.transform.rotate turns the image (ccw on screen)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def depth_scale(age, flight):
    """Fake depth: a thrown sprite swells toward the camera at the top of its arc."""
    if flight is None:
        return 1.0
    p = min(1.0, max(0.0, age / flight))
    return 0.9 + 0.14 * math.sin(math.pi * p)


def draw_shadow(surf, shadow, x, y, ang, s):
    # the nearer the sprite (bigger s), the further and fainter its shadow on the wall
    k = min(1.0, max(0.0, (s - 0.9) / 0.14))
    off = 10 + 16 * k
    im = pygame.transform.rotate(shadow, ang)  # soft blob: no smoothing or depth scale needed, and ~5x cheaper
    im.set_alpha(int(255 * (0.9 - 0.3 * k)))
    surf.blit(im, im.get_rect(center=(round(x + off * 0.59), round(y + off * 0.81))))


def draw_sprite(surf, img, x, y, ang, s, vx, vy, dt):
    im = pygame.transform.rotozoom(img, ang, s)
    if dt > 0 and vx * vx + vy * vy > BLUR_SPEED * BLUR_SPEED:
        for k, a in GHOSTS[::-1]:  # reuse the rotated image: ghosts cost a blit, not a rotozoom
            im.set_alpha(a)
            surf.blit(im, im.get_rect(center=(round(x - vx * dt * k), round(y - vy * dt * k))))
        im.set_alpha(255)
    surf.blit(im, im.get_rect(center=(round(x), round(y))))


def flight_time(vy, static):
    if static:
        return None
    return max(0.6, 2 * abs(vy) / GRAVITY)  # time to fall back to the launch height (either way up)


class Body:
    """A thrown fruit, special banana or bomb."""
    rain = False  # Fever's rain: dropping one never costs a strike or a life

    def __init__(self, art, kind, x, y, vx, vy, static=False):
        self.kind = kind
        self.bomb = kind == "bomb"
        self.hazard = "ice" if kind == "icebomb" else ""  # an ice bomb: no fruit, not a bomb either
        self.ft = None if self.bomb or self.hazard else FRUITS[kind]
        self.special = "" if self.ft is None else self.ft.special
        self.r = 38 if self.ft is None else self.ft.r
        self.points = 0 if self.ft is None else self.ft.points  # what a cut scores (the golden fruit's last: more)
        self.hp, self.hit_t = (5 if kind == "golden" else 1), -1.0  # hits it takes; when it was last hit (world time)
        # a drop costs a strike or a life only for ordinary fruit: never bombs, power-ups or the hazard specials
        self.costly = self.ft is not None and not self.special and kind not in ("golden", "chaos")
        if self.bomb:
            self.img, self.shadow = art.bomb, art.bomb_shadow
        elif self.hazard:
            self.img, self.shadow = art.icebomb, art.icebomb_shadow
        else:
            fa = art.fruits[kind]
            self.img, self.shadow = fa.whole, fa.shadow
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = random.uniform(0, 360)
        self.spin = random.uniform(-200, 200) if not static else random.choice((-25, 25))
        self.static = static
        self.alive = True
        self.entered = False
        self.age, self.flight, self.dt = 0.0, flight_time(vy, static), 0.0

    def update(self, dt, g=GRAVITY):
        if not self.static:
            self.vy += g * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.r < self.y < H - self.r:  # launched from the bottom, or from the top while gravity is flipped
                self.entered = True
        self.ang += self.spin * dt
        self.age += dt
        self.dt = dt

    def scale(self):
        return depth_scale(self.age, self.flight)

    def gone(self):
        # moving away past either edge: gravity can be flipped, so a fruit can also leave over the top
        return not self.static and (self.vy > 0 and self.y > H + self.r * 2 or self.vy < 0 and self.y < -self.r * 2)

    def draw_shadow(self, surf):
        draw_shadow(surf, self.shadow, self.x, self.y, self.ang, self.scale())

    def draw(self, surf):
        vx, vy = (0, 0) if self.static else (self.vx, self.vy)
        draw_sprite(surf, self.img, self.x, self.y, self.ang, self.scale(), vx, vy, self.dt)


class Half:
    def __init__(self, fruit_art, x, y, vx, vy, out_deg, parent=None):
        self.img, self.shadow = fruit_art.half, fruit_art.half_shadow
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = out_deg - fruit_art.half_local
        self.spin = random.uniform(-260, 260)
        # halves carry on along the whole fruit's depth arc, so the cut doesn't pop in size
        self.age, self.flight = (parent.age, parent.flight) if parent else (0.0, None)
        self.dt = 0.0

    def update(self, dt, g=GRAVITY):
        self.vy += g * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ang += self.spin * dt
        self.age += dt
        self.dt = dt

    def gone(self):
        return self.vy > 0 and self.y > H + 150 or self.vy < 0 and self.y < -150

    def scale(self):
        return depth_scale(self.age, self.flight)

    def draw_shadow(self, surf):
        draw_shadow(surf, self.shadow, self.x, self.y, self.ang, self.scale())

    def draw(self, surf):
        draw_sprite(surf, self.img, self.x, self.y, self.ang, self.scale(), self.vx, self.vy, self.dt)
