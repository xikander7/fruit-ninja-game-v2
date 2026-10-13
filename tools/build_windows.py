"""Build the Windows edition: a self-contained folder with HoneysSlashAndSplash.exe, zipped for sharing.

    pip install -r requirements.txt
    python tools/build_windows.py

Output: dist/HoneysSlashAndSplash/ (double-click the .exe, no Python needed) and dist/HoneysSlashAndSplash-windows.zip.
Both dist/ and build/ are git-ignored: the zip is a release file, not part of the repo."""
import io
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "HoneysSlashAndSplash"
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
    # Pad the sprite onto a square canvas so resizing it doesn't squash it.
    square = pygame.Surface((side, side), pygame.SRCALPHA)
    square.blit(src, ((side - w) // 2, (side - h) // 2))
    # An .ico file can hold several sizes so Windows can pick a sharp one for each place the icon shows up.
    entries = []
    for size in (256, 64, 48, 32, 16):
        tmp = WORK / f"icon{size}.png"
        pygame.image.save(pygame.transform.smoothscale(square, (size, size)), str(tmp))
        entries.append((size, tmp.read_bytes()))
    pygame.quit()
    # The .ico layout is: a 6-byte header, one 16-byte directory entry per image, then the PNG image data.
    # A width/height of 256 is stored as 0 in the file, which is why the entries use size % 256.
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
    """Make the icon, run PyInstaller to build the .exe folder, then zip it for sharing."""
    WORK.mkdir(parents=True, exist_ok=True)
    icon = WORK / "watermelon.ico"
    make_icon(icon)
    # PyInstaller packs main.py, Python itself and our libraries into one folder. --noconsole hides the black
    # terminal window, --clean clears PyInstaller's cache and --noconfirm overwrites old output without asking.
    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"), "--noconfirm", "--clean", "--noconsole",
           "--name", NAME, "--icon", str(icon)]
    # --add-data copies a folder into the bundle as 'source;destination' (';' is the separator on Windows).
    for sub in ("sprites", "audio", "fonts", "glyphs"):  # not assets/raw: the source art is git-ignored and never ships
        cmd += ["--add-data", f"{ROOT / 'assets' / sub};assets/{sub}"]
    # moderngl picks its GL loader at runtime, so PyInstaller can't see the import
    cmd += ["--hidden-import", "glcontext", "--hidden-import", "glcontext.wgl",
            "--exclude-module", "numpy",  # a dev tool only; pygame's optional array hooks would drag in ~27 MB
            "--distpath", str(DIST), "--workpath", str(WORK), "--specpath", str(WORK)]
    # Run PyInstaller from the repo root; check=True stops this script if the build fails.
    subprocess.run(cmd, check=True, cwd=ROOT)
    folder = DIST / NAME
    zpath = DIST / f"{NAME}-windows.zip"
    # Zip the folder so there is one file to share. Files are stored under a NAME/ folder, so unzipping makes a tidy directory.
    zpath.unlink(missing_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(folder.rglob("*")):
            z.write(f, Path(NAME) / f.relative_to(folder))
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"built {folder} ({size / 1e6:.1f} MB)")
    print(f"zipped {zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
