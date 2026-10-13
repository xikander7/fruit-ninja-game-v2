"""Shareable editions: asset paths resolve inside a PyInstaller bundle; the browser build's frame step and save."""
import sys
import unittest
from pathlib import Path

from ninja import settings


class ResourcePath(unittest.TestCase):
    """Finding asset files both from the repo and from inside a packaged (PyInstaller) app."""
    # Proves: when run from the repo, asset paths point at the real assets folder.
    def test_repo_mode(self):
        self.assertTrue(settings.resource_path("assets", "fonts").is_dir())

    # Proves: inside a PyInstaller bundle (which sets sys._MEIPASS), asset paths point into the bundle.
    def test_frozen_mode(self):
        sys._MEIPASS = "C:/bundle"
        try:
            self.assertEqual(settings.resource_path("assets", "x.png"), Path("C:/bundle/assets/x.png"))
        finally:
            del sys._MEIPASS


class FrameStep(unittest.TestCase):
    """The one-frame-at-a-time loop used by the browser edition, and the safe save writer."""
    # Proves: the game can run 120 frames one step at a time with no window.
    def test_frame_step_runs_headless(self):
        import os
        os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
        from ninja import game
        app = game.App()
        for _ in range(120):
            app.frame_step()
        self.assertTrue(app.running)

    # Proves: failing to write the save file (bad path) doesn't crash the game.
    def test_unwritable_save_is_swallowed(self):
        from ninja import game
        old = game.SAVE_PATH
        game.SAVE_PATH = Path("Z:/definitely/not/here/save.json")
        try:
            game.write_save({"best": {}})
        finally:
            game.SAVE_PATH = old


class KanjiStencils(unittest.TestCase):
    """The browser has no Japanese font: seals fall back to the bundled glyph stencils."""

    def setUp(self):
        """Start pygame with a small hidden window."""
        import os
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))

    def tearDown(self):
        """Shut pygame down."""
        import pygame
        pygame.quit()

    # Proves: every kanji character in the code has a PNG stencil (run tools/build_glyphs.py if this fails).
    def test_every_kanji_in_the_game_has_a_stencil(self):
        import re
        chars = set()
        for f in (settings.REPO_ROOT / "ninja").glob("*.py"):
            chars |= set(re.findall(r"[㐀-鿿]", f.read_text(encoding="utf-8")))
        self.assertGreater(len(chars), 10)
        for c in chars:
            self.assertTrue(settings.resource_path("assets", "glyphs", f"{ord(c):x}.png").is_file(), c)

    # Proves: with no Japanese system font, the seal is drawn from the stencil, with the character cut out of the red.
    def test_seal_uses_the_stencil_without_a_system_font(self):
        from ninja import art
        old = art._system_kanji
        art._system_kanji = False
        try:
            g = art.kanji(art.Fonts(), "忍", 60)
            seal = art.make_seal(art.Fonts(), "忍", 100)
        finally:
            art._system_kanji = old
        self.assertEqual(g.get_height(), 87)  # the 120 px stencil (174 px tall) at half size
        self.assertLess(seal.get_at((50, 50)).a, 128)  # the glyph's strokes are cut out of the red


if __name__ == "__main__":
    unittest.main()
