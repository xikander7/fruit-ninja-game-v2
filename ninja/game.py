import json
import math
import os
import random

import pygame

from .art import Art, FRUITS, REGULAR, WEIGHTS, SPECIALS
from .audio import Audio
from .entities import Body, Half, seg_hits_circle, rotate_vec
from .fx import Particles, Stains, Trail, Shake, Popups, Stamp, ray_burst, glow, shade
from .settings import W, H, FPS, GRAVITY, SAVE_PATH, WASHI, GOLD, HANKO, LACQUER, BLADES, MODES

SLICE_SPEED = 300  # px/s — just moving the cursor slices; a slow drift doesn't
MAX_JUMP = 350  # px in one motion event


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


def text(surf, font, s, color, pos, anchor="center", shadow=3, alpha=255):
    img = font.render(s, True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(s, True, (0, 0, 0))
        sh.set_alpha(min(alpha, 170))
        surf.blit(sh, r.move(shadow, shadow))
    img.set_alpha(alpha)
    surf.blit(img, r)
    return r


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

    def stamp(self, glyph, caption, x, y, size=120, color=GOLD):
        self.stamps.append(Stamp(self.art, glyph, caption, x, y, size, color))

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
        for s in self.stamps:
            s.draw(screen)
        self.popups.draw(screen)
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

    def __init__(self, world, kind, x, y, glyph, title, sub="", sub2=""):
        self.world, self.kind = world, kind
        self.x, self.y = x, y
        self.glyph, self.title, self.sub, self.sub2 = glyph, title, sub, sub2
        self.body = world.throw(kind, x, y, 0, 0, static=True)
        self.t = random.uniform(0, 6)
        self.cut_at = None

    def update(self, dt, segments):
        self.t += dt
        if self.body.alive:
            self.body.y = self.y + math.sin(self.t * 2.2) * 7
            for seg in segments:
                if seg_hits_circle(*seg, self.body.x, self.body.y, self.body.r * 1.25):
                    self.world.cut(self.body, *seg)
                    self.world.stamp(self.glyph, self.title, self.x, self.y - 10, 110)
                    self.cut_at = self.t
                    return True
        return False

    def draw(self, surf):
        f = self.world.art.fonts
        r = self.body.r + 30
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = (self.x, self.y)
        spin = self.t * (0.6 if self.body.alive else 3)
        for k in range(14):
            a = spin + k * math.tau / 14
            pygame.draw.arc(surf, (205, 185, 150), rect, a, a + 0.24, 3)
        seal = self.world.art.seal(self.glyph, 44)
        surf.blit(seal, seal.get_rect(center=(self.x - r - 10, self.y - r + 6)))
        text(surf, f.mid, self.title, WASHI, (self.x, self.y + r + 30))
        if self.sub:
            text(surf, f.util, self.sub, (215, 200, 170), (self.x, self.y + r + 62), shadow=2)
        if self.sub2:
            text(surf, f.small, self.sub2, GOLD, (self.x, self.y + r + 90), shadow=2)


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
    def __init__(self, app):
        self.app = app
        self.w = World(app)
        best = app.save["best"]
        self.buttons = []
        for (mode, kind), x in zip((("classic", "watermelon"), ("arcade", "dragonfruit"), ("zen", "peach")), (W * 0.24, W * 0.5, W * 0.76)):
            m = MODES[mode]
            b = SliceButton(self.w, kind, x, H * 0.52, m["glyph"], m["title"], m["hint"], f"BEST {best[mode]}")
            b.mode = mode
            self.buttons.append(b)
        self.chosen = None
        self.t = 0.0
        self.arrow_rects = []

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
                self.w.cut(b.body, b.x - 80, b.y - 60, b.x + 80, b.y + 60)
                self.w.stamp(b.glyph, b.title, b.x, b.y - 10, 110)
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
        self.w.update(dt, dt)
        for b in self.buttons:
            if b.update(dt, self.app.segments) and not self.chosen:
                self.chosen, self.chosen_t = b.mode, 0.0
        if self.chosen:
            self.chosen_t += dt
            if self.chosen_t > 0.6:
                mode = self.chosen
                self.chosen = None
                self.app.go(lambda: Play(self.app, mode))

    def fx_params(self):
        return self.w.fx_params()

    def draw(self, screen):
        f = self.app.art.fonts
        self.w.draw(screen)
        for b in self.buttons:
            b.draw(screen)
        # title: the one place the type gets loud
        drop = max(0.0, 1 - self.t / 0.5) ** 3 * -120
        r = text(screen, f.huge, "FRUIT NINJA", WASHI, (W / 2, 120 + drop), shadow=6)
        pygame.draw.line(screen, GOLD, (r.left + 8, r.bottom + 4), (r.right - 8, r.bottom + 4), 2)
        text(screen, f.small, "N I G H T   D O J O", GOLD, (W / 2, r.bottom + 26), shadow=2)
        # blade picker
        name = self.app.save["blade"]
        col = BLADES[name][1]
        y = H - 78
        lbl = text(screen, f.small, f"BLADE  ·  {name.upper()}", col, (W / 2, y), shadow=2)
        self.arrow_rects = []
        for step, cx in ((-1, lbl.left - 34), (1, lbl.right + 34)):
            rr = pygame.Rect(0, 0, 44, 44)
            rr.center = (cx, y)
            self.arrow_rects.append((step, rr))
            pts = [(cx - 8 * step, y - 11), (cx + 9 * step, y), (cx - 8 * step, y + 11)]
            pygame.draw.polygon(screen, col, pts)
        locked = [(n, b[3]) for n, b in BLADES.items() if n not in self.unlocked()]
        hint = f"next blade: {locked[0][0]} at best {locked[0][1]}" if locked else "all blades unlocked"
        text(screen, f.util, hint, (190, 175, 150), (W / 2, y + 28), shadow=2)
        text(screen, f.util, "move the mouse fast to slice  ·  1/2/3 quick start  ·  M mute  ·  F11 fullscreen  ·  Esc quit",
             (170, 155, 130), (W / 2, H - 14), shadow=0)
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
        self.score_pop = 0.0
        self.last_tick = None
        m = MODES[mode]
        self.w.stamp(m["glyph"], "READY", W / 2, H / 2 - 20, 150)
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
        self.score_pop = 0.18
        if self.mode == "classic":
            while self.score >= self.next_life:
                self.next_life += 100
                if self.strikes > 0:
                    self.strikes -= 1
                    self.w.popups.add("+1 LIFE", W - 150, 110, GOLD, True)
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
            w.popups.add("CRITICAL +10", b.x, b.y - 50, GOLD, True)
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
            name, glyph, cap, dur = {"freeze": ("freeze", "凍", "FREEZE", 6.0), "frenzy": ("frenzy", "嵐", "FRENZY", 4.5),
                                     "double": ("double", "倍", "DOUBLE SCORE", 8.0)}[b.special]
            setattr(self, name, dur)
            w.stamp(glyph, cap, b.x, b.y, 120, b.ft.juice)
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
            self.w.stamp("連", f"{self.combo} FRUIT COMBO  +{bonus}", *self.combo_pos, 100 + min(60, self.combo * 6))
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
        return self.w.fx_params()

    def update(self, dt):
        if self.paused:
            self.app.audio.fuse(False)
            return
        w = self.w
        # game clock: only freeze slows the timer, spawning and difficulty ramp; slow-mo only slows the world
        wdt = dt * (0.4 if self.freeze > 0 else 1.0)
        w.update(wdt * w.time_scale(), dt)
        self.score_pop = max(0.0, self.score_pop - dt)
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
                    w.stamp("時", "TIME'S UP", W / 2, H / 2 - 20, 150, WASHI)
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
        snap = self.app.frame.copy()
        self.app.go(lambda: GameOver(self.app, self, snap))

    def draw_world_extra(self, L, add):
        for x, age in self.misses:
            k = min(1.0, age / 0.12)
            s = 22 * (1.6 - 0.6 * k)
            y = H - 46
            for a, b in (((-1, -1), (1, 1)), ((1, -1), (-1, 1))):
                pygame.draw.line(L, HANKO, (x + a[0] * s, y + a[1] * s), (x + b[0] * s, y + b[1] * s), 8)

    def draw(self, screen):
        w, f = self.w, self.app.art.fonts
        w.draw(screen, self.draw_world_extra)
        if self.freeze > 0:
            screen.fill((185, 215, 255), special_flags=pygame.BLEND_RGB_MULT)
            self.app.art.frost.set_alpha(int(255 * min(1, self.freeze / 0.6)))
            screen.blit(self.app.art.frost, (0, 0))
        if self.frenzy > 0:
            k = int(40 + 25 * math.sin(w.shake.t * 10))
            pygame.draw.rect(screen, (k, k // 3, 0), screen.get_rect(), 26)
        # HUD — score
        icon = pygame.transform.smoothscale(self.app.art.fruits["watermelon"].face, (52, 52))
        screen.blit(icon, (26, 22))
        k = 1 + self.score_pop * 1.4
        img = f.big.render(str(self.score), True, GOLD)
        sh = f.big.render(str(self.score), True, (0, 0, 0))
        if k > 1.001:
            img, sh = (pygame.transform.rotozoom(i, 0, k) for i in (img, sh))
        r = img.get_rect(midleft=(90, 50))
        sh.set_alpha(170)
        screen.blit(sh, r.move(3, 3))
        screen.blit(img, r)
        best = max(self.best_prev, self.score)
        text(screen, f.util, f"BEST {best}", (215, 200, 170), (92, 88), "midleft", 2)
        if self.double > 0:
            text(screen, f.mid, "×2", GOLD, (r.right + 30, 52), shadow=3)
        # HUD — strikes or timer
        if self.mode == "classic":
            for i in range(3):
                x = W - 60 - (2 - i) * 54
                s = 15 + i * 2 + self.strike_pop[i] * 30
                hit = i < self.strikes
                col = HANKO if hit else (120, 105, 85)
                wd = 9 if hit else 4
                for a, b in (((-1, -1), (1, 1)), ((1, -1), (-1, 1))):
                    pygame.draw.line(screen, col, (x + a[0] * s, 48 + a[1] * s), (x + b[0] * s, 48 + b[1] * s), wd)
        else:
            t = max(0.0, self.time)
            col = HANKO if t <= 5 else GOLD if t <= 10 else WASHI
            img = f.big.render(f"{int(t) // 60}:{int(t) % 60:02d}", True, col)
            if t <= 5 and self.state == "play":
                img = pygame.transform.rotozoom(img, 0, 1 + 0.18 * (math.ceil(t) - t))
            screen.blit(img, img.get_rect(topright=(W - 30, 14)))
        y = 104
        for val, total, name, col in ((self.freeze, 6.0, "FREEZE", FRUITS["freeze"].juice), (self.frenzy, 4.5, "FRENZY", FRUITS["frenzy"].juice),
                                      (self.double, 8.0, "DOUBLE", FRUITS["double"].juice)):
            if val > 0:
                text(screen, f.util, name, col, (W - 30, y), "topright", 2)
                pygame.draw.rect(screen, (40, 30, 25), (W - 190, y + 24, 160, 6))
                pygame.draw.rect(screen, col, (W - 190, y + 24, 160 * val / total, 6))
                y += 42
        w.draw_overlay(screen)
        if self.paused:
            screen.fill((95, 90, 100), special_flags=pygame.BLEND_RGB_MULT)
            seal = self.app.art.seal("休", 130)
            screen.blit(seal, seal.get_rect(center=(W / 2, H / 2 - 90)))
            text(screen, f.big, "PAUSED", WASHI, (W / 2, H / 2 + 40), shadow=4)
            text(screen, f.small, "click or Esc to resume   ·   Q to quit to menu", (215, 200, 170), (W / 2, H / 2 + 95), shadow=2)


# ---------------- game over ----------------

class GameOver(Scene):
    def __init__(self, app, play, snap):
        self.app, self.play = app, play
        bg = snap.copy()
        bg.fill((80, 72, 70), special_flags=pygame.BLEND_RGB_MULT)
        self.w = World(app, bg)
        self.t = 0.0
        self.new_best = play.score > play.best_prev and play.score > 0
        self.retry = SliceButton(self.w, "watermelon", W * 0.32, H * 0.77, "再", "RETRY")
        self.menu = SliceButton(self.w, "apple", W * 0.68, H * 0.77, "戻", "MENU")
        self.choice = None
        self.stamped = 0
        self.shown = 0.0

    def handle(self, e):
        if e.type == pygame.KEYDOWN and not self.choice:
            if e.key in (pygame.K_RETURN, pygame.K_r, pygame.K_SPACE):
                self.choose("retry")
            elif e.key == pygame.K_ESCAPE:
                self.choose("menu")

    def choose(self, c):
        self.choice, self.choice_t = c, 0.0

    def update(self, dt):
        self.t += dt
        self.w.update(dt, dt)
        self.shown = min(float(self.play.score), self.shown + max(1, self.play.score) * dt * 1.6)
        if self.stamped == 0 and self.t > 0.25:
            self.stamped = 1
            over = "TIME'S UP" if self.play.time is not None else "GAME OVER"
            self.w.stamp("終", over, W / 2, 96, 96, WASHI)
        if self.stamped == 1 and self.new_best and self.t > 1.2:
            self.stamped = 2
            self.w.stamp("極", "NEW BEST", W * 0.82, H * 0.36, 120)
            self.w.particles.sparks(W * 0.82, H * 0.36, GOLD, 60, 700)
            self.app.audio.play("power")
        if self.t > 0.6 and not self.choice:
            if self.retry.update(dt, self.app.segments):
                self.choose("retry")
            elif self.menu.update(dt, self.app.segments):
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
        text(screen, f.huge, str(int(self.shown)), GOLD, (W / 2, H * 0.42), shadow=6)
        p = self.play
        best = self.app.save["best"][p.mode]
        text(screen, f.small, f"{MODES[p.mode]['title']}  ·  BEST {best}", WASHI, (W / 2, H * 0.42 + 72), shadow=2)
        stats = f"sliced {p.stats['sliced']}    ·    best combo {p.stats['best_combo']}    ·    bombs hit {p.stats['bombs']}"
        text(screen, f.util, stats, (215, 200, 170), (W / 2, H * 0.42 + 104), shadow=2)
        if self.t > 0.6:
            self.retry.draw(screen)
            self.menu.draw(screen)
        text(screen, f.util, "slice a fruit  ·  Enter retry  ·  Esc menu", (170, 155, 130), (W / 2, H - 14), shadow=0)
        self.w.draw_overlay(screen)


# ---------------- transition: the screen is cut in two ----------------

class Wipe:
    DUR = 0.5

    def __init__(self, snap):
        xt, xb = W * 0.62, W * 0.38
        self.pieces = []
        for poly in ([(0, 0), (xt, 0), (xb, H), (0, H)], [(xt, 0), (W, 0), (W, H), (xb, H)]):
            s = snap.convert_alpha()
            m = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.polygon(m, (255, 255, 255, 255), poly)
            s.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.pieces.append(s)
        L = math.hypot(xb - xt, H)
        self.n = (H / L, -(xb - xt) / L)  # normal pointing right
        self.line = ((xt, 0), (xb, H))
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.DUR

    def draw(self, screen):
        k = min(1.0, self.t / self.DUR)
        e = 1 - (1 - k) ** 3
        d = e * W * 0.8
        nx, ny = self.n
        screen.blit(self.pieces[0], (-nx * d, -ny * d - e * 40))
        screen.blit(self.pieces[1], (nx * d, ny * d + e * 40))
        if k < 0.3:
            c = int(255 * (1 - k / 0.3))
            pygame.draw.line(screen, (c, c, c), *self.line, 5)


# ---------------- app ----------------

class App:
    def __init__(self):
        pygame.init()
        self.fullscreen = False
        self.open_window()
        pygame.display.set_caption("Fruit Ninja · Night Dojo")
        self.add = pygame.Surface((W, H))  # emissive layer: glows only, black = none
        self.frame.fill(LACQUER)
        f = pygame.font.SysFont("bahnschrift,segoeui,arial", 28, bold=True)
        img = f.render("sharpening the blade…", True, WASHI)
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
        from .gpu import letterbox
        x, y, w, h = letterbox(0, 0, *pygame.display.get_window_size())
        return ((pos[0] - x) * W / w, (pos[1] - y) * H / h)

    def present(self, params):
        if self.gpu:
            self.gpu.render(self.frame, self.add, params, (0, 0, *pygame.display.get_window_size()))
        pygame.display.flip()

    def go(self, make_scene):
        snap = self.frame.copy()
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
        self.scene.draw(self.frame)
        if self.wipe and not self.wipe.update(dt):
            self.wipe = None
        if self.wipe:
            self.wipe.draw(self.frame)
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
