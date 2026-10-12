import os, tempfile, unittest
from pathlib import Path
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game
from ninja.powers import KiMeter, KI_MAX, KI_PER_CUT

DT = 1 / 60
def run(app, n, events=()):
    for _ in range(n):
        app.step(DT, list(events))
def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)
def move(app, p):
    app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=p, rel=(0, 0), buttons=(0, 0, 0))])
def rclick():
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(640, 360), button=3)

class Ki(unittest.TestCase):
    def test_fill_clamp_spend_lock(self):
        k = KiMeter()
        for _ in range(30): k.add(4)
        self.assertEqual(k.value, KI_MAX); self.assertTrue(k.full)
        k.locked = True; k.spend(); k.add(50)
        self.assertEqual(k.value, 0)

class Powers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()
        self.app.go(lambda: game.Play(self.app, "path"))
        self.p = self.app.scene
        run(self.app, 80)  # past "ready"

    def tearDown(self):
        pygame.quit(); self.tmp.cleanup()

    def test_no_power_without_full_meter_or_when_paused(self):
        p = self.p
        self.assertFalse(p.use_power("timestop"))
        p.ki.value = KI_MAX; p.paused = True
        run(self.app, 1, [key(pygame.K_w)])
        self.assertIsNone(p.power); self.assertEqual(p.ki.value, KI_MAX)

    def test_classic_has_no_ki(self):
        self.app.go(lambda: game.Play(self.app, "classic"))
        self.assertIsNone(self.app.scene.ki)

    def test_timestop_freezes_world_and_cuts_touched_in_order(self):
        p, app = self.p, self.app
        p.queue.clear(); p.spawn_t = 99
        a = p.w.throw("apple", 400, 360, 0, 0, static=True)
        b = p.w.throw("orange", 800, 360, 0, 0, static=True)
        c = p.w.throw("kiwi", 640, 120, 0, 0, static=True)  # not on the path
        p.ki.value = KI_MAX
        run(app, 1, [key(pygame.K_q)])
        self.assertEqual(p.power.name, "timestop")
        self.assertEqual(p.w.time_scale(), 0.0)
        for x in range(300, 901, 25):
            move(app, (x, 360))
        self.assertTrue(a.alive and b.alive)   # nothing cut while time is stopped
        run(app, int(3.2 / DT) + 10)
        self.assertFalse(a.alive); self.assertFalse(b.alive); self.assertTrue(c.alive)
        self.assertIsNone(p.power)

    def test_timestop_empty_path_ends_cleanly(self):
        p, app = self.p, self.app
        p.ki.value = KI_MAX
        run(app, 1, [key(pygame.K_q)])
        run(app, int(3.5 / DT))
        self.assertIsNone(p.power); self.assertEqual(p.ki.value, 0)

    def test_clones_cut_fruit_never_bombs(self):
        p, app = self.p, self.app
        p.queue.clear(); p.spawn_t = 99
        f = p.w.throw("apple", 500, 300, 0, 0, static=True)
        bomb = p.w.throw("bomb", 800, 300, 0, 0, static=True)
        p.ki.value = KI_MAX
        run(app, 1, [key(pygame.K_w)])
        run(app, int(5.2 / DT))
        self.assertFalse(f.alive); self.assertTrue(bomb.alive)

    def test_dragonfire_chain_within_radius_only(self):
        p, app = self.p, self.app
        p.queue.clear(); p.spawn_t = 99
        first = p.w.throw("apple", 400, 300, 0, 0, static=True)
        near = p.w.throw("orange", 520, 300, 0, 0, static=True)   # 120 px away -> ignites
        far = p.w.throw("kiwi", 900, 300, 0, 0, static=True)      # 380 px away -> stays
        p.ki.value = KI_MAX
        run(app, 1, [key(pygame.K_e)])
        p.hit(first, (300, 300, 450, 300))
        run(app, 30)
        self.assertFalse(near.alive); self.assertTrue(far.alive)

    # --- review focus 1 and 2 ---
    def test_no_power_in_ready_dying_or_ending(self):
        p = self.p
        for state in ("ready", "dying", "ending"):
            p.state, p.ki.value = state, KI_MAX
            run(self.app, 1, [key(pygame.K_e), rclick()])
            self.assertIsNone(p.power, state); self.assertEqual(p.ki.value, KI_MAX, state)

    def test_q_while_paused_still_quits_to_menu(self):
        p = self.p
        p.ki.value = KI_MAX; p.paused = True
        run(self.app, 1, [key(pygame.K_q)])
        self.assertIsInstance(self.app.scene, game.Menu); self.assertEqual(p.ki.value, KI_MAX)

    def test_right_click_uses_last_power(self):
        p = self.p
        p.ki.value = KI_MAX
        run(self.app, 1, [rclick()])
        self.assertEqual(p.power.name, "timestop")
        p.power = None; p.ki.locked = False; p.last_power = "clones"; p.ki.value = KI_MAX
        run(self.app, 1, [rclick()])
        self.assertEqual(p.power.name, "clones")

    def test_timestop_path_over_bomb_only_costs_a_life_and_ends(self):
        p, app = self.p, self.app
        p.queue.clear(); p.spawn_t = 99
        bomb = p.w.throw("bomb", 640, 360, 0, 0, static=True)
        p.ki.value = KI_MAX
        run(app, 1, [key(pygame.K_q)])
        for x in range(500, 801, 25):
            move(app, (x, 360))
        run(app, int(3.3 / DT))
        self.assertFalse(bomb.alive); self.assertEqual(p.lives, 2)
        self.assertIsNone(p.power); self.assertEqual(p.ki.value, 0); self.assertFalse(p.ki.locked)

    def test_cuts_fill_ki_but_not_while_a_power_runs(self):
        p = self.p
        p.queue.clear(); p.spawn_t = 99
        p.hit(p.w.throw("apple", 400, 300, 0, 0, static=True), (300, 300, 500, 300))
        self.assertEqual(p.ki.value, KI_PER_CUT)
        p.ki.value = KI_MAX
        self.assertTrue(p.use_power("clones"))
        p.hit(p.w.throw("apple", 400, 500, 0, 0, static=True), (300, 500, 500, 500))
        self.assertEqual(p.ki.value, 0)
