"""UI: every scene renders headless, the rolling score converges, the seal drop curve, font fallback."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_NO_GPU"] = "1"

import pygame  # noqa: E402

from ninja import art, game  # noqa: E402
from ninja.fx import stamp_scale  # noqa: E402

DT = 1 / 60


def run(app, n):
    for _ in range(n):
        app.step(DT, [])


class Scenes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def show(self, scene):
        self.app.scene, self.app.wipe = scene, None
        run(self.app, 30)
        return scene

    def test_menu_renders(self):
        self.show(game.Menu(self.app))

    def test_play_classic_renders(self):
        p = game.Play(self.app, "classic")
        p.state = "play"
        p.strike(p.w.throw("apple", 640, 800, 0, 0))
        self.show(p)
        self.assertEqual(p.strikes, 1)

    def test_play_arcade_renders(self):
        p = game.Play(self.app, "arcade")
        p.state, p.time, p.double, p.freeze, p.frenzy = "play", 4.5, 3.0, 2.0, 1.0
        self.show(p)

    def test_game_over_renders(self):
        p = game.Play(self.app, "classic")
        p.score = 40
        self.show(game.GameOver(self.app, p, self.app.frame.copy()))

    def test_paused_play_renders(self):
        p = game.Play(self.app, "arcade")
        p.paused = True
        self.show(p)
        self.assertIsNotNone(p.pause_bg)

    def test_wipe_renders(self):
        self.app.go(lambda: game.Menu(self.app))
        run(self.app, 40)
        self.assertIsNone(self.app.wipe)

    def test_rolling_score_converges_within_a_second(self):
        p = game.Play(self.app, "arcade")
        p.state = "play"
        self.app.scene, self.app.wipe = p, None
        p.add_score(1234)
        run(self.app, 2)
        self.assertLess(p.shown, 1234)  # it rolls rather than jumping
        run(self.app, 58)
        self.assertEqual(round(p.shown), 1234)
        p.score -= 10  # a bomb in arcade: the counter rolls back down too
        run(self.app, 60)
        self.assertEqual(round(p.shown), 1224)


class SealDrop(unittest.TestCase):
    def test_drop_curve(self):
        self.assertAlmostEqual(stamp_scale(0.0), 1.8)
        self.assertAlmostEqual(stamp_scale(0.11), 1.0)
        lows = [stamp_scale(i / 1000) for i in range(110, 400)]
        self.assertAlmostEqual(min(lows), 0.92, places=3)  # the undershoot as the stone bites
        self.assertEqual(stamp_scale(0.5), 1.0)


class FontsTest(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((64, 64))

    def tearDown(self):
        pygame.quit()

    def test_tracking_widens_text(self):
        f = art.Fonts()
        plain = f.text(f.mono12, "SCORE", (255, 255, 255))
        spaced = f.text(f.mono12, "SCORE", (255, 255, 255), 4)
        self.assertEqual(spaced.get_width(), sum(f.mono12.size(c)[0] for c in "SCORE") + 4 * 4)
        self.assertGreater(spaced.get_width(), plain.get_width())
        self.assertIs(f.text(f.mono12, "SCORE", (255, 255, 255), 4), spaced)  # cached

    def test_missing_font_files_fall_back_to_system_fonts(self):
        old = art.FONT_DIR
        with tempfile.TemporaryDirectory() as empty:
            art.FONT_DIR = empty
            try:
                f = art.Fonts()
            finally:
                art.FONT_DIR = old
        self.assertGreater(f.title.get_height(), 0)
        self.assertGreater(f.text(f.score, "123", (255, 255, 255)).get_width(), 0)


if __name__ == "__main__":
    unittest.main()
