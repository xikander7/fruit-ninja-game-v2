import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resource_path(*parts):
    """A bundled file: under the PyInstaller unpack dir (sys._MEIPASS) in the .exe, else under the repo."""
    return Path(getattr(sys, "_MEIPASS", REPO_ROOT)) / Path(*parts)


W, H = 1280, 720
FPS = 120
GRAVITY = 1250.0

SAVE_PATH = Path.home() / ".fruit_ninja_dojo.json"
TITLE = "Hanifa"  # the menu title is a signature: a person's name, spelled exactly
SUBTITLE = "THE FRUIT NINJA"
CAPTION = "Hanifa · The Fruit Ninja"

# Palette: dark and few colours; light comes from the blade, juice and effects.
INK = (10, 8, 8)
WASHI = (236, 228, 210)  # paper white: text
GOLD = (226, 182, 92)  # the only UI emphasis colour
HANKO = (196, 40, 36)  # seals, strikes, danger, nothing else
STEEL = (190, 215, 235)
MUTED = (150, 138, 120)  # secondary text
LACQUER = INK  # v2 name, still used for the letterbox fill
CEDAR = (92, 54, 36)  # procedural fallback wood only

# name: (outer glow, mid, core, unlock score)
BLADES = {
    "Moonlight": ((40, 90, 170), (120, 190, 255), (255, 255, 255), 0),
    "Sakura": ((170, 40, 100), (255, 140, 195), (255, 240, 248), 100),
    "Ember": ((190, 50, 0), (255, 140, 30), (255, 240, 190), 250),
    "Gold Leaf": ((150, 100, 0), (255, 205, 70), (255, 255, 225), 500),
}

MODES = {
    "classic": {"title": "Classic", "glyph": "斬", "hint": "3 strikes · bombs end it"},
    "arcade": {"title": "Arcade", "glyph": "速", "hint": "60 seconds · power bananas"},
    "zen": {"title": "Zen", "glyph": "禅", "hint": "90 seconds · no bombs"},
    "path": {"title": "Ninja Path", "glyph": "道", "hint": "Endless · powers · bosses"},
}
# which v4 systems each mode runs; every hook is a no-op when its flag is off
MODE_FEATURES = {"classic": set(), "zen": set(), "arcade": {"powers", "fever"}, "path": {"powers", "fever", "boss", "hazards"}}
