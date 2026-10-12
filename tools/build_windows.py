"""Build the Windows edition: a self-contained folder with FruitNinjaNightDojo.exe, zipped for sharing.

    pip install -r requirements-dev.txt
    python tools/build_windows.py

Output: dist/FruitNinjaNightDojo/ (double-click the .exe, no Python needed) and dist/FruitNinjaNightDojo-windows.zip.
Both dist/ and build/ are git-ignored: the zip is a release file, not part of the repo."""
import io
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "FruitNinjaNightDojo"
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"


def make_icon(path):
    """The watermelon sprite as a .ico (PNG-compressed entries, which Windows Vista+ reads), made with pygame."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    src = pygame.image.load(str(ROOT / "assets" / "sprites" / "watermelon.png")).convert_alpha()
    w, h = src.get_size()
    side = max(w, h)
    square = pygame.Surface((side, side), pygame.SRCALPHA)
    square.blit(src, ((side - w) // 2, (side - h) // 2))
    entries = []
    for size in (256, 64, 48, 32, 16):
        tmp = WORK / f"icon{size}.png"
        pygame.image.save(pygame.transform.smoothscale(square, (size, size)), str(tmp))
        entries.append((size, tmp.read_bytes()))
    pygame.quit()
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for size, data in entries:
        out.write(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, data in entries:
        out.write(data)
    path.write_bytes(out.getvalue())


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    icon = WORK / "watermelon.ico"
    make_icon(icon)
    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"), "--noconfirm", "--clean", "--noconsole",
           "--name", NAME, "--icon", str(icon)]
    for sub in ("sprites", "audio", "fonts", "glyphs"):  # not assets/raw: the source art is git-ignored and never ships
        cmd += ["--add-data", f"{ROOT / 'assets' / sub};assets/{sub}"]
    # moderngl picks its GL loader at runtime, so PyInstaller can't see the import
    cmd += ["--hidden-import", "glcontext", "--hidden-import", "glcontext.wgl",
            "--exclude-module", "numpy",  # a dev tool only; pygame's optional array hooks would drag in ~27 MB
            "--distpath", str(DIST), "--workpath", str(WORK), "--specpath", str(WORK)]
    subprocess.run(cmd, check=True, cwd=ROOT)
    folder = DIST / NAME
    zpath = DIST / f"{NAME}-windows.zip"
    zpath.unlink(missing_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(folder.rglob("*")):
            z.write(f, Path(NAME) / f.relative_to(folder))
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"built {folder} ({size / 1e6:.1f} MB)")
    print(f"zipped {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
