import unittest
from ninja.fever import Fever, CHAIN_STEP, MAX_MULT, FEVER_TIME

class FeverLogic(unittest.TestCase):
    def test_mult_steps_every_ten(self):
        f = Fever()
        for _ in range(CHAIN_STEP - 1): f.cut()
        self.assertEqual(f.mult, 1)
        f.cut(); self.assertEqual(f.mult, 2)
        self.assertEqual(f.points(3), 6)

    def test_reaching_max_starts_fever_then_resets(self):
        f = Fever()
        for _ in range(CHAIN_STEP * (MAX_MULT - 1)): f.cut()
        self.assertTrue(f.active); self.assertEqual(f.points(2), 10)
        f.update(FEVER_TIME + 0.01)
        self.assertFalse(f.active); self.assertEqual(f.mult, 1); self.assertEqual(f.chain, 0)

    def test_miss_resets(self):
        f = Fever()
        for _ in range(25): f.cut()
        f.reset(); self.assertEqual((f.chain, f.mult), (0, 1))

    def test_rain_only_during_fever(self):
        f = Fever()
        self.assertEqual(f.update(1.0), [])
        for _ in range(40): f.cut()
        self.assertGreaterEqual(len(f.update(0.5)), 3)
