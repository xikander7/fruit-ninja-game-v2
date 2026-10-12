"""Headless checks: hit math + a full scripted run through every scene."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402

from ninja import game  # noqa: E402
from ninja.entities import seg_hits_circle  # noqa: E402

DT = 1 / 60


def move(app, p):
    app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(0, 0), buttons=(0, 0, 0))])


def swipe(app, a, b, steps=4):
    """No clicking: moving the cursor fast is the blade."""
    move(app, a)
    for i in range(1, steps + 1):
        move(app, (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps))


def run(app, frames):
    for _ in range(frames):
        app.step(DT, [])


class HitMath(unittest.TestCase):
    def test_segment_circle(self):
        self.assertTrue(seg_hits_circle(0, 0, 10, 0, 5, 3, 4))
        self.assertFalse(seg_hits_circle(0, 0, 10, 0, 5, 5, 4))
        self.assertTrue(seg_hits_circle(0, 0, 0, 0, 1, 1, 2))  # zero-length segment
        self.assertFalse(seg_hits_circle(0, 0, 10, 0, 20, 0, 4))  # beyond the end


class CursorOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def test_slow_drift_and_teleport_do_not_cut(self):
        app = self.app
        b = app.scene.buttons[0]
        move(app, (b.x - 60, b.y))
        for i in range(1, 25):  # 4.9 px/frame at 60 fps = 294 px/s, just under SLICE_SPEED
            move(app, (b.x - 60 + i * 4.9, b.y))
        self.assertTrue(b.body.alive)
        move(app, (5, 5))
        move(app, (b.x + 400, b.y))  # big jump (re-entering the window) is ignored
        self.assertTrue(b.body.alive)
        swipe(app, (b.x - 100, b.y), (b.x + 100, b.y))  # a fast flick cuts, no click
        self.assertFalse(b.body.alive)


class FullRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def slice_all(self, scene, kinds=None):
        n = 0
        for b in list(scene.w.bodies):
            if b.alive and (kinds is None or b.kind in kinds) and 0 < b.y < 720:
                swipe(self.app, (b.x - 90, b.y - 60), (b.x + 90, b.y + 60))
                n += 1
        return n

    def test_classic_to_gameover_and_retry(self):
        app = self.app
        run(app, 10)
        b = app.scene.buttons[0]
        swipe(app, (b.x - 100, b.y - 80), (b.x + 100, b.y + 80))  # slice the menu watermelon
        run(app, 60)
        self.assertIsInstance(app.scene, game.Play)
        play = app.scene
        for _ in range(40):
            run(app, 12)
            self.slice_all(play, [k for k in game.FRUITS])
            if play.score >= 5:
                break
        self.assertGreater(play.score, 0)
        play.launch("bomb", 640)
        run(app, 30)
        bomb = next(b for b in play.w.bodies if b.bomb)
        swipe(app, (bomb.x - 90, bomb.y), (bomb.x + 90, bomb.y))
        self.assertEqual(play.state, "dying")
        run(app, 150)
        self.assertIsInstance(app.scene, game.GameOver)
        self.assertEqual(app.save["best"]["classic"], play.score)
        self.assertTrue(game.SAVE_PATH.exists())
        app.step(DT, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="\r", scancode=0)])
        run(app, 60)
        self.assertIsInstance(app.scene, game.Play)

    def test_arcade_specials_and_timeout(self):
        app = self.app
        app.go(lambda: game.Play(app, "arcade"))
        play = app.scene
        run(app, 80)
        for kind in ("freeze", "frenzy", "double"):
            play.launch(kind, 640)
            run(app, 30)
            self.slice_all(play, [kind])
        self.assertTrue(play.freeze > 0 or play.frenzy > 0 or play.double > 0)
        play.time = 0.5
        run(app, 200)
        self.assertIsInstance(app.scene, game.GameOver)

    def test_corrupt_save_is_ignored(self):
        game.SAVE_PATH.write_text("{not json", encoding="utf-8")
        self.assertEqual(game.load_save()["best"]["classic"], 0)


if __name__ == "__main__":
    unittest.main()
