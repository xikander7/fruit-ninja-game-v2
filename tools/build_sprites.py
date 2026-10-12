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


if __name__ == "__main__":
    main()
