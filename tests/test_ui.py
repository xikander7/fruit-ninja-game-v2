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
from ninja.settings import W, H  # noqa: E402

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


class Layers(unittest.TestCase):
    """The UI layer (HUD, stamps, overlays) and the glow layer, around snapshots and wipes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def test_ui_is_composited_onto_the_cpu_frame(self):
        app = self.app

        class Marker(game.Scene):
            def draw(self, screen):
                screen.fill((10, 10, 10))
                app.ui.fill((200, 40, 40, 255), (100, 100, 20, 20))

        app.scene, app.wipe = Marker(), None
        app.step(DT, [])
        self.assertEqual(tuple(app.frame.get_at((110, 110)))[:3], (200, 40, 40))
        self.assertEqual(tuple(app.frame.get_at((300, 300)))[:3], (10, 10, 10))

    def test_hud_draws_to_the_ui_layer(self):
        p = game.Play(self.app, "arcade")
        p.state = "play"
        self.app.scene, self.app.wipe = p, None
        run(self.app, 5)
        self.assertGreater(self.app.ui.get_at((60, 70)).a, 0)  # the score numerals

    def test_gpu_snapshot_flattens_glow_and_ui(self):
        app = self.app
        app.gpu = object()  # snapshot only tests it against None
        try:
            app.frame.fill((20, 20, 20))
            app.add.fill((0, 0, 0))
            app.add.fill((30, 0, 0), (0, 0, 50, 50))
            app.ui.fill((0, 0, 0, 0))
            app.ui.fill((0, 0, 255, 255), (60, 0, 10, 10))
            snap = app.snapshot()
        finally:
            app.gpu = None
        self.assertEqual(tuple(snap.get_at((10, 10)))[:3], (50, 20, 20))
        self.assertEqual(tuple(snap.get_at((65, 5)))[:3], (0, 0, 255))
        self.assertEqual(tuple(snap.get_at((200, 200)))[:3], (20, 20, 20))

    def test_wipe_hides_the_new_scenes_glow_and_ui_under_its_pieces(self):
        wipe = game.Wipe(pygame.Surface((W, H)))
        wipe.t = 0.1
        frame, add, ui = pygame.Surface((W, H)), pygame.Surface((W, H)), pygame.Surface((W, H), pygame.SRCALPHA)
        add.fill((255, 255, 255))
        ui.fill((255, 255, 255, 255))
        wipe.draw(frame, add, False, ui)
        # both pieces still cover the outer edges; the gap opens along the cut in the middle
        for x in (40, W - 40):
            self.assertEqual(tuple(add.get_at((x, H // 2)))[:3], (0, 0, 0))
            self.assertEqual(ui.get_at((x, H // 2)).a, 0)
        self.assertEqual(ui.get_at((W // 2, H // 2)).a, 255)  # revealed: the new scene's UI shows

    def test_game_over_key_cuts_the_fruit_and_stamps(self):
        p = game.Play(self.app, "classic")
        over = game.GameOver(self.app, p, self.app.frame.copy())
        self.app.scene, self.app.wipe = over, None
        stamps = len(over.w.stamps)
        over.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="", scancode=0))
        self.assertFalse(over.retry.body.alive)
        self.assertEqual(len(over.w.stamps), stamps + 1)
        self.assertEqual(over.choice, "retry")
        self.assertTrue(over.menu.body.alive)


class TitleIntro(unittest.TestCase):
    """Task 10: the menu opens with "Hanifa, the Fruit Ninja" signed in watermelon juice."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def test_title_strings(self):
        from ninja import settings
        self.assertEqual(settings.TITLE, "Hanifa")
        self.assertEqual(settings.SUBTITLE, "THE FRUIT NINJA")
        self.assertEqual(pygame.display.get_caption()[0], "Hanifa · The Fruit Ninja")

    def test_intro_settles_within_two_seconds(self):
        m = game.Menu(self.app)
        self.app.scene, self.app.wipe = m, None
        self.assertFalse(m.intro_done)
        run(self.app, 30)
        self.assertFalse(m.intro.melon.alive)  # cut at the apex by then
        run(self.app, 90)  # 2.0 s in all
        self.assertTrue(m.intro_done)

    def test_any_key_skips_the_intro(self):
        m = game.Menu(self.app)
        self.app.scene, self.app.wipe = m, None
        run(self.app, 5)
        m.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=0))
        self.assertTrue(m.intro_done)
        self.assertNotIn(m.intro.melon, m.w.bodies)
        run(self.app, 5)  # and the settled title draws fine
        self.assertIsNone(m.chosen)  # a non-mode key only skips


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
