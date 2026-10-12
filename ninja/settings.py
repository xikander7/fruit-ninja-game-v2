from pathlib import Path

W, H = 1280, 720
FPS = 120
GRAVITY = 1250.0
SAVE_PATH = Path.home() / ".fruit_ninja_dojo.json"

# Palette — named by role
LACQUER = (22, 14, 12)
CEDAR = (92, 54, 36)
WASHI = (243, 233, 210)
GOLD = (242, 193, 78)
HANKO = (200, 48, 42)
MOON = (170, 220, 255)

# name: (outer glow, mid, core, unlock score)
BLADES = {
    "Moonlight": ((40, 90, 170), (120, 190, 255), (255, 255, 255), 0),
    "Sakura": ((170, 40, 100), (255, 140, 195), (255, 240, 248), 100),
    "Ember": ((190, 50, 0), (255, 140, 30), (255, 240, 190), 250),
    "Gold Leaf": ((150, 100, 0), (255, 205, 70), (255, 255, 225), 500),
}

MODES = {
    "classic": {"title": "CLASSIC", "glyph": "斬", "hint": "3 strikes · bombs end it"},
    "arcade": {"title": "ARCADE", "glyph": "速", "hint": "60 seconds · power bananas"},
    "zen": {"title": "ZEN", "glyph": "禅", "hint": "90 seconds · no bombs"},
}
