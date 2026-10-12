"""Turn the raw generated cutouts (assets/raw, git-ignored) into game-size sprites in assets/sprites.

Run from the repo root:  python tools/build_sprites.py
Idempotent: always rebuilds every file from the manifest.
"""
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from ninja.art import FRUITS  # noqa: E402
from ninja.settings import W, H  # noqa: E402

RAW = os.path.join(ROOT, "assets", "raw")
OUT = os.path.join(ROOT, "assets", "sprites")
FILL = 2.35  # longer side of a whole sprite = FILL * r
BOMB_R = 38
SPLASH_SIZE = 300  # longer side of a splash sprite; the game scales it to the fruit
SPLASH_CROP = {"drops1": 0.72}  # keep the top fraction: drops1's bottom edge is a cut-off pool
# luma -> alpha: the black studio background keys out, the milk body is fully opaque
SPLASH_ALPHA = bytes(max(0, min(255, round((v - 12) * 1.6))) for v in range(256))


def load_trimmed(path):
    img = pygame.image.load(path).convert_alpha()
    # trim to pixels with alpha > 8 (threshold 8 -> mask uses alpha >= 9)
    rect = pygame.mask.from_surface(img, 8).get_bounding_rects()
    box = rect[0].unionall(rect[1:]) if rect else img.get_rect()
    return img.subsurface(box).copy()


def scale_by(img, k):
    w, h = img.get_size()
    return pygame.transform.smoothscale(img, (max(1, round(w * k)), max(1, round(h * k))))


def gold_grade(img):
    # the generated "double" came out as a plain banana: push it to gold (alpha preserved by RGB blends)
    img.fill((255, 200, 90), special_flags=pygame.BLEND_RGB_MULT)
    img.fill((40, 28, 0), special_flags=pygame.BLEND_RGB_ADD)
    return img


def key_splash(img):
    """White-on-black photo -> greyscale sprite keyed by brightness: RGB = luma (tinted in game), alpha from luma."""
    w, h = img.get_size()
    rgb = pygame.image.tobytes(img, "RGB")
    # Rec. 601 luma, rounded (pygame's grayscale() reads a little high, which would leave the black a faint veil)
    luma = bytes((299 * r + 587 * g + 114 * b + 500) // 1000 for r, g, b in zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    rgba = bytearray(w * h * 4)
    rgba[0::4] = rgba[1::4] = rgba[2::4] = luma
    rgba[3::4] = luma.translate(SPLASH_ALPHA)
    return pygame.image.frombytes(bytes(rgba), (w, h), "RGBA").convert_alpha()


def build_splash(name, path):
    img = pygame.image.load(path).convert()
    if name in SPLASH_CROP:
        img = img.subsurface((0, 0, img.get_width(), round(img.get_height() * SPLASH_CROP[name]))).copy()
    img = key_splash(img)
    if name in SPLASH_CROP:  # feather the crop line so the splash doesn't end in a ruler-straight edge
        w, h = img.get_size()
        band = h // 8
        fade = pygame.Surface((w, band), pygame.SRCALPHA)
        for y in range(band):
            fade.fill((255, 255, 255, round(255 * (1 - (y + 1) / band) ** 1.5)), (0, y, w, 1))
        img.blit(fade, (0, h - band), special_flags=pygame.BLEND_RGBA_MULT)
    rect = pygame.mask.from_surface(img, 8).get_bounding_rects()
    box = rect[0].unionall(rect[1:]) if rect else img.get_rect()
    img = img.subsurface(box).copy()
    img = scale_by(img, SPLASH_SIZE / max(img.get_size()))
    pygame.image.save(img, os.path.join(OUT, f"splash_{name}.png"))
    print(f"splash_{name}.png", img.get_size())


def build_background(src):
    img = pygame.image.load(src).convert()
    iw, ih = img.get_size()
    k = max(W / iw, H / ih)
    img = pygame.transform.smoothscale(img, (max(W, round(iw * k)), max(H, round(ih * k))))
    x, y = (img.get_width() - W) // 2, (img.get_height() - H) // 2
    out = img.subsurface((x, y, W, H)).copy()
    path = os.path.join(OUT, "background.jpg")
    pygame.image.save(out, path)
    print("background.jpg", out.get_size())


def main():
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    with open(os.path.join(RAW, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    os.makedirs(OUT, exist_ok=True)

    def src(name):
        return os.path.join(ROOT, manifest[name])

    names = list(FRUITS) + ["bomb"]
    for name in names:
        r = BOMB_R if name == "bomb" else FRUITS[name].r
        whole = load_trimmed(src(name))
        k = FILL * r / max(whole.get_size())
        whole = scale_by(whole, k)
        if name == "double":
            gold_grade(whole)
        pygame.image.save(whole, os.path.join(OUT, name + ".png"))
        print(f"{name}.png", whole.get_size())
        if name + "_half" in manifest:
            half = scale_by(load_trimmed(src(name + "_half")), k)  # same factor as its whole
            pygame.image.save(half, os.path.join(OUT, name + "_half.png"))
            print(f"{name}_half.png", half.get_size())
    build_background(src("background"))
    for key in manifest:
        if key.startswith("splash_"):
            build_splash(key[len("splash_"):], src(key))


if __name__ == "__main__":
    main()
