"""Heads-up display: the Play HUD and the small UI drawing helpers it shares with the menus."""
import math

import pygame

from .art import FRUITS
from .boss import HP as BOSS_HP, CRACK_AT, TALLY_HOLD, TALLY_FADE
from .fx import glow
from .fever import GRADE as FEVER_GRADE
from .hazards import FREEZE_TIME, FLIP_TIME, ICE, VIOLET, draw_grades as hazard_grades
from .powers import KI_MAX
from .settings import W, H, WASHI, GOLD, HANKO, MUTED


def lerp_rgb(a, b, t):
    """Blend colour a into colour b: t=0 gives a, t=1 gives b, 0.5 is halfway. ("lerp" = linear interpolation.)"""
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


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


# Caches for the small images below. Drawing them is slow, so each is built once per size/colour and then reused every frame.
_CHEVRONS = {}


def chevron(step, color):
    """A thin < or > (step -1 / 1), anti-aliased by drawing 4x and smoothscaling (aalines only antialias over an
    opaque surface, and the UI layer is transparent)."""
    key = (step, color)
    if key not in _CHEVRONS:
        # Draw at 4x size, then shrink: the shrinking smooths the jagged edges (supersampling).
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


def thin_bar(ui, x, y, w, frac, color, h=2, right=False):
    """A hairline track with a solid fill (power timers, the Ki meter)."""
    track = pygame.Surface((w, h), pygame.SRCALPHA)
    track.fill((*WASHI, 40))
    ui.blit(track, (x, y))
    fill = int(w * max(0.0, min(1.0, frac)))
    if fill > 0:
        ui.fill(color, (x + w - fill if right else x, y, fill, h))


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
        # Each stroke is a polygon built from points along a gently curved line, blunt at the start and tapering to a point.
        # (ux, uy) points along the stroke; (nx, ny) points sideways, used to push the left and right edges apart.
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


def draw_play_hud(play, ui):
    """`ui` is the UI layer: above the post-processing, so the camera never moves, fringes or dims it."""
    f = play.app.art.fonts
    # Layout: score on the left, strikes or time on the right, power timers underneath. `y` tracks where the next chip goes.
    # score: left, gold, the number rolls toward the real value
    label(ui, f, f.mono12, "SCORE", MUTED, (42, 34), "midleft", tracking=4)
    sr = label(ui, f, f.score, str(round(play.shown)), GOLD, (38, 44), "topleft")
    best = max(play.best_prev, play.score)
    label(ui, f, f.mono13, f"Best {best}", MUTED, (42, sr.bottom + 6), "midleft")
    if play.mode in ("classic", "path"):  # strikes (path: lives lost): three brush marks, empty until missed
        for i in range(3):
            cx = W - 66 - (2 - i) * 52
            if i < play.strikes:
                img = brush_x(40, HANKO)
                p = play.strike_pop[i]
                if p > 0:  # lands big and settles, like the brush hitting paper
                    img = pygame.transform.smoothscale_by(img, 1 + p * 1.6)
                img.set_alpha(255)
            else:
                img = brush_x(40, WASHI, outline=True)
                img.set_alpha(64)  # 25 %
            ui.blit(img, img.get_rect(center=(cx, 62)))
        y = 112
    else:
        label(ui, f, f.mono12, "TIME", MUTED, (W - 42, 34), "midright", tracking=4)
        t = max(0.0, play.time)
        col = HANKO if t <= 5 else GOLD if t <= 10 else WASHI
        s = f"{int(t) // 60}:{int(t) % 60:02d}" if t > 0 or play.state != "play" else "0:00"
        img = f.text(f.timer, s, col)
        sh = f.shadow(f.timer, s)
        r = img.get_rect(topright=(W - 38, 44))
        if t <= 5 and play.state == "play":  # each second lands with a pulse
            p = (math.ceil(t) - t) ** 3 if t > 0 else 0
            k = 1 + 0.14 * p
            img = pygame.transform.smoothscale_by(img, k)
            sh = pygame.transform.smoothscale_by(sh, k)
            r = img.get_rect(midright=r.midright)
        sh.set_alpha(230)
        ui.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
        img.set_alpha(255)
        ui.blit(img, r)
        y = r.bottom + 18
    # power-up chips: what's active and how long it has left
    # Each tuple is (seconds left, total seconds, label, colour); the bar under the label shows left / total.
    for val, total, name, col in ((play.freeze, 6.0, "FREEZE", FRUITS["freeze"].juice),
                                  (play.frenzy, 4.5, "FRENZY", FRUITS["frenzy"].juice),
                                  (play.double, 8.0, "DOUBLE ×2", FRUITS["double"].juice),
                                  (play.blade_frozen, FREEZE_TIME, "BLADE FROZEN", ICE),
                                  (play.hz.flip_t, FLIP_TIME, "GRAVITY FLIPPED", VIOLET)):
        if val > 0:
            label(ui, f, f.mono12, name, col, (W - 42, y), "midright", tracking=3)
            thin_bar(ui, W - 42 - 140, y + 14, 140, val / total, col, right=True)
            y += 38
    draw_mult(play, ui, sr)
    pw = play.power
    if pw is not None:  # the running superpower and its time, under the score
        y = sr.bottom + 40
        label(ui, f, f.mono12, pw.title, pw.color, (42, y), "midleft", tracking=3)
        thin_bar(ui, 42, y + 14, 140, pw.left(), pw.color)
    draw_ki(play, ui)
    draw_boss_bar(play, ui)


