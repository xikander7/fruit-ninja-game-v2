import math
import random

import pygame

from .art import FRUITS
from .settings import H, GRAVITY


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


def blit_rot(surf, img, x, y, ang):
    im = pygame.transform.rotozoom(img, ang, 1)
    surf.blit(im, im.get_rect(center=(round(x), round(y))))


class Body:
    """A thrown fruit, special banana or bomb."""

    def __init__(self, art, kind, x, y, vx, vy, static=False):
        self.kind = kind
        self.bomb = kind == "bomb"
        self.ft = None if self.bomb else FRUITS[kind]
        self.special = "" if self.bomb else self.ft.special
        self.r = 38 if self.bomb else self.ft.r
        if self.bomb:
            self.img, self.shadow = art.bomb, art.bomb_shadow
        else:
            fa = art.fruits[kind]
            self.img, self.shadow = fa.whole, fa.shadow
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = random.uniform(0, 360)
        self.spin = random.uniform(-200, 200) if not static else random.choice((-25, 25))
        self.static = static
        self.alive = True
        self.entered = False

    def update(self, dt):
        if not self.static:
            self.vy += GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.y < H - self.r:
                self.entered = True
        self.ang += self.spin * dt

    def gone(self):
        return not self.static and self.vy > 0 and self.y > H + self.r * 2

    def draw_shadow(self, surf):
        blit_rot(surf, self.shadow, self.x + 16, self.y + 22, self.ang)

    def draw(self, surf):
        blit_rot(surf, self.img, self.x, self.y, self.ang)


class Half:
    def __init__(self, fruit_art, x, y, vx, vy, out_deg):
        self.img, self.shadow = fruit_art.half, fruit_art.half_shadow
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.ang = out_deg - fruit_art.half_local
        self.spin = random.uniform(-260, 260)

    def update(self, dt):
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ang += self.spin * dt

    def gone(self):
        return self.vy > 0 and self.y > H + 150

    def draw_shadow(self, surf):
        blit_rot(surf, self.shadow, self.x + 16, self.y + 22, self.ang)

    def draw(self, surf):
        blit_rot(surf, self.img, self.x, self.y, self.ang)
