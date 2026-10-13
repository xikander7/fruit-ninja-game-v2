"""UI: every scene renders headless, the rolling score converges, the seal drop curve, font fallback."""
import os
import tempfile
import unittest
from pathlib import Path

# Run without a window, sound card or GPU so the tests work on any machine (including a build server).
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_NO_GPU"] = "1"

import pygame  # noqa: E402

from ninja import art, game  # noqa: E402
from ninja.fx import stamp_scale  # noqa: E402
from ninja.settings import W, H  # noqa: E402
from ninja.title import make_streak  # noqa: E402

# One frame at 60 frames per second, in seconds.
DT = 1 / 60


def run(app, n):
    """Advance the game n frames with no input."""
    for _ in range(n):
        app.step(DT, [])


class Scenes(unittest.TestCase):
    """Each screen (menu, play, game over, pause, wipe) draws without errors."""
    def setUp(self):
        """Use a throwaway save file and start the game at the menu."""
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        """Shut pygame down and delete the temporary save folder."""
        pygame.quit()
        self.tmp.cleanup()

    def show(self, scene):
        """Make the scene the current one, run half a second, and return it."""
        self.app.scene, self.app.wipe = scene, None
        run(self.app, 30)
        return scene

    # Proves: the menu draws without errors.
    def test_menu_renders(self):
        self.show(game.Menu(self.app))

    # Proves: a brand-new player can select every blade without earning a high score first.
    def test_all_blades_are_available_to_a_new_player(self):
        menu = game.Menu(self.app)
        self.assertEqual(menu.unlocked(), ["Moonlight", "Petal Fan", "Ember", "Gold Leaf"])

    # Proves: the classic game draws, and a dropped fruit adds a strike.
    def test_play_classic_renders(self):
        p = game.Play(self.app, "classic")
        p.state = "play"
        p.strike(p.w.throw("apple", 640, 800, 0, 0))
        self.show(p)
        self.assertEqual(p.strikes, 1)

    # Proves: the arcade game draws with its special effects active.
    def test_play_arcade_renders(self):
        p = game.Play(self.app, "arcade")
        p.state, p.time, p.double, p.freeze, p.frenzy = "play", 4.5, 3.0, 2.0, 1.0
        self.show(p)

    # Proves: the game-over screen draws.
    def test_game_over_renders(self):
        p = game.Play(self.app, "classic")
        p.score = 40
        self.show(game.GameOver(self.app, p, self.app.frame.copy()))

    # Proves: a paused game draws and keeps a snapshot of the screen behind the pause menu.
    def test_paused_play_renders(self):
        p = game.Play(self.app, "arcade")
        p.paused = True
        self.show(p)
        self.assertIsNotNone(p.pause_bg)

    # Proves: the slashing screen-wipe between scenes plays and finishes.
    def test_wipe_renders(self):
        self.app.go(lambda: game.Menu(self.app))
        run(self.app, 40)
        self.assertIsNone(self.app.wipe)

    # Proves: the displayed score counts up smoothly to the real score (and back down after a penalty) within a second.
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
        """Use a throwaway save file and start the game at the menu."""
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        """Shut pygame down and delete the temporary save folder."""
        pygame.quit()
        self.tmp.cleanup()

    # Proves: without the GPU, the UI layer is painted on top of the game picture.
    def test_ui_is_composited_onto_the_cpu_frame(self):
        app = self.app

        class Marker(game.Scene):
            """A tiny test scene: a grey screen with one red square on the UI layer."""
            def draw(self, screen):
                screen.fill((10, 10, 10))
                app.ui.fill((200, 40, 40, 255), (100, 100, 20, 20))

        app.scene, app.wipe = Marker(), None
        app.step(DT, [])
        self.assertEqual(tuple(app.frame.get_at((110, 110)))[:3], (200, 40, 40))
        self.assertEqual(tuple(app.frame.get_at((300, 300)))[:3], (10, 10, 10))

    # Proves: the score numbers are drawn on the UI layer.
    def test_hud_draws_to_the_ui_layer(self):
        p = game.Play(self.app, "arcade")
        p.state = "play"
        self.app.scene, self.app.wipe = p, None
        run(self.app, 5)
        self.assertGreater(self.app.ui.get_at((60, 70)).a, 0)  # the score numerals

    # Proves: a screenshot combines the picture, the glow layer and the UI into one image.
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

    # Proves: during a wipe the new scene's glow and UI are hidden under the wipe pieces and revealed along the cut.
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

    # Proves: pressing Enter on game over slices the Retry fruit and stamps a seal.
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


