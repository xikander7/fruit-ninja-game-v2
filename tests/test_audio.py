import os
import re
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from ninja import audio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def game_sound_names():
    """Every literal name passed to audio.play(...) anywhere in ninja/, plus the ones audio.py serves itself."""
    names = set()
    for fn in os.listdir(os.path.join(ROOT, "ninja")):
        if fn.endswith(".py"):
            with open(os.path.join(ROOT, "ninja", fn), encoding="utf-8") as f:
                names.update(re.findall(r"audio\.play\(\s*\"(\w+)\"", f.read()))
    return names | {"fuse", "music"}


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = game_sound_names()

    def check(self, a):
        if not a.ok:
            self.skipTest("no audio device")
        for n in self.names:
            self.assertTrue(a.s.get(n), f"no sound for {n!r}")
            a.play(n, 0.0)

    def test_names_found(self):
        self.assertGreaterEqual(len(self.names), 10)

    def test_every_game_sound_resolves_from_files(self):
        a = audio.Audio()
        self.check(a)
        # files really replaced the synthesis: swoosh has one variant per slash hit (>4 is the synth count)
        self.assertGreater(len(a.s["swoosh"]), 4)
        self.assertIn(a.music_snd, a.s["music"])

    def test_built_assets_present(self):
        wavs = os.listdir(os.path.join(ROOT, "assets", "audio"))
        for prefix in audio.GROUPS:
            self.assertTrue(any(w.startswith(prefix) for w in wavs), prefix)

    def test_synth_fallback_with_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            a = audio.Audio(d)
            self.check(a)
            self.assertEqual(len(a.s["swoosh"]), 4)  # the synthesized set

    def test_missing_dir_falls_back(self):
        a = audio.Audio(os.path.join(ROOT, "nope"))
        self.check(a)

    def test_play_volume_variation_stays_valid(self):
        a = audio.Audio()
        if not a.ok:
            self.skipTest("no audio device")
        for _ in range(20):
            a.play("splat", 1.0)  # min(1.0, ...) clamp: set_volume raises/clamps outside 0..1
        a.fuse(True)
        a.fuse(False)
        a.start_music()
        a.toggle_mute()
        a.toggle_mute()


if __name__ == "__main__":
    unittest.main()
