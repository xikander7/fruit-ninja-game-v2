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

    # Proves: the English-only game can build a seal without a CJK font or legacy stencil asset.
    def test_english_seal_does_not_use_the_legacy_glyph_path(self):
        from ninja import art
        old = art.kanji
        art.kanji = lambda *_args, **_kwargs: self.fail("English seals must not request a CJK glyph")
        try:
            seal = art.make_seal(art.Fonts(), "GO", 100)
        finally:
            art.kanji = old
        self.assertGreater(seal.get_bounding_rect().width, 0)
        interior_alpha = [seal.get_at((x, y)).a for y in range(30, 71) for x in range(20, 81)]
        self.assertLess(min(interior_alpha), 64)  # some Latin strokes are cut out of the red


if __name__ == "__main__":
    unittest.main()
