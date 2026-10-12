"""Heads-up display: the Play HUD and the small UI drawing helpers it shares with the menus."""
import math

import pygame

from .art import FRUITS
from .settings import W, WASHI, GOLD, HANKO, MUTED


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


def draw_play_hud(play, ui):
    """`ui` is the UI layer: above the post-processing, so the camera never moves, fringes or dims it."""
    f = play.app.art.fonts
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
    for val, total, name, col in ((play.freeze, 6.0, "FREEZE", FRUITS["freeze"].juice),
                                  (play.frenzy, 4.5, "FRENZY", FRUITS["frenzy"].juice),
                                  (play.double, 8.0, "DOUBLE ×2", FRUITS["double"].juice)):
        if val > 0:
            label(ui, f, f.mono12, name, col, (W - 42, y), "midright", tracking=3)
            track = pygame.Surface((140, 2), pygame.SRCALPHA)
            track.fill((*WASHI, 40))
            ui.blit(track, (W - 42 - 140, y + 14))
            fill = int(140 * val / total)
            if fill > 0:
                ui.fill(col, (W - 42 - fill, y + 14, fill, 2))
            y += 38
