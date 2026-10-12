"""World animation / VFX logic: blade smoothing, post-fx decay after a bomb, combo slow-mo."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["NINJA_NO_GPU"] = "1"

import pygame  # noqa: E402

from ninja import game  # noqa: E402
from ninja.entities import depth_scale  # noqa: E402
from ninja.fx import catmull_rom  # noqa: E402

DT = 1 / 60
NEUTRAL = {"zoom": 1.0, "shocks": [], "aberration": 0.0, "saturation": 1.0, "flash": 0.0}


class CatmullRom(unittest.TestCase):
    def test_passes_through_control_points(self):
        pts = [(0, 0, 0.0), (40, 10, 0.1), (90, -20, 0.2), (120, 35, 0.3), (200, 0, 0.4)]
        out = catmull_rom(pts, 4)
        self.assertEqual(len(out), (len(pts) - 1) * 4 + 1)
        for i, p in enumerate(pts):
            for a, b in zip(out[i * 4], p):
                self.assertAlmostEqual(a, b, places=9)

    def test_subdivides_between_points(self):
        out = catmull_rom([(0, 0), (100, 0)], 4)
        xs = [x for x, _ in out]
        self.assertEqual(xs, sorted(xs))  # no overshoot or backtracking on a straight stroke
        self.assertAlmostEqual(xs[2], 50)
        self.assertTrue(all(y == 0 for _, y in out))

    def test_short_input_is_returned_as_is(self):
        self.assertEqual(catmull_rom([(5, 5)], 4), [(5, 5)])


class Depth(unittest.TestCase):
    def test_scale_peaks_mid_flight(self):
        self.assertAlmostEqual(depth_scale(0, 2.0), 0.9)
        self.assertAlmostEqual(depth_scale(1.0, 2.0), 1.04)
        self.assertAlmostEqual(depth_scale(5.0, 2.0), 0.9)  # clamped after landing
        self.assertEqual(depth_scale(3.0, None), 1.0)  # static menu fruit


class WorldFx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()
        self.play = game.Play(self.app, "arcade")
        self.app.scene = self.play
        self.play.state = "play"

    def tearDown(self):
        pygame.quit()
        self.tmp.cleanup()

    def run_for(self, seconds):
        for _ in range(round(seconds / DT)):
            self.app.step(DT, [])

    def test_bomb_fx_returns_to_neutral(self):
        play = self.play
        play.mode = "zen"  # a bomb in zen doesn't end the run, so the scene stays put
        b = play.w.throw("bomb", 640, 360, 0, 0, static=True)
        play.hit(b, (600, 360, 680, 360))
        fx = play.fx_params()
        self.assertGreater(fx["flash"], 0.5)
        self.assertEqual(len(fx["shocks"]), 1)
        self.assertGreater(fx["aberration"], 0.0)
        self.run_for(0.1)
        shock = play.fx_params()["shocks"][0]
        self.assertGreater(shock[2], 0.0)  # the ring has started to grow
        self.assertAlmostEqual(shock[0], 0.5, delta=0.05)
        self.run_for(1.9)
        self.assertIs(self.app.scene, play)
        self.assertEqual(play.fx_params(), NEUTRAL)

    def test_four_fruit_combo_slows_time_then_recovers(self):
        play, w = self.play, self.play.w
        fruits = [w.throw("orange", 300 + i * 150, 360, 0, 0, static=True) for i in range(4)]
        for i, b in enumerate(fruits):
            play.hit(b, (b.x - 50, b.y, b.x + 50, b.y))
            if i == 2:
                self.assertGreater(play.fx_params()["zoom"], 1.0)  # 3-combo punch
                self.assertEqual(w.time_scale(), 1.0)
        self.assertLess(w.time_scale(), 1.0)
        fx = play.fx_params()
        self.assertAlmostEqual(fx["saturation"], 0.65)
        self.assertAlmostEqual(fx["zoom"], 1.03)
        self.run_for(1.0)
        self.assertEqual(w.time_scale(), 1.0)
        self.assertEqual(play.fx_params()["zoom"], 1.0)

    def test_glow_layer_shakes_with_the_world_on_gpu_path(self):
        app, w = self.app, self.play.w
        app.gpu = object()  # World/App only test it against None while drawing
        w.particles.items.clear()
        w.throw("double", 640, 360, 0, 0, static=True)  # special: its aura is drawn to the glow layer

        def centroid():
            app.add.fill((0, 0, 0))
            w.draw(app.frame)
            sx = sy = n = 0
            for x in range(490, 791, 2):
                for y in range(210, 511, 2):
                    v = app.add.get_at((x, y))[0]
                    sx, sy, n = sx + x * v, sy + y * v, n + v
            return sx / n, sy / n

        cx, cy = centroid()
        w.shake.trauma, w.shake.t = 1.0, 0.37
        ox, oy = (round(v) for v in w.shake.offset())
        self.assertGreater(abs(ox) + abs(oy), 5)
        sx, sy = centroid()
        self.assertAlmostEqual(sx - cx, ox, delta=1.5)
        self.assertAlmostEqual(sy - cy, oy, delta=1.5)

    def test_swipe_during_hitstop_still_cuts(self):
        w = self.play.w
        b = w.throw("orange", 640, 360, 0, 0, static=True)
        w.hitstop = 0.1
        self.app.segments = [(540, 360, 740, 360)]
        self.play.update(DT)
        self.assertFalse(b.alive)

    def test_slowmo_slows_bodies(self):
        w = self.play.w
        b = w.throw("orange", 640, 600, 0, -1000)
        y0 = b.y
        w.slow()
        self.play.update(DT)
        self.assertAlmostEqual(b.y - y0, -1000 * DT * 0.3 + 1250 * (DT * 0.3) ** 2, delta=0.5)


if __name__ == "__main__":
    unittest.main()
