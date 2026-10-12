"""Ki and the three superpowers: Time Stop, Shadow Clones and Dragon Fire.

Play owns a KiMeter (only in modes with the "powers" feature) and at most one active power, and keeps thin hooks:
`use_power` (keys Q/W/E, right click), `tick_power` once a frame, `on_cut` from `Play.hit`, `power.fx` in its post-fx
and `power.draw` in its world layer. Everything a power does or draws lives here.
"""
import math
import random

import pygame

from .entities import seg_hits_circle
from .fx import Trail, catmull_rom, glow, shade
from .settings import W, H, GOLD

KI_MAX = 100
KI_PER_CUT = 4
KI_PER_COMBO = 3  # x combo size, for combos of 3 or more


class KiMeter:
    def __init__(self, value=0.0):
        self.value = value
        self.locked = False  # set while a power runs: powers never feed the meter

    @property
    def full(self):
        return self.value >= KI_MAX

    def add(self, n):
        if not self.locked:
            self.value = min(KI_MAX, self.value + n)

    def spend(self):
        self.value = 0.0


def on_screen(b):
    return b.alive and -b.r < b.x < W + b.r and -b.r < b.y < H


class Power:
    name, DURATION, world_scale, blocks_slicing = "", 1.0, 1.0, False
    blade = None  # (outer, mid, core, trail core): replaces the player's blade colours while active
    color = GOLD  # HUD accent
    title = ""

    def __init__(self, play):
        self.play, self.t, self.done = play, 0.0, False

    def left(self):
        """Share of the power's time still to run (HUD bar)."""
        return max(0.0, 1 - self.t / self.DURATION)

    def fx(self, params):
        pass

    def on_cut(self, b):
        pass


# ---------------- Time Stop ----------------

