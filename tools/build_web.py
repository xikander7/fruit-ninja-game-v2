"""Build the browser edition with pygbag (CPython compiled to WebAssembly).

    pip install -r requirements-dev.txt
    python tools/build_web.py

Copies main.py, ninja/ and assets/ into build/web_src/ (the sounds downsampled to mono 22.05 kHz to cut the
download roughly 4x), then runs `python -m pygbag --build`. The result, build/web_src/build/web/, is a static site
(index.html + the game archive) that any web host can serve, e.g. GitHub Pages. In the browser there is no OpenGL,
so the game draws on the CPU path; pygbag fetches its Python runtime from its CDN when the page loads.

Test it locally:  python -m http.server 8000 -d build/web_src/build/web   then open http://localhost:8000"""
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "web_src"
OUT = SRC / "build" / "web"


def mono_22k(src, dst):
    """16-bit WAV -> mono 22.05 kHz 16-bit WAV (channels averaged; 44.1 kHz halved with a 2-tap average)."""
    with wave.open(str(src)) as w:
        ch, rate, width = w.getnchannels(), w.getframerate(), w.getsampwidth()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
    assert width == 2, f"{src.name}: expected 16-bit audio"
    data = data.reshape(-1, ch).mean(axis=1)
    if rate == 44100:
        data = data[: len(data) // 2 * 2].reshape(-1, 2).mean(axis=1)
        rate = 22050
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.clip(np.round(data), -32768, 32767).astype("<i2").tobytes())


WEB_SKIP = {"music_2.wav", "fever_2.wav", "fuse_2.wav"}  # second takes of long loops: ~2 MB less to download

# pygbag's default page: grey/powder-blue background, green "Ready to start" box, no mobile handling
PAGE_FIXES = [
    ('platform.document.body.style.background = "#7f7f7f"', 'platform.document.body.style.background = "#0a0808"'),
    ("background-color:powderblue;", "background-color:#0a0808; color:#e2b65c; overflow:hidden; touch-action:none;"),
    ('msg  = "Ready to start ! Please click/touch page"', 'msg  = "Tap to start"'),
    ("""            background: green;
            color: blue;
            font-weight: bold;
            padding: 12px 24px;""",
     """            background: #0a0808; color: #e2b65c; border: 1px solid #e2b65c;
            font: 22px Georgia, serif; letter-spacing: 3px; padding: 14px 34px;
            top: 50% !important; left: 50% !important; right: auto !important; transform: translate(-50%, -50%); white-space: nowrap;"""),
    ("color: rgb(120, 120, 120);", "color: #968a78; font-family: Georgia, serif;"),
    ("</body>", """<div id="rotate">Turn your phone sideways</div>
<style>
#rotate { display:none; position:fixed; inset:0; z-index:9999999; background:#0a0808; color:#e2b65c;
          font:19px Georgia, serif; letter-spacing:1px; padding:24px; box-sizing:border-box; align-items:center; justify-content:center; text-align:center; }
@media (orientation: portrait) and (max-width: 900px) { #rotate { display:flex; } }
</style>
<script>
// phones: first tap goes fullscreen and locks landscape, so the game fills the screen
addEventListener("pointerdown", async () => {
  try { await document.documentElement.requestFullscreen(); await screen.orientation.lock("landscape"); } catch (e) {}
}, { once: true });
</script>
</body>"""),
]


def patch_page(path):
    html = path.read_text(encoding="utf-8")
    for old, new in PAGE_FIXES:
        assert old in html, f"pygbag template changed, can't find: {old[:50]!r}"
        html = html.replace(old, new)
    html = html.replace("<head>", '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">', 1)
    path.write_text(html, encoding="utf-8")


def size_of(folder):
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


def main():
    if SRC.exists():
        shutil.rmtree(SRC)
    SRC.mkdir(parents=True)
    shutil.copy2(ROOT / "main.py", SRC / "main.py")
    shutil.copytree(ROOT / "ninja", SRC / "ninja", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for sub in ("sprites", "fonts", "glyphs"):  # never assets/raw: the source art is git-ignored and never ships
        shutil.copytree(ROOT / "assets" / sub, SRC / "assets" / sub)
    audio = SRC / "assets" / "audio"
    audio.mkdir(parents=True)
    for f in sorted((ROOT / "assets" / "audio").glob("*.wav")):
        if f.name not in WEB_SKIP:
            mono_22k(f, audio / f.name)
    shutil.copy2(ROOT / "assets" / "sprites" / "watermelon.png", SRC / "favicon.png")
    print(f"audio {size_of(ROOT / 'assets' / 'audio') / 1e6:.1f} MB -> {size_of(audio) / 1e6:.1f} MB")
    cmd = [sys.executable, "-m", "pygbag", "--build", "--app_name", "hanifa-fruit-ninja",
           "--title", "Hanifa, the Fruit Ninja", "--icon", str(SRC / "favicon.png"),
           "--disable-sound-format-error",  # WAV: pygbag prefers OGG, but SDL_mixer in the browser reads WAV too
           str(SRC)]
    subprocess.run(cmd, check=True, cwd=ROOT)
    patch_page(OUT / "index.html")
    print(f"built {OUT} ({size_of(OUT) / 1e6:.1f} MB)")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}  {f.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
