import os, random, tempfile, unittest
from pathlib import Path
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game
from ninja.hazards import Shuriken, roll_hazard, HAZARDS_FROM

DT = 1 / 60
def run(app, n):
    for _ in range(n): app.step(DT, [])
def move(app, p):
    app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(0, 0), buttons=(0, 0, 0))])

class HazardLogic(unittest.TestCase):
    def test_no_hazards_before_20s(self):
        rng = random.Random(1)
        self.assertTrue(all(roll_hazard(rng, HAZARDS_FROM - 1) is None for _ in range(500)))

    def test_shuriken_flies_at_target(self):
        s = Shuriken(0, 360, 640, 360)
        for _ in range(55): s.update(DT)
        self.assertTrue(s.near(640, 360))

class HazardsInPlay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App(); self.app.go(lambda: game.Play(self.app, "path")); self.p = self.app.scene
        run(self.app, 80); self.p.queue.clear(); self.p.spawn_t = 99

    def tearDown(self):
        pygame.quit(); self.tmp.cleanup()

    def test_shuriken_hit_costs_one_life(self):
        p = self.p
        move(self.app, (640, 360))
        p.throw_shuriken(0, 360, 640, 360)
        run(self.app, 90)
        self.assertEqual(p.lives, 2)

    def test_fast_slice_parries(self):
        p = self.p
        move(self.app, (640, 600))
        s = p.throw_shuriken(0, 300, 1280, 300)
        run(self.app, 50)  # shuriken near x≈580
        for x in (s.x - 120, s.x + 120):
            move(self.app, (x, s.y))
        self.assertTrue(s.parried); self.assertEqual(p.lives, 3)

    def test_ice_bomb_freezes_blade_2s(self):
        p = self.p
        ice = p.w.throw("icebomb", 640, 300, 0, 0, static=True)
        p.hit(ice, (540, 300, 740, 300))
        self.assertAlmostEqual(p.blade_frozen, 2.0, delta=0.05)
        f = p.w.throw("apple", 640, 500, 0, 0, static=True)
        move(self.app, (500, 500)); move(self.app, (780, 500))
        self.assertTrue(f.alive)
        self.assertEqual(p.lives, 3)

    def test_golden_needs_five_hits(self):
        p = self.p
        g = p.w.throw("golden", 640, 300, 0, 0, static=True)
        for i in range(4):
            p.hit(g, (540, 300, 740, 300)); run(self.app, 6)
            self.assertTrue(g.alive)
        p.hit(g, (540, 300, 740, 300))
        self.assertFalse(g.alive)

    def test_chaos_flips_gravity_and_drops_count_once(self):
        p = self.p
        c = p.w.throw("chaos", 640, 300, 0, 0, static=True)
        p.hit(c, (540, 300, 740, 300))
        self.assertEqual(p.w.gflip, -1)
        f = p.w.throw("apple", 640, 300, 0, -10)
        f.entered = True
        lives = p.lives
        run(self.app, int(1.5 / DT))
        self.assertFalse(f.alive)
        self.assertEqual(p.lives, lives - 1)  # left through the top: one drop
        run(self.app, int(4.0 / DT))
        self.assertEqual(p.w.gflip, 1)

    def test_flip_back_mid_flight_counts_once(self):
        p = self.p
        c = p.w.throw("chaos", 640, 300, 0, 0, static=True)
        p.hit(c, (540, 300, 740, 300))
        run(self.app, int(4.8 / DT))
        f = p.w.throw("apple", 640, 300, 0, -500)  # rising toward the top just before gravity flips back
        f.entered = True
        run(self.app, int(0.4 / DT))
        self.assertEqual(p.w.gflip, 1); self.assertTrue(f.alive)  # turned around on screen: no drop yet
        self.assertEqual(p.lives, 3)
        run(self.app, int(3.0 / DT))
        self.assertFalse(f.alive)
        self.assertEqual(p.lives, 2)

    def test_special_drops_cost_nothing(self):
        p = self.p
        for kind in ("golden", "chaos", "icebomb"):
            b = p.w.throw(kind, 640, 650, 0, 200)
            b.entered = True
        run(self.app, 60)
        self.assertEqual(p.lives, 3)
        self.assertFalse(p.w.bodies)

    def test_ice_bomb_is_not_a_bomb(self):
        b = self.p.w.throw("icebomb", 640, 300, 0, 0, static=True)
        self.assertFalse(b.bomb); self.assertEqual(b.hazard, "ice")

    def test_flipped_waves_launch_from_the_top(self):
        p = self.p
        c = p.w.throw("chaos", 640, 300, 0, 0, static=True)
        p.hit(c, (540, 300, 740, 300))
        p.launch("apple", 640)
        b = p.w.bodies[-1]
        self.assertLess(b.y, 0); self.assertGreater(b.vy, 0)

    def test_classic_waves_have_no_hazards(self):
        app = self.app
        app.go(lambda: game.Play(app, "classic")); p = app.scene
        p.elapsed = 100
        for _ in range(200):
            p.wave()
        self.assertFalse({q[1] for q in p.queue} & {"shuriken", "icebomb", "golden", "chaos"})