class TimeStop(Power):
    """The world holds its breath for 3 s: the cursor draws a path of light, then every fruit it crossed is cut in
    the order it was touched, 40 ms apart, as the blade retraces the path."""
    name, DURATION, world_scale, blocks_slicing = "timestop", 3.0, 0.0, True
    title, color = "TIME STOP", (214, 222, 236)
    GAP = 0.04  # s between resolution cuts
    INK = ((14, 18, 30), (92, 108, 146), (226, 232, 248))  # path glow: outer, body, core

    def __init__(self, play):
        super().__init__(play)
        self.path = [play.app.mouse]
        self.marked = []  # [body, segment, time marked], in order of first touch
        self.queue = None  # bodies to cut, filled when time resumes
        self.after = 0.0  # real s since time resumed
        self.next_cut = 0.0

    def update(self, dt):
        p = self.play
        if self.queue is None:
            self.t += dt
            m = p.app.mouse
            if m != self.path[-1]:
                self.touch((*self.path[-1], *m))
                self.path.append(m)
            if self.t >= self.DURATION:
                self.world_scale, self.blocks_slicing = 1.0, False
                self.queue = [(b, seg) for b, seg, _ in self.marked]
                self.retrace = max(0.18, self.GAP * len(self.queue))
                p.w.shake.kick(0.3)
                p.w.flash = max(p.w.flash, 0.25)
                p.app.audio.play("swoosh")
            return
        self.after += dt
        self.next_cut -= dt
        while self.queue and self.next_cut <= 0:
            b, seg = self.queue.pop(0)
            if b.alive and p.state == "play":
                p.hit(b, seg)
                ax, ay, bx, by = seg
                L = math.hypot(bx - ax, by - ay) or 1
                p.w.slashes.append([b.x, b.y, (bx - ax) / L, (by - ay) / L, b.r * 2.6, 0.0])  # a long clean stroke
                p.w.shake.kick(0.12)
            self.next_cut += self.GAP
        if not self.queue and self.after >= 0.3:
            self.done = True

    def touch(self, seg):
        for b in self.play.w.bodies:
            if b.alive and all(m[0] is not b for m in self.marked) and seg_hits_circle(*seg, b.x, b.y, b.r * 1.05):
                self.marked.append([b, seg, self.t])

    def touched(self):
        """Bodies the path crossed, in order of first touch, each with the segment that touched it."""
        return [(b, seg) for b, seg, _ in self.marked if b.alive]

    def left(self):
        return 0.0 if self.queue is not None else max(0.0, 1 - self.t / self.DURATION)

    def strength(self):
        """1 while time is held (eased in), dropping fast back to 0 as it resumes."""
        if self.queue is None:
            return min(1.0, self.t / 0.12)
        return max(0.0, 1 - self.after / 0.2)

    def fx(self, params):
        k = self.strength()
        params["saturation"] = min(params["saturation"], 1 - 0.75 * k)
        params["zoom"] = max(params["zoom"], 1 + 0.02 * k)

    def draw(self, L, add, ui):
        app, k = self.play.app, self.strength()
        if app.gpu is None and k > 0:  # no post-fx on the CPU: a cool grade stands in for the drained colour
            L.fill(tuple(int(255 - (255 - c) * k) for c in (170, 176, 192)), special_flags=pygame.BLEND_RGB_MULT)
        fade = 1.0 if self.queue is None else max(0.0, 1 - self.after / 0.3)
        if fade > 0 and len(self.path) >= 2:
            self.draw_path(add, fade)
        for b, seg, tm in self.marked:  # each fruit the path has claimed wears a thin gold ring until it is cut
            if b.alive:
                u = min(1.0, (self.t - tm) / 0.14)
                r = b.r * (1.25 + 0.5 * (1 - u) ** 2)
                pygame.draw.circle(add, shade(GOLD, 0.55 * fade), (b.x, b.y), r, 2)
                g = glow(app.art, b.r * 1.5, GOLD, 0.18 * fade)
                add.blit(g, g.get_rect(center=(b.x, b.y)), special_flags=pygame.BLEND_RGB_ADD)
        if self.queue is None:
            self.draw_countdown(ui)

    def draw_path(self, add, fade):
        """A brush stroke of light: thick where the hand moved slowly, thin on fast flicks, tapering at both ends.
        Once time resumes a bright head races along it, retracing the cut."""
        pts = catmull_rom(self.path[-300:], 2)
        n = len(pts)
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        total = cum[-1] or 1
        head = None if self.queue is None else min(1.0, self.after / self.retrace) * total
        prof = []  # (x, y, unit normal * width) once; each layer scales it
        for i, (x, y) in enumerate(pts):
            a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            seg = math.hypot(dx, dy) or 1
            c = cum[i]
            speed = max(0.4, min(1.25, 1.45 - seg / 28))  # slow hand, wet brush
            taper = min(1.0, c / 60, ((total - c) / 90) ** 0.7 + 0.15)
            grain = 0.82 + 0.12 * math.sin(c / 23) + 0.06 * math.sin(c / 6.3)  # the bristles never lay down evenly
            w = 3.2 * speed * taper * grain / seg
            prof.append((x, y, -dy * w, dx * w))
        for col, wk in zip(self.INK, (2.6, 1.0, 0.32)):
            left = [(x + nx * wk, y + ny * wk) for x, y, nx, ny in prof]
            right = [(x - nx * wk, y - ny * wk) for x, y, nx, ny in reversed(prof)]
            pygame.draw.polygon(add, shade(col, fade), left + right)
        if head is not None and head < total:
            i = next((j for j, c in enumerate(cum) if c >= head), n - 1)
            hx, hy = pts[i]
            g = glow(self.play.app.art, 26, (255, 250, 235), 0.9 * fade)
            add.blit(g, g.get_rect(center=(hx, hy)), special_flags=pygame.BLEND_RGB_ADD)
            tail = pts[max(0, i - 24):i + 1]
            if len(tail) >= 2:
                pygame.draw.lines(add, (255, 252, 240), False, tail, 3)

    def draw_countdown(self, ui):
        """A thin ring beside the cursor, unwinding as the held breath runs out."""
        ss, R = 3, 13
        d = (R + 3) * 2 * ss
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        c = d / 2
        pygame.draw.circle(s, (236, 228, 210, 60), (c, c), R * ss, ss)
        left = self.left()
        if left > 0:
            a0 = math.pi / 2
            rect = pygame.Rect(c - R * ss, c - R * ss, R * 2 * ss, R * 2 * ss)
            pygame.draw.arc(s, (*GOLD, 255), rect, a0, a0 + math.tau * left, 2 * ss)
        s = pygame.transform.smoothscale(s, (d // ss, d // ss))
        mx, my = self.play.app.mouse
        ui.blit(s, s.get_rect(center=(mx + 30, my - 30)))


# ---------------- Shadow Clones ----------------

class Clone:
    __slots__ = ("i", "x", "y", "vx", "vy", "target", "trail")

    def __init__(self, i, x, y, vx, vy):
        self.i, self.x, self.y, self.vx, self.vy = i, x, y, vx, vy
        self.target = None
        self.trail = Trail()


class ShadowClones(Power):
    """Three ghost blades leave the cursor and hunt fruit on their own for 5 s. They never touch bombs or hazards."""
    name, DURATION = "clones", 5.0
    title, color = "SHADOW CLONES", (176, 150, 232)
    N, SPEED = 3, 1600
    FADE = 0.3
    GHOST = ((48, 26, 92), (104, 70, 178), (196, 172, 250), (206, 186, 255))
    EMERGE = 0.22  # s the clones fan out of the cursor before they start hunting

    def __init__(self, play):
        super().__init__(play)
        mx, my = play.app.mouse
        self.clones = []
        for i in range(self.N):  # fanned out of the cursor, so they curve away before turning onto their targets
            a = -math.pi / 2 + (i - 1) * 2.1
            self.clones.append(Clone(i, mx, my, math.cos(a) * self.SPEED * 0.7, math.sin(a) * self.SPEED * 0.7))
        w = play.w
        w.particles.sparks(mx, my, self.GHOST[2], 26, 520, 0.45)
        for _ in range(8):
            a = random.uniform(0, math.tau)
            w.particles.add(mx, my, math.cos(a) * 140, math.sin(a) * 140, 0.45, 26, self.GHOST[1], "glow", 0.0)

    def pick(self, c):
        """Nearest fruit on screen, preferring one no other clone is already chasing."""
        mine = [b for b in self.play.w.bodies if on_screen(b) and not b.bomb and getattr(b, "hazard", "") == ""]
        if not mine:
            return None
        taken = {id(o.target) for o in self.clones if o is not c and o.target is not None}
        free = [b for b in mine if id(b) not in taken] or mine
        return min(free, key=lambda b: (b.x - c.x) ** 2 + (b.y - c.y) ** 2)

    def update(self, dt):
        self.t += dt
        hunting = self.EMERGE <= self.t < self.DURATION
        mx, my = self.play.app.mouse
        for c in self.clones:
            if hunting and (c.target is None or not on_screen(c.target)):
                c.target = self.pick(c)
            tgt = c.target if hunting else None
            if tgt is not None:
                tx, ty = tgt.x, tgt.y
            else:  # nothing to cut: drift in a loose ring around the cursor
                a = self.t * 3 + c.i * math.tau / self.N
                tx, ty = mx + math.cos(a) * 80, my + math.sin(a) * 50
            dx, dy = tx - c.x, ty - c.y
            d = math.hypot(dx, dy) or 1
            sp = self.SPEED if tgt is not None else min(self.SPEED * 0.6, d * 5)
            if self.t < self.EMERGE:  # still fanning out: keep the launch heading, slowing to a poise
                sp, dx, dy, d = self.SPEED * 0.7 * (1 - self.t / self.EMERGE) + 120, c.vx, c.vy, math.hypot(c.vx, c.vy) or 1
            # steering tightens as the target nears, so a clone curves in instead of orbiting it
            k = min(1.0, dt * max(7.0, 2.2 * self.SPEED / d))
            c.vx += (dx / d * sp - c.vx) * k
            c.vy += (dy / d * sp - c.vy) * k
            v = math.hypot(c.vx, c.vy) or 1
            if tgt is not None:
                c.vx, c.vy = c.vx / v * sp, c.vy / v * sp
            px, py = c.x, c.y
            c.x += c.vx * dt
            c.y += c.vy * dt
            if tgt is not None and seg_hits_circle(px, py, c.x, c.y, tgt.x, tgt.y, tgt.r):
                self.cut(c, tgt)
            c.trail.add(c.x, c.y, self.t)
            c.trail.update(self.t)
        if self.t >= self.DURATION + self.FADE:
            self.done = True

    def cut(self, c, b):
        v = math.hypot(c.vx, c.vy) or 1
        ux, uy = c.vx / v, c.vy / v
        r = b.r * 1.5
        self.play.hit(b, (b.x - ux * r, b.y - uy * r, b.x + ux * r, b.y + uy * r))
        self.play.w.particles.sparks(b.x, b.y, self.GHOST[2], 10, 420, 0.35)
        c.target = None

    def draw(self, L, add, ui):
        fade = min(1.0, self.t / 0.1, max(0.0, (self.DURATION + self.FADE - self.t) / self.FADE))
        if fade <= 0:
            return
        cols = tuple(shade(col, 0.8 * fade) for col in self.GHOST)  # ghosts: never as solid as the real blade
        art = self.play.app.art
        for c in self.clones:
            c.trail.draw(add, cols, self.t, outer=self.play.app.gpu is None)
            g = glow(art, 30, self.GHOST[1], 0.6 * fade)
            add.blit(g, g.get_rect(center=(c.x, c.y)), special_flags=pygame.BLEND_RGB_ADD)
            v = math.hypot(c.vx, c.vy) or 1  # the ghost blade itself: a short edge of light along its heading
            ux, uy = c.vx / v * 16, c.vy / v * 16
            pygame.draw.line(add, cols[2], (c.x - ux, c.y - uy), (c.x + ux, c.y + uy), 3)
            pygame.draw.circle(add, cols[3], (c.x + ux, c.y + uy), 2)


# ---------------- Dragon Fire ----------------

class DragonFire(Power):
    """For 6 s the blade burns: a fruit it cuts flares and bursts after 0.15 s, and the burst sets every fruit
    within 140 px alight in turn. Fire never touches bombs."""
    name, DURATION = "dragonfire", 6.0
    title, color = "DRAGON FIRE", (255, 146, 60)
    IGNITE_DELAY, RADIUS = 0.15, 140
    RING = 0.4  # s for a fire ring to spread
    blade = ((150, 26, 0), (255, 96, 14), (255, 196, 96), (255, 226, 160))
    FLAME = ((255, 120, 30), (255, 90, 20), (255, 160, 60))

    def __init__(self, play):
        super().__init__(play)
        self.pending = []  # [x, y, delay left, r]: cut fruit about to burst
        self.rings = []  # [x, y, age]
        self.jumps = []  # [x0, y0, x1, y1, age, bend]: the fire leaping to the next fruit
        self.emit = 0.0
        self.burst(*play.app.mouse, spread=False)

    def on_cut(self, b):
        if self.t < self.DURATION and not b.bomb:
            self.pending.append([b.x, b.y, self.IGNITE_DELAY, b.r])

    def update(self, dt):
        self.t += dt
        app, w = self.play.app, self.play.w
        if self.t < self.DURATION and app.speed > 250:  # the blade sheds flame and embers as it moves
            self.emit += dt * 160
            mx, my = app.mouse
            while self.emit >= 1:
                self.emit -= 1
                a = random.uniform(0, math.tau)
                sp = random.uniform(20, 120)
                w.particles.add(mx, my, math.cos(a) * sp, math.sin(a) * sp - 60, random.uniform(0.16, 0.3),
                                random.uniform(12, 22), random.choice(self.FLAME), "glow", -0.12)
                if random.random() < 0.5:
                    w.particles.add(mx, my, math.cos(a) * sp * 2, math.sin(a) * sp * 2 - 140, random.uniform(0.5, 1.0),
                                    random.uniform(1.5, 2.5), random.choice(self.FLAME), "ember", -0.25)
        for q in self.pending:
            q[2] -= dt
        ready = [q for q in self.pending if q[2] <= 0]
        self.pending = [q for q in self.pending if q[2] > 0]
        for x, y, _, r in ready:
            self.burst(x, y)
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < self.RING]
        for j in self.jumps:
            j[4] += dt
        self.jumps = [j for j in self.jumps if j[4] < 0.22]
        if self.t >= self.DURATION and not self.pending and not self.rings:
            self.done = True

    def burst(self, x, y, spread=True):
        w = self.play.w
        self.rings.append([x, y, 0.0])
        w.particles.embers(x, y, 24, 480)
        w.particles.sparks(x, y, (255, 170, 70), 16, 600, 0.4)
        for _ in range(12):  # the fireball: soft flame blobs rolling outward and up
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 260)
            w.particles.add(x, y, math.cos(a) * sp, math.sin(a) * sp - 60, random.uniform(0.3, 0.5), random.uniform(28, 50),
                            random.choice(self.FLAME), "glow", -0.15)
        if not spread:
            return
        w.shake.kick(0.18)
        for b in list(w.bodies):
            if b.alive and not b.bomb and getattr(b, "hazard", "") == "" and math.dist((x, y), (b.x, b.y)) <= self.RADIUS:
                dx, dy = b.x - x, b.y - y
                d = math.hypot(dx, dy) or 1
                self.jumps.append([x, y, b.x, b.y, 0.0, random.choice((-1, 1)) * random.uniform(0.15, 0.3)])
                r = b.r * 1.5  # cut across the line the fire travelled
                self.play.hit(b, (b.x - dy / d * r, b.y + dx / d * r, b.x + dy / d * r, b.y - dx / d * r))
                if self.play.state != "play":
                    return

    def draw(self, L, add, ui):
        art = self.play.app.art
        for x, y, left, r in self.pending:  # the cut fruit flares up before it bursts
            u = 1 - left / self.IGNITE_DELAY
            g = glow(art, r * (1.5 + 0.9 * u), (255, 120, 30), (0.5 + 0.5 * u) * random.uniform(0.85, 1.0))
            add.blit(g, g.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
        for x, y, age in self.rings:
            u = age / self.RING
            e = 1 - (1 - u) ** 3
            rad = self.RADIUS * (0.2 + 0.8 * e)
            k = 1 - u * u
            g = glow(art, rad * 0.9, (255, 110, 30), 0.45 * k)
            add.blit(g, g.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)
            for i in range(24):  # the flame front: licks of fire riding the ring, flickering
                a = i * math.tau / 24 + age * 2.5
                rr = rad * random.uniform(0.93, 1.04)
                f = glow(art, 14 + 20 * k, random.choice(self.FLAME), k * random.uniform(0.6, 1.0))
                add.blit(f, f.get_rect(center=(x + math.cos(a) * rr, y + math.sin(a) * rr)), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(add, shade((255, 222, 160), k), (x, y), rad, max(1, int(3 * k)))
        for x0, y0, x1, y1, age, bend in self.jumps:  # a curling tongue of flame, gone in a blink
            k = 1 - age / 0.22
            nx, ny = -(y1 - y0) * bend, (x1 - x0) * bend
            pts = []
            for i in range(9):
                t = i / 8
                s = 4 * t * (1 - t)
                pts.append((x0 + (x1 - x0) * t + nx * s + random.uniform(-2, 2), y0 + (y1 - y0) * t + ny * s + random.uniform(-2, 2)))
            pygame.draw.lines(add, shade((255, 90, 20), 0.8 * k), False, pts, 7)
            pygame.draw.lines(add, shade((255, 220, 150), k), False, pts, 2)


# ---------------- Play hooks ----------------

POWERS = {"timestop": TimeStop, "clones": ShadowClones, "dragonfire": DragonFire}
KEYS = {pygame.K_q: "timestop", pygame.K_w: "clones", pygame.K_e: "dragonfire"}
STAMPS = {"timestop": ("止", "Time stop"), "clones": ("影", "Shadow clones"), "dragonfire": ("炎", "Dragon fire")}


def use_power(play, name):
    """Start a power: only in play, unpaused, with a full meter and nothing already running."""
    ki = play.ki
    if ki is None or play.state != "play" or play.paused or not ki.full or play.power is not None:
        return False
    ki.spend()
    ki.locked = True
    play.power = POWERS[name](play)
    play.last_power = name
    play.app.audio.play(name)
    play.w.stamp(*STAMPS[name], W / 2, H * 0.72, 110)  # low: the action is up in the fruit's arcs
    play.w.shake.kick(0.25)
    return True


def tick_power(play, dt):
    """Run the active power for a real-time frame; end it (unlocking Ki) once it's done and its combo is tallied,
    or as soon as the run stops being played."""
    pw = play.power
    if pw is not None:
        if play.state == "play":
            pw.update(dt)
        if (pw.done and not play.combo) or play.state != "play":
            play.power = None
            play.ki.locked = False
    play.w.power_scale = play.power.world_scale if play.power else 1.0


def on_cut(play, b):
    if play.ki:
        play.ki.add(KI_PER_CUT)
    if play.power:
        play.power.on_cut(b)
