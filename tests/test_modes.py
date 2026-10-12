import os, tempfile, unittest
from pathlib import Path
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game, settings
from ninja.entities import Body

DT = 1 / 60

def run(app, n):
    for _ in range(n):
        app.step(DT, [])

class Modes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit(); self.tmp.cleanup()

    def test_feature_table(self):
        self.assertEqual(settings.MODE_FEATURES["classic"], set())
        self.assertEqual(settings.MODE_FEATURES["zen"], set())
        self.assertEqual(settings.MODE_FEATURES["arcade"], {"powers", "fever"})
        self.assertEqual(settings.MODE_FEATURES["path"], {"powers", "fever", "boss", "hazards"})

    def test_old_save_gets_path_best(self):
        game.SAVE_PATH.write_text('{"best": {"classic": 5, "arcade": 1, "zen": 2}}', encoding="utf-8")
        self.assertEqual(game.load_save()["best"]["path"], 0)

    def test_path_bomb_costs_a_life_not_the_run(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        self.assertEqual(p.lives, 3)
        p.launch("bomb", 640); run(app, 30)
        b = next(b for b in p.w.bodies if b.bomb)
        p.hit(b, (b.x - 50, b.y, b.x + 50, b.y))
        self.assertEqual(p.lives, 2)
        self.assertEqual(p.state, "play")

    def test_path_three_lost_lives_end_the_run(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        for _ in range(3):
            p.lose_life(640, "test")
        self.assertEqual(p.state, "dying")
        run(app, 200)
        self.assertIsInstance(app.scene, game.GameOver)
        self.assertIn("path", app.save["best"])

    def test_path_life_regained_every_150(self):
        app = self.app
        app.go(lambda: game.Play(app, "path")); p = app.scene; run(app, 80)
        p.lose_life(640, "test"); self.assertEqual(p.lives, 2)
        p.add_score(150)
        self.assertEqual(p.lives, 3)
        p.add_score(150)
        self.assertEqual(p.lives, 3)  # capped

    def test_body_gone_both_directions(self):
        b = Body(self.app.art, "apple", 640, -200, 0, -300)
        self.assertTrue(b.gone())
        b = Body(self.app.art, "apple", 640, 900, 0, 300)
        self.assertTrue(b.gone())
        b = Body(self.app.art, "apple", 640, 300, 0, -300)
        self.assertFalse(b.gone())

    def test_menu_key_4_starts_path(self):
        app = self.app; run(app, 10)
        app.step(DT, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=0, unicode="4", scancode=0)])
        run(app, 60)
        self.assertIsInstance(app.scene, game.Play)
        self.assertEqual(app.scene.mode, "path")

    def test_classic_and_zen_have_no_new_systems(self):
        app = self.app
        for mode in ("classic", "zen"):
            app.go(lambda: game.Play(app, mode)); p = app.scene
            self.assertEqual(p.features, set())
