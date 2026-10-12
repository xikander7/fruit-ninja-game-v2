import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NINJA_NO_GPU", "1")

import pygame

from ninja import art, game
from ninja.art import Art, FRUITS

ROOT = Path(__file__).resolve().parent.parent


def load_build_sprites():
    spec = importlib.util.spec_from_file_location("build_sprites", ROOT / "tools" / "build_sprites.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class SplashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_splash_sprites_load_with_alpha(self):
        a = Art()
        self.assertEqual(len(a.splashes), 4)
        self.assertEqual(a.splash_dirs[0], None)  # burst1: the radial crown
        for img in a.splashes:
            self.assertTrue(img.get_flags() & pygame.SRCALPHA)
            self.assertEqual(max(img.get_size()), 300)
            alphas = pygame.image.tobytes(img, "RGBA")[3::4]
            self.assertEqual(min(alphas), 0)  # the black studio background keyed out
            self.assertGreaterEqual(max(alphas), 250)  # the milk body is opaque (smoothscale rounds 255 down a hair)

    def test_black_keys_to_transparent(self):
        bs = load_build_sprites()
        src = pygame.Surface((4, 1))
        for x, c in enumerate(((0, 0, 0), (12, 12, 12), (100, 100, 100), (255, 255, 255))):
            src.set_at((x, 0), c)
        out = bs.key_splash(src)
        self.assertTrue(out.get_flags() & pygame.SRCALPHA)
        self.assertEqual(tuple(out.get_at((0, 0))), (0, 0, 0, 0))
        self.assertEqual(out.get_at((1, 0)).a, 0)
        self.assertEqual(tuple(out.get_at((2, 0))), (100, 100, 100, round(88 * 1.6)))
        self.assertEqual(tuple(out.get_at((3, 0))), (255, 255, 255, 255))

    def test_tinted_splash_is_cached_per_colour_and_step(self):
        a = Art()
        red = a.splash(1, (225, 35, 55), 31)
        self.assertIs(a.splash(1, (225, 35, 55), 29), red)  # both snap to 30 deg
        self.assertIsNot(a.splash(1, (140, 210, 60), 30), red)
        flat = a.splash(1, (225, 35, 55))
        c = flat.get_at(flat.get_rect().center)
        self.assertGreaterEqual(c.r, c.g)  # tinted toward the juice colour, not left white
        self.assertGreater(c.r, c.b)


class SplashCutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_save = game.SAVE_PATH
        game.SAVE_PATH = Path(self.tmp.name) / "save.json"
        self.app = game.App()

    def tearDown(self):
        game.SAVE_PATH = self.old_save
        pygame.quit()
        self.tmp.cleanup()

    def cut_one(self):
        w = game.World(self.app)
        w.particles.items = []  # drop the ambient dust so only the cut's particles remain
        b = w.throw("orange", 640, 360, 0, 0)
        w.cut(b, 560, 330, 720, 390)
        kinds = [p.kind for p in w.particles.items]
        return kinds.count("splash"), kinds.count("drop")

    def test_cut_spawns_one_splash(self):
        splashes, drops = self.cut_one()
        self.assertEqual(splashes, 1)
        self.assertEqual(drops, 10 + 35 // 2 + 24)  # heavy drops kept, fine spray halved, both fans kept

    def test_no_splash_without_sprites(self):
        self.app.art.splashes, self.app.art.splash_dirs = [], []
        splashes, drops = self.cut_one()
        self.assertEqual(splashes, 0)
        self.assertEqual(drops, 10 + 35 + 24)  # the full spray as before


if __name__ == "__main__":
    unittest.main()
