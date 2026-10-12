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

    def test_shock_displaces_pixels_near_the_ring_only(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        for x in range(0, W, 8):  # fine vertical stripes: any horizontal displacement changes pixels
            base.fill((255, 255, 255), (x, 0, 3, H))
        self.fx.time = 0.0
        plain = self.render(base, emissive)
        self.fx.time = 0.0  # same grain
        shocked = self.render(base, emissive, {"shocks": [(0.5, 0.5, 0.2, 0.04)]})

        def diff(x0, x1):
            return sum(abs(plain.get_at((x, H // 2))[0] - shocked.get_at((x, H // 2))[0]) for x in range(x0, x1))

        ring = W // 2 + round(0.2 * H)  # radius is in units of screen height
        self.assertGreater(diff(ring - 40, ring + 40), 500)
        self.assertLess(diff(W // 2 + 320, W // 2 + 400), 50)  # well outside the ring: untouched
        self.assertLess(diff(W // 2 - 30, W // 2 + 30), 50)  # inside the ring: untouched

    def test_flash_brightens(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((60, 60, 60))
        self.fx.time = 0.0
        off = self.render(base, emissive).get_at((W // 2, H // 2))
        self.fx.time = 0.0
        on = self.render(base, emissive, {"flash": 0.5}).get_at((W // 2, H // 2))
        for a, b in zip(off[:3], on[:3]):
            self.assertGreater(b, a + 100)

    def test_image_is_not_upside_down(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((255, 255, 255), (W // 2 - 10, 100, 20, 20))  # near the top in pygame coords
        out = self.render(base, emissive)
        self.assertGreater(out.get_at((W // 2, 110))[0], 150)
        self.assertLess(out.get_at((W // 2, H - 110))[0], 30)


    def render_ui(self, base, emissive, params, ui):
        self.fx.render(base, emissive, params, VIEW, target=self.fbo, ui=ui)
        img = pygame.image.frombytes(self.fbo.read(components=3), (W, H), "RGB")
        return pygame.transform.flip(img, False, True)

    def test_ui_layer_skips_every_post_effect(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        base.fill((90, 90, 90))
        base.fill((255, 255, 255), (W // 2 + 200 - 3, H // 2 - 3, 6, 6))  # a world marker, for contrast
        ui = pygame.Surface((W, H), pygame.SRCALPHA)
        ui.fill((200, 40, 40, 255), (60, 40, 30, 20))  # a HUD marker in the corner, where vignette and fringes peak
        harsh = {"zoom": 1.2, "aberration": 0.05, "saturation": 0.2, "flash": 0.3,
                 "shocks": [(0.06, 0.07, 0.03, 0.04)]}
        self.fx.time = 0.0
        out = self.render_ui(base, emissive, harsh, ui)
        for x, y in ((60, 40), (89, 59), (75, 50)):  # exactly in place, exactly its colour: no grade, no grain
            self.assertEqual(tuple(out.get_at((x, y)))[:3], (200, 40, 40))
        self.fx.time = 0.0
        bare = self.render_ui(base, emissive, harsh, None)
        for x, y in ((58, 50), (92, 50), (75, 37), (75, 62)):  # just outside: the marker leaves no fringe
            self.assertEqual(out.get_at((x, y)), bare.get_at((x, y)))
        # meanwhile the world marker did move with the zoom
        row = [bare.get_at((x, H // 2))[0] for x in range(W // 2, W)]
        self.assertGreater(row.index(max(row)), 220)

    def test_half_transparent_ui_is_premultiplied_alpha_over(self):
        base, emissive = pygame.Surface((W, H)), pygame.Surface((W, H))
        ui = pygame.Surface((W, H), pygame.SRCALPHA)
        ui.fill((128, 128, 128, 128))  # premultiplied: white at half coverage
        self.fx.time = 0.0
        r, g, b, _ = self.render_ui(base, emissive, {}, ui).get_at((W // 2, H // 2))
        for c in (r, g, b):
            self.assertAlmostEqual(c, 128, delta=4)


@unittest.skipIf(CTX is None, "no standalone OpenGL context")
class Lifetime(unittest.TestCase):
    def test_release_frees_a_context_it_created_but_not_a_borrowed_one(self):
        from unittest import mock
        from ninja.gpu import PostFX
        own = moderngl.create_standalone_context()
        with mock.patch("moderngl.create_context", lambda: own):
            fx = PostFX()
        fx.release()
        CTX.__enter__()  # releasing a context leaves none current: make the shared test context current again
        self.assertEqual(type(own.mglo).__name__, "InvalidObject")
        borrowed = PostFX(CTX)
        borrowed.release()
        self.assertNotEqual(type(CTX.mglo).__name__, "InvalidObject")


@unittest.skipIf(CTX is None, "no moderngl")
class WindowMapping(unittest.TestCase):
    def test_letterbox_and_to_logical(self):
        from ninja.gpu import letterbox, to_logical
        self.assertEqual(letterbox(0, 0, W, H), (0, 0, W, H))
        self.assertEqual(letterbox(0, 0, 2560, 1080), (320, 0, 1920, 1080))  # wider: pillarbox bars left/right
        self.assertEqual(letterbox(0, 0, 1280, 1024), (0, 152, 1280, 720))  # taller: letterbox bars top/bottom
        cases = [((W, H), (640, 360), (640, 360)),
                 ((2560, 1080), (320, 0), (0, 0)), ((2560, 1080), (2240, 1080), (W, H)),
                 ((2560, 1080), (1280, 540), (640, 360)), ((2560, 1080), (100, 540), (-146.67, 360)),
                 ((1280, 1024), (0, 152), (0, 0)), ((1280, 1024), (640, 512), (640, 360)),
                 ((1280, 1024), (1280, 872), (W, H))]
        for size, pos, want in cases:
            got = to_logical(pos, size)
            self.assertAlmostEqual(got[0], want[0], delta=0.01, msg=(size, pos))
            self.assertAlmostEqual(got[1], want[1], delta=0.01, msg=(size, pos))


if __name__ == "__main__":
    unittest.main()
