"""Game-mode tests: which features each mode has (classic, arcade, zen, path), lives, saves and Fever in play."""
import os, tempfile, unittest
from pathlib import Path
# Run without a window, sound card or GPU so the tests work on any machine (including a build server).
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game, settings
from ninja.entities import Body

# One frame at 60 frames per second, in seconds.
DT = 1 / 60
# A y position just below the bottom of the screen.
H_OFF = settings.H + 100  # just past the bottom edge, still falling

def run(app, n):
    """Advance the game n frames with no input."""
    for _ in range(n):
        app.step(DT, [])

class Modes(unittest.TestCase):
    """Mode rules, lives and Fever, checked in a real running game."""
    def setUp(self):
        """Use a throwaway save file and start the game at the menu."""
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        """Shut pygame down and delete the temporary save folder."""
        pygame.quit(); self.tmp.cleanup()

    # Proves: each mode has exactly the features it should (powers, fever, boss, hazards).
    def test_feature_table(self):
        self.assertEqual(settings.MODE_FEATURES["classic"], set())
        self.assertEqual(settings.MODE_FEATURES["zen"], set())
        self.assertEqual(settings.MODE_FEATURES["arcade"], {"powers", "fever"})
        self.assertEqual(settings.MODE_FEATURES["path"], {"powers", "fever", "boss", "hazards"})

    # Proves: a save file from before the path mode existed still loads and gets a best score of 0 for it.
    def test_old_save_gets_path_best(self):
        game.SAVE_PATH.write_text('{"best": {"classic": 5, "arcade": 1, "zen": 2}}', encoding="utf-8")
        self.assertEqual(game.load_save()["best"]["path"], 0)

    # Proves: in path mode a bomb takes one life but the run continues.
    def test_path_bomb_costs_a_life_not_the_run(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        self.assertEqual(p.lives, 3)
        p.launch("bomb", 640); run(app, 30)
        b = next(b for b in p.w.bodies if b.bomb)
        p.hit(b, (b.x - 50, b.y, b.x + 50, b.y))
        self.assertEqual(p.lives, 2)
        self.assertEqual(p.state, "play")

    # Proves: losing three lives ends the run and saves the result.
    def test_path_three_lost_lives_end_the_run(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        for _ in range(3):
            p.lose_life(640, "test")
        self.assertEqual(p.state, "dying")
        run(app, 200)
        self.assertIsInstance(app.scene, game.GameOver)
        self.assertIn("path", app.save["best"])

    # Proves: every 150 points earns a life back, up to the maximum of 3.
    def test_path_life_regained_every_150(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        p.lose_life(640, "test"); self.assertEqual(p.lives, 2)
        p.add_score(150)
        self.assertEqual(p.lives, 3)
        p.add_score(150)
        self.assertEqual(p.lives, 3)  # capped

    # Proves: a fruit counts as gone once it leaves through the top or bottom, but not while it is still on screen.
    def test_body_gone_both_directions(self):
        b = Body(self.app.art, "apple", 640, -200, 0, -300)
        self.assertTrue(b.gone())
        b = Body(self.app.art, "apple", 640, 900, 0, 300)
        self.assertTrue(b.gone())
        b = Body(self.app.art, "apple", 640, 300, 0, -300)
        self.assertFalse(b.gone())

    # Proves: pressing 4 at the menu starts path mode.
    def test_menu_key_4_starts_path(self):
        app = self.app; run(app, 10)
        app.step(DT, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=0, unicode="4", scancode=0)])
        run(app, 60)
        self.assertIsInstance(app.scene, game.Play)
        self.assertEqual(app.scene.mode, "path")

    # Proves: classic and zen have none of the extra systems.
    def test_classic_and_zen_have_no_new_systems(self):
        app = self.app
        for mode in ("classic", "zen"):
            app.go(lambda: game.Play(app, mode)); p = app.scene
            self.assertEqual(p.features, set())

    # --- fever ---
    def cut_n(self, p, n):
        """Cut n apples in a row."""
        for _ in range(n):
            b = p.w.throw("apple", 640, 300, 0, 0)
            p.hit(b, (590, 300, 690, 300))

    def start(self, mode):
        """Start a game in the given mode, play past the countdown, and stop new fruit from spawning."""
        app = self.app
        app.go(lambda: game.Play(app, mode)); p = app.scene; run(app, 80)
        p.spawn_t = 999
        return p

    # Proves: 40 cuts in a row start Fever in arcade, and Fever multiplies the points by 5.
    def test_arcade_forty_cuts_start_fever(self):
        p = self.start("arcade")
        self.assertIsNotNone(p.fever)
        self.cut_n(p, 39); self.assertFalse(p.fever.active); self.assertEqual(p.fever.mult, 4)
        self.cut_n(p, 1); self.assertTrue(p.fever.active)
        s = p.score; self.cut_n(p, 1)
        self.assertIn(p.score - s, (5, 55))  # apple 1 point x5 (or a critical: (1 + 10) x5)

    # Proves: classic and zen have no Fever at all.
    def test_classic_and_zen_have_no_fever(self):
        for mode in ("classic", "zen"):
            self.assertIsNone(self.start(mode).fever)

    # Proves: a dropped fruit or a bomb resets the combo multiplier.
    def test_path_strike_and_bomb_reset_mult(self):
        p = self.start("path")
        self.cut_n(p, 25); self.assertEqual(p.fever.mult, 3)
        p.strike(p.w.throw("apple", 640, 900, 0, 300))
        self.assertEqual(p.fever.mult, 1)
        self.cut_n(p, 25); self.assertEqual(p.fever.mult, 3)
        b = p.w.throw("bomb", 640, 300, 0, 0)
        p.hit(b, (590, 300, 690, 300))
        self.assertEqual((p.fever.mult, p.fever.chain), (1, 0))

    # Proves: dropping a fruit during Fever costs a life but doesn't end Fever.
    def test_path_drop_during_fever_costs_life_keeps_fever(self):
        p = self.start("path")
        self.cut_n(p, 40); self.assertTrue(p.fever.active)
        b = p.w.throw("apple", 640, H_OFF, 0, 400); b.entered = True
        run(self.app, 5)
        self.assertFalse(b.alive)
        self.assertEqual(p.lives, 2)
        self.assertTrue(p.fever.active)

    # Proves: hitting a bomb during Fever ends it and resets the multiplier.
    def test_bomb_during_fever_ends_it(self):
        p = self.start("path")
        self.cut_n(p, 40); self.assertTrue(p.fever.active)
        b = p.w.throw("bomb", 640, 300, 0, 0)
        p.hit(b, (590, 300, 690, 300))
        self.assertFalse(p.fever.active); self.assertEqual(p.fever.mult, 1)

    # Proves: the bonus fruit raining down during Fever never cost a life, even when missed.
    def test_rain_fruit_never_cost_lives(self):
        p = self.start("path")
        self.cut_n(p, 40); self.assertTrue(p.fever.active)
        rained = set()
        for _ in range(240):
            run(self.app, 1)
            rained |= {id(b) for b in p.w.bodies if getattr(b, "rain", False)}
        self.assertGreater(len(rained), 5)
        self.assertEqual((p.lives, p.stats["missed"]), (3, 0))
        self.assertTrue(p.fever.active)  # dropped rain never ends the fever either

    # Proves: Time Stop pauses the Fever timer and the fruit rain.
    def test_time_stop_holds_fever(self):
        p = self.start("path")
        self.cut_n(p, 40); run(self.app, 2)
        p.ki.value = 100; self.assertTrue(p.use_power("timestop"))
        run(self.app, 30); t = p.fever.t
        n = len(p.w.bodies)
        run(self.app, 60)
        self.assertEqual(p.fever.t, t)
        self.assertEqual(len(p.w.bodies), n)  # no rain into frozen time
