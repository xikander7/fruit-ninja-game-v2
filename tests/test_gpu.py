"""PostFX checks against a standalone GL context, read back from an offscreen framebuffer."""
import os
import unittest

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame  # noqa: E402

try:
    import moderngl
    CTX = moderngl.create_standalone_context()
except Exception:  # no moderngl or no GL 3.3 on this machine
    CTX = None

from ninja.settings import W, H  # noqa: E402

VIEW = (0, 0, W, H)


@unittest.skipIf(CTX is None, "no standalone OpenGL context")
class PostFXRender(unittest.TestCase):
    def setUp(self):
        from ninja.gpu import PostFX
        self.fx = PostFX(CTX)
        self.fbo = CTX.simple_framebuffer((W, H), components=3)

    def tearDown(self):
        self.fx.release()
        self.fbo.release()

    def render(self, base, emissive, params=None):
        self.fx.render(base, emissive, params or {}, VIEW, target=self.fbo)
        img = pygame.image.frombytes(self.fbo.read(components=3), (W, H), "RGB")
        return pygame.transform.flip(img, False, True)  # GL rows are bottom-up; back to screen coords

    def test_bloom_spreads_but_corners_stay_dark(self):
        base, lit, unlit = pygame.Surface((W, H)), pygame.Surface((W, H)), pygame.Surface((W, H))
        lit.fill((255, 255, 255), (W // 2 - 4, H // 2 - 4, 8, 8))
        self.fx.time = 0.0
        on = self.render(base, lit)
        self.fx.time = 0.0  # same grain pattern, so any difference is bloom
        off = self.render(base, unlit)

        def patch(img, x, y):  # 5x5 mean, so one grain speck can't decide the result
            return sum(img.get_at((x + i, y + j))[0] for i in range(-2, 3) for j in range(-2, 3)) / 25

        x, y = W // 2 + 4 + 20, H // 2  # 20 px right of the square
        self.assertGreater(on.get_at((x, y))[0], 0)
        self.assertGreater(patch(on, x, y), patch(off, x, y) + 0.5)
        self.assertLess(on.get_at((2, 2))[0], 30)

    def test_mid_grey_survives_tonemap(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((128, 128, 128))
        r, g, b, _ = self.render(base, emissive).get_at((W // 2, H // 2))
        for c in (r, g, b):
            self.assertAlmostEqual(c, 128, delta=12)

    def test_zoom_moves_marker_outward(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((255, 255, 255), (W // 2 + 200 - 3, H // 2 - 3, 6, 6))  # marker 200 px right of centre

        def marker_x(params):
            out = self.render(base, emissive, params)
            row = [out.get_at((x, H // 2))[0] for x in range(W // 2, W)]
            return W // 2 + row.index(max(row))

        self.assertAlmostEqual(marker_x({}), W // 2 + 200, delta=3)
        self.assertAlmostEqual(marker_x({"zoom": 1.2}), W // 2 + 240, delta=4)

    def test_image_is_not_upside_down(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((255, 255, 255), (W // 2 - 10, 100, 20, 20))  # near the top in pygame coords
        out = self.render(base, emissive)
        self.assertGreater(out.get_at((W // 2, 110))[0], 150)
        self.assertLess(out.get_at((W // 2, H - 110))[0], 30)


if __name__ == "__main__":
    unittest.main()
