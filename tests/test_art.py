import os
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from ninja import art
from ninja.art import Art, FRUITS


class SpriteArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_loaded_sprites_have_alpha_and_size(self):
        a = Art()
        for name, ft in FRUITS.items():
            fa = a.fruits[name]
            for surf in (fa.whole, fa.half):
                self.assertTrue(surf.get_flags() & pygame.SRCALPHA, name)
            self.assertEqual(fa.half_local, 270, name)
            longer = max(fa.whole.get_size())
            self.assertLessEqual(abs(longer - 2.35 * ft.r), 3, name)
        self.assertEqual(a.bg.get_size(), (1280, 720))
        self.assertLess(a.bomb_tip[1], 0)  # fuse end is above the centre

    def test_procedural_fallback_when_sprites_missing(self):
        old = art.SPRITE_DIR
        with tempfile.TemporaryDirectory() as d:
            art.SPRITE_DIR = d
            try:
                a = Art()
            finally:
                art.SPRITE_DIR = old
        self.assertEqual(set(a.fruits), set(FRUITS))
        self.assertEqual(a.fruits["apple"].half_local, 90)
        self.assertEqual(a.bg.get_size(), (1280, 720))


if __name__ == "__main__":
    unittest.main()