# Width in pixels of the Ki bar. Ki is the energy meter that fills as you slice and powers up special moves.
KI_W = 180


def draw_ki(play, ui):
    """Bottom-left: a quiet hairline that fills with each cut. Full, it is the one thing on screen that glows, and
    the keys for the three powers appear beside it."""
    ki = play.ki
    if ki is None:
        return
    f, app = play.app.art.fonts, play.app
    x, y = 42, H - 40
    full = ki.full and play.power is None
    # A slow 0-to-1 wobble over time that makes the full Ki bar breathe.
    pulse = 0.5 + 0.5 * math.sin(play.w.t * 4.5)
    label(ui, f, f.mono12, "POWER", GOLD if full else MUTED, (x, y - 14), "midleft", tracking=2)
    if full:
        label(ui, f, f.mono12, "Q  W  E", GOLD, (x + KI_W, y - 14), "midright", tracking=2, alpha=int(150 + 105 * pulse))
        g = pygame.transform.smoothscale(glow(app.art, 48, GOLD, 0.5 + 0.35 * pulse), (KI_W + 60, 34))
        g.fill(GOLD, (30, 16, KI_W, 3), special_flags=pygame.BLEND_RGB_ADD)  # the bar itself, lit for the bloom
        pos = g.get_rect(topleft=(x - 30, y - 15))
        app.add.blit(g, pos, special_flags=pygame.BLEND_RGB_ADD)
        if app.gpu is None:  # the CPU frame already holds the glow layer: add it straight on
            app.frame.blit(g, pos, special_flags=pygame.BLEND_RGB_ADD)
    thin_bar(ui, x, y, KI_W, ki.value / KI_MAX, GOLD, h=3)


def draw_mult(play, ui, sr):
    """The multiplier beside the score: x2..x5 in gold, landing with a small pop each step. During Fever a red
    seal reads FEVER above it, and a hairline under both runs down with the time left."""
    fv = play.fever
    if fv is None or fv.mult < 2:
        return
    f = play.app.art.fonts
    x = sr.right + 16
    s = f"×{fv.mult}"
    img, sh = f.text(f.bonus, s, GOLD), f.shadow(f.bonus, s)
    if fv.pop > 0:
        k = 1 + 0.35 * fv.pop ** 2
        img, sh = pygame.transform.smoothscale_by(img, k), pygame.transform.smoothscale_by(sh, k)
    r = img.get_rect(bottomleft=(x, sr.bottom - 6))
    sh.set_alpha(230)
    ui.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
    ui.blit(img, r)
    if not fv.active:
        return
    seal = fever_seal(f)
    sr2 = seal.get_rect(bottomleft=(x + 2, r.top + 4))
    seal.set_alpha(int(255 * min(1.0, fv.grade() * 1.5)))
    ui.blit(seal, sr2)
    thin_bar(ui, x + 2, r.bottom + 4, max(sr2.width, r.width), fv.left(), GOLD)


_SEAL = []


def fever_seal(f):
    """FEVER in washi on a hanko-red seal: square-cornered, a touch uneven, like ink pressed onto paper."""
    if not _SEAL:
        t = f.text(f.mono12, "FEVER", WASHI, 3)
        s = pygame.Surface((t.get_width() + 14, t.get_height() + 6), pygame.SRCALPHA)
        pygame.draw.rect(s, (*HANKO, 235), s.get_rect(), border_radius=2)
        s.blit(t, t.get_rect(center=(s.get_width() / 2 + 1, s.get_height() / 2)))
        _SEAL.append(s)
    return _SEAL[0]


