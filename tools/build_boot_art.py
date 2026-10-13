"""Cut the high-resolution fruit art for the boot screen (web/index.html) from the raw source cutouts.

Run from the repo root:  python tools/build_boot_art.py      (needs Pillow: pip install pillow)
Reads assets/raw (git-ignored) and writes assets/boot/*.webp, which are committed; tools/build_web_js.py copies
them into web/assets/boot for deploy. The in-game sprites are only ~100 px, far too soft for a full-screen
title, so the boot screen gets its own larger cuts: whole fruit and its cut half, trimmed and downsized to WHOLE px on
the whole fruit's long side (the half keeps the same scale), plus one juice splash keyed from luma (white on black, as in build_sprites.py).
"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "raw"
OUT = ROOT / "assets" / "boot"
FRUITS = ["watermelon", "orange", "kiwi", "dragonfruit", "apple", "strawberry", "lemon", "peach", "banana"]
WHOLE, SPLASH = 360, 760
# luma -> alpha, same curve as build_sprites.SPLASH_ALPHA: the black studio background keys out
SPLASH_ALPHA = [max(0, min(255, round((v - 12) * 1.6))) for v in range(256)]


def trimmed(path):
    img = Image.open(path).convert("RGBA")
    return img.crop(img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())


def scaled(img, k):
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def splash(path):
    luma = Image.open(path).convert("L")
    img = Image.merge("LA", (luma, luma.point(SPLASH_ALPHA))).convert("RGBA")
    img = img.crop(img.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    k = SPLASH / max(img.size)
    return img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)


def main():
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FRUITS:
        whole = trimmed(ROOT / manifest[name])
        k = WHOLE / max(whole.size)  # a half shares its whole's scale, so the page can size it from the whole
        for key, img in ((name, whole), (name + "_half", trimmed(ROOT / manifest[name + "_half"]))):
            img = scaled(img, k)
            img.save(OUT / f"{key}.webp", quality=84, method=6)
            print(f"{key}.webp", img.size)
    img = splash(ROOT / manifest["splash_burst1"])
    img.save(OUT / "splash.webp", quality=84, method=6)
    print("splash.webp", img.size)


if __name__ == "__main__":
    main()