class TitleHelpers(unittest.TestCase):
    # Proves: title heights whose final sine rounds just below zero still produce a valid blade streak.
    def test_streak_tolerates_floating_point_rounding_at_its_tip(self):
        pygame.display.set_mode((1, 1))
        try:
            streak = make_streak(209)
            self.assertGreater(streak.get_width(), 48)
            self.assertGreater(streak.get_height(), 209)
        finally:
            pygame.quit()


class TitleIntro(unittest.TestCase):
    """The menu opens with "Honey’s Slash & Splash" signed in watermelon juice."""

    def setUp(self):
        """Use a throwaway save file and start the game at the menu."""
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        """Shut pygame down and delete the temporary save folder."""
        pygame.quit()
        self.tmp.cleanup()

    # Proves: the game title, subtitle and window caption are the expected text.
    def test_title_strings(self):
        from ninja import settings
        self.assertEqual(settings.TITLE, "Honey’s Slash & Splash")
        self.assertEqual(settings.SUBTITLE, "FRUIT-SLICING ARCADE")
        self.assertEqual(pygame.display.get_caption()[0], "Honey’s Slash & Splash · Fruit-Slicing Arcade")

    # Proves: the longer title remains fully visible inside the 1280-pixel game stage.
    def test_title_fits_inside_the_stage(self):
        intro = game.Menu(self.app).intro
        self.assertGreaterEqual(intro.rect.left, 24)
        seal_x, _ = intro.seal_pos()
        self.assertLessEqual(seal_x + intro.seal.get_width(), W - 24)

    # Proves: the title intro slices its watermelon after half a second and finishes within two seconds.
    def test_intro_settles_within_two_seconds(self):
        m = game.Menu(self.app)
        self.app.scene, self.app.wipe = m, None
        self.assertFalse(m.intro_done)
        run(self.app, 30)
        self.assertFalse(m.intro.melon.alive)  # cut at the apex by then
        run(self.app, 90)  # 2.0 s in all
        self.assertTrue(m.intro_done)

    # Proves: pressing a key skips the intro without picking a game mode.
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
    """The size animation of a seal stamp dropping onto the screen."""
    # Proves: a stamp starts large, lands at normal size, dips slightly below as it bites in, then settles.
    def test_drop_curve(self):
        self.assertAlmostEqual(stamp_scale(0.0), 1.8)
        self.assertAlmostEqual(stamp_scale(0.11), 1.0)
        lows = [stamp_scale(i / 1000) for i in range(110, 400)]
        self.assertAlmostEqual(min(lows), 0.92, places=3)  # the undershoot as the stone bites
        self.assertEqual(stamp_scale(0.5), 1.0)


class FontsTest(unittest.TestCase):
    """Text drawing and font loading."""
    def setUp(self):
        """Start pygame with a small hidden window."""
        pygame.init()
        pygame.display.set_mode((64, 64))

    def tearDown(self):
        """Shut pygame down."""
        pygame.quit()

    # Proves: one-to-four-letter English seal labels are rendered inside the stamp's safe area.
    def test_english_seal_labels_are_cut_out_and_fit(self):
        self.assertTrue(hasattr(art, "latin_seal_text"))
        fonts = art.Fonts()
        for text in ("H", "GO", "TRY", "MENU"):
            glyph = art.latin_seal_text(fonts, text, 100)
            self.assertLessEqual(glyph.get_width(), 78)
            self.assertLessEqual(glyph.get_height(), 70)
            self.assertGreater(glyph.get_bounding_rect().width, 0)
            seal = art.make_seal(fonts, text, 100)
            self.assertGreater(pygame.mask.from_surface(seal).count(), 0)

    # Proves: letter spacing makes text wider by exactly the spacing added, and results are cached.
    def test_tracking_widens_text(self):
        f = art.Fonts()
        plain = f.text(f.mono12, "SCORE", (255, 255, 255))
        spaced = f.text(f.mono12, "SCORE", (255, 255, 255), 4)
        self.assertEqual(spaced.get_width(), sum(f.mono12.size(c)[0] for c in "SCORE") + 4 * 4)
        self.assertGreater(spaced.get_width(), plain.get_width())
        self.assertIs(f.text(f.mono12, "SCORE", (255, 255, 255), 4), spaced)  # cached

    # Proves: if the bundled font files are missing, system fonts are used instead of crashing.
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
