"""Boss tests: the boss's own rules (hits, cooldown, escape, timing) and how a boss behaves
inside a real game (scoring, game over, Time Stop)."""
import os, tempfile, unittest
from pathlib import Path
# Run without a window, sound card or GPU so the tests work on any machine (including a build server).
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"; os.environ["NINJA_NO_GPU"] = "1"
import pygame
from ninja import game
from ninja.boss import Boss, BossDirector

# One frame at 60 frames per second, in seconds.
DT = 1 / 60
def run(app, n):
    """Advance the game n frames with no input."""
    for _ in range(n): app.step(DT, [])

class BossLogic(unittest.TestCase):
    """The Boss and BossDirector rules on their own, with no game around them."""
    def setUp(self):
        """Make a tiny hidden window and load the art the bosses need."""
        pygame.display.set_mode((1, 1))
        from ninja.art import Art
        self.art = Art()

    # Proves: hits closer than the cooldown don't count, and the boss dies when its health runs out.
    def test_hit_cooldown_and_death(self):
        b = Boss(self.art, "durian"); b.update(1.3)  # into hover
        self.assertTrue(b.hit(0.0)); self.assertFalse(b.hit(0.03)); self.assertTrue(b.hit(0.07))
        t = 0.07
        while b.hp > 0:
            t += 0.07; b.hit(t)
        self.assertEqual(b.phase, "dead")

    # Proves: a boss left alone flees after its hover time, still alive.
    def test_escapes_after_hover(self):
        b = Boss(self.art, "pineapple")
        for _ in range(int(10.5 / DT)): b.update(DT)
        self.assertTrue(b.done); self.assertGreater(b.hp, 0)

    # Proves: the first boss (durian) arrives at 45 s, and the next one (pineapple) comes 45 s after it ends.
    def test_director_timing_and_alternation(self):
        d = BossDirector(first_at=45.0, every=45.0)
        self.assertIsNone(d.update(44.0, None))
        first = d.update(45.0, None); self.assertEqual(first.name, "durian")
        first.done = True; d.update(50.0, None)
        self.assertIsNone(d.update(94.0, None))
        self.assertEqual(d.update(95.1, None).name, "pineapple")

class BossInPlay(unittest.TestCase):
    """Bosses inside a real 'path' game, driven with simulated mouse swipes."""
    def setUp(self):
        """Use a throwaway save file, start a path game and play past the 'ready' countdown."""
        self.tmp = tempfile.TemporaryDirectory()
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App(); self.app.go(lambda: game.Play(self.app, "path")); self.p = self.app.scene
        run(self.app, 80)

    def tearDown(self):
        """Shut pygame down and delete the temporary save folder."""
        pygame.quit(); self.tmp.cleanup()

    # Proves: slicing a boss to death ends it and awards the kill points.
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

    # Proves: losing all lives while a boss is up still reaches the game-over screen.
    def test_game_over_with_boss_on_screen(self):
        p = self.p
        p.elapsed = 45.0; run(self.app, 90)
        self.assertIsNotNone(p.boss.active)
        for _ in range(3): p.lose_life(640, "test")
        run(self.app, 200)
        self.assertIsInstance(self.app.scene, game.GameOver)

    # Proves: waves pause during a boss, and once the run ends the boss leaves and no new wave starts.
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

    # Proves: the Time Stop power freezes the boss, so swipes through it do nothing.
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

    # Proves: only the 'path' mode has bosses.
    def test_other_modes_have_no_boss(self):
        for mode in ("classic", "arcade", "zen"):
            self.assertIsNone(game.Play(self.app, mode).boss)

    # Proves: boss hits add up in one counter (no popup per hit), and the kill seal appears after the burst.
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