def draw_grades(play, screen):
    """Power-up and Fever grades over the world, under the HUD."""
    app, w = play.app, play.w
    if play.freeze > 0:  # a cold grade that fades in and out with the effect
        k = min(1.0, play.freeze / 0.6)
        screen.fill(lerp_rgb((255, 255, 255), (190, 214, 240), k), special_flags=pygame.BLEND_RGB_MULT)
        app.art.frost.set_alpha(int(255 * k))
        screen.blit(app.art.frost, (0, 0))
    if play.frenzy > 0:  # embers at the edges, breathing slowly
        k = min(1.0, play.frenzy / 0.5)
        ember = app.art.ember
        gain = 1.0 if app.gpu is None else 0.4  # bloom and additive composite amplify it on the GPU
        ember.set_alpha(int(255 * gain * k * (0.75 + 0.25 * math.sin(w.t * 5))))
        # it is light, not paint: on the GPU it goes to the glow layer so the bloom carries it
        (screen if app.gpu is None else app.add).blit(ember, (0, 0))
    hazard_grades(play, screen)
    k = play.fever.grade() if play.fever else 0.0
    if k > 0:  # Fever's warm gold (the GPU also lifts saturation in its post-fx)
        screen.fill(lerp_rgb((255, 255, 255), FEVER_GRADE, k), special_flags=pygame.BLEND_RGB_MULT)


# Width in pixels of the boss health bar.
BOSS_W = 360


def draw_boss_bar(play, ui):
    """Top centre while a boss is up: its name in Cormorant SC over a thin hanko-red bar, with a pale trail where the
    last hits took the HP and hairline notches where the rind cracks. Fades in as it rises and out as it goes."""
    b = play.boss.active if play.boss else None
    if b is None:
        return
    f = play.app.art.fonts
    draw_boss_tally(b, f, ui)
    a = min(1.0, b.t / 0.4) if b.phase == "rise" else max(0.0, 1 - b.t / 0.5) if b.phase == "escape" else         max(0.0, 1 - b.dead_t / 0.6) if b.phase == "dead" else 1.0
    if a <= 0:
        return
    x, y = W // 2 - BOSS_W // 2, 50
    label(ui, f, f.boss, b.title, WASHI, (W / 2, y - 16), tracking=2, alpha=int(255 * a))
    bar = pygame.Surface((BOSS_W, 4), pygame.SRCALPHA)
    bar.fill((*WASHI, 40))
    bar.fill((*WASHI, 150), (0, 0, int(BOSS_W * b.shown / BOSS_HP), 4))
    bar.fill((*HANKO, 255), (0, 0, int(BOSS_W * b.hp / BOSS_HP), 4))
    for h in CRACK_AT:
        bar.fill((0, 0, 0, 160), (int(BOSS_W * h / BOSS_HP), 0, 1, 4))
    bar.set_alpha(int(255 * a))
    ui.blit(bar, (x, y))


def draw_boss_tally(b, f, ui):
    """One "+N" off the boss's upper right that counts up the current run of hits: it pops on each hit and fades
    TALLY_FADE s after holding TALLY_HOLD s past the last one (a popup per hit piles into an unreadable heap)."""
    if not b.tally:
        return
    a = min(1.0, (TALLY_HOLD + TALLY_FADE - b.tally_t) / TALLY_FADE)
    if a <= 0:
        return
    s = f"+{b.tally}"
    img, sh = f.text(f.bonus, s, GOLD), f.shadow(f.bonus, s)
    pop = max(0.0, 1 - b.tally_t / 0.15)
    if pop > 0:  # each hit lands with a small swell
        k = 1 + 0.3 * pop * pop
        img, sh = pygame.transform.smoothscale_by(img, k), pygame.transform.smoothscale_by(sh, k)
    x = min(max(b.x + b.r * 0.85, 60), W - 60)
    y = min(max(b.y - b.r * 0.95, 110), H - 60)
    r = img.get_rect(midleft=(x, y))
    sh.set_alpha(int(230 * a))
    img.set_alpha(int(255 * a))
    ui.blit(sh, sh.get_rect(center=(r.centerx, r.centery + 3)))
    ui.blit(img, r)
