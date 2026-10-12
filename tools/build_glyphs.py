"""Kanji stencils for the hanko seals, for machines with no Japanese system font (the browser build, most Linux).

    python tools/build_glyphs.py

Renders every CJK character used in ninja/*.py with Zen Kaku Gothic New Bold (SIL OFL 1.1, downloaded once into the
git-ignored assets/raw/fonts/) to assets/glyphs/<codepoint hex>.png: black, alpha-antialiased, 120 px font size.
art.make_seal uses a system font when there is one and these stencils otherwise."""
import os
import re
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "raw" / "fonts"
OUT = ROOT / "assets" / "glyphs"
FONT = "ZenKakuGothicNew-Bold.ttf"
URL = "https://github.com/google/fonts/raw/main/ofl/zenkakugothicnew/"
SIZE = 120  # font size the stencils are rendered at (art.GLYPH_SIZE)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, remote in ((FONT, FONT), ("OFL-ZenKakuGothicNew.txt", "OFL.txt")):
        if not (RAW / name).exists():
            urllib.request.urlretrieve(URL + remote, RAW / name)
    chars = set()
    for f in (ROOT / "ninja").glob("*.py"):
        chars |= set(re.findall(r"[㐀-鿿]", f.read_text(encoding="utf-8")))
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    font = pygame.font.Font(str(RAW / FONT), SIZE)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for c in sorted(chars):
        pygame.image.save(font.render(c, True, (0, 0, 0)), str(OUT / f"{ord(c):x}.png"))
    shutil.copy2(RAW / "OFL-ZenKakuGothicNew.txt", OUT / "OFL-ZenKakuGothicNew.txt")
    print(f"{len(chars)} glyphs -> {OUT}: {''.join(sorted(chars))}")


if __name__ == "__main__":
    main()
