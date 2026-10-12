import os, tempfile, unittest
from pathlib import Path
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game
from ninja.boss import Boss, BossDirector

DT = 1 / 60
def run(app, n):
    for _ in range(n): app.step(DT, [])

class BossLogic(unittest.TestCase):
    def setUp(self):
        pygame.display.set_mode((1, 1))
        from ninja.art import Art
        self.art = Art()

    def test_hit_cooldown_and_death(self):
        b = Boss(self.art, "durian"); b.update(1.3)  # into hover
        self.assertTrue(b.hit(0.0)); self.assertFalse(b.hit(0.03)); self.assertTrue(b.hit(0.07))
        t = 0.07
        while b.hp > 0:
            t += 0.07; b.hit(t)
        self.assertEqual(b.phase, "dead")

    def test_escapes_after_hover(self):
        b = Boss(self.art, "pineapple")
        for _ in range(int(10.5 / DT)): b.update(DT)
        self.assertTrue(b.done); self.assertGreater(b.hp, 0)

    def test_director_timing_and_alternation(self):
        d = BossDirector(first_at=45.0, every=45.0)
        self.assertIsNone(d.update(44.0, None))
        first = d.update(45.0, None); self.assertEqual(first.name, "durian")
        first.done = True; d.update(50.0, None)
        self.assertIsNone(d.update(94.0, None))
        self.assertEqual(d.update(95.1, None).name, "pineapple")

class BossInPlay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App(); self.app.go(lambda: game.Play(self.app, "path")); self.p = self.app.scene
        run(self.app, 80)

    def tearDown(self):
        pygame.quit(); self.tmp.cleanup()

    def test_defeat_scores_and_bursts(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 90)
        boss = p.boss.active; self.assertIsNotNone(boss)
        score0 = p.score
        # the brief swung +-200 px (400 px jumps), but App drops any motion over MAX_JUMP (350) as the cursor
        # re-entering the window, so those swipes never cut; +-150 px is the same swipe through the boss, in reach
        for i in range(40):
            self.app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=(boss.x - 150 + (i % 2) * 300, boss.y), rel=(0, 0), buttons=(0, 0, 0))])
            if boss.phase == "dead": break
            run(self.app, 4)
        self.assertEqual(boss.phase, "dead")
        self.assertGreaterEqual(p.score - score0, 30 + 50)

    def test_game_over_with_boss_on_screen(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 90)
        self.assertIsNotNone(p.boss.active)
        for _ in range(3): p.lose_life(640, "test")
        run(self.app, 200)
        self.assertIsInstance(self.app.scene, game.GameOver)

    def test_run_end_removes_boss_and_waves_never_resume(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 90)
        boss = p.boss.active
        waves = []
        p.wave = lambda: waves.append(p.elapsed)
        run(self.app, 120)
        self.assertEqual(waves, [])  # paused while the boss is up
        for _ in range(3): p.lose_life(640, "test")
        run(self.app, 2)
        self.assertIsNone(p.boss.active)
        self.assertTrue(p.boss.pause_waves)
        self.assertFalse(boss.hit(self.app.now + 1))  # leaving: no longer hittable
        p.state = "play"  # even if play somehow went on, no boss and no wave would come back
        p.elapsed, p.spawn_t = 200.0, 0.0
        run(self.app, 30)
        self.assertIsNone(p.boss.active)
        self.assertEqual(waves, [])

    def test_time_stop_holds_the_boss(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 30)
        boss = p.boss.active
        p.ki.value = 100; p.use_power("timestop")
        run(self.app, 2)
        t, y, hp = boss.t, boss.y, boss.hp
        for i in range(30):  # swipes through the frozen boss do nothing; it doesn't move
            self.app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=(boss.x - 150 + (i % 2) * 300, boss.y), rel=(0, 0), buttons=(0, 0, 0))])
        self.assertEqual((boss.t, boss.y, boss.hp), (t, y, hp))

    def test_other_modes_have_no_boss(self):
        for mode in ("classic", "arcade", "zen"):
            self.assertIsNone(game.Play(self.app, mode).boss)

    def test_hits_tally_into_one_counter_and_the_seal_waits_for_the_burst(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 90)
        boss = p.boss.active
        pops = len(p.w.popups.items)
        for i in range(60):
            self.app.step(DT, [pygame.event.Event(pygame.MOUSEMOTION, pos=(boss.x - 150 + (i % 2) * 300, boss.y), rel=(0, 0), buttons=(0, 0, 0))])
            if boss.phase == "dead": break
            if i == 5:
                self.assertGreaterEqual(boss.tally, 5)
                self.assertEqual(len(p.w.popups.items), pops)  # no popup per hit
            run(self.app, 4)
        self.assertEqual(boss.phase, "dead")
        kill = p.app.art.seal("討", 140)
        self.assertFalse(any(s.seal is kill for s in p.w.stamps))  # not on top of the burst
        run(self.app, 30)
        seal = [s for s in p.w.stamps if s.seal is kill]
        self.assertEqual(len(seal), 1)
