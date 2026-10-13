"""Audio tests: every sound the game asks for exists, whether it comes from the WAV files
or from the built-in synthesized fallback, and playing them never crashes."""
import os
import re
import tempfile
import unittest

# Run without a window, sound card or GPU so the tests work on any machine (including a build server).
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
    """Checks the sound system against the real files, against an empty folder and against a missing folder."""
    @classmethod
    def setUpClass(cls):
        """Collect the sound names the game uses once, up front."""
        cls.names = game_sound_names()

    def check(self, a):
        """Skip if there is no audio device; otherwise every game sound must exist and be playable (at zero volume)."""
        if not a.ok:
            self.skipTest("no audio device")
        for n in self.names:
            self.assertTrue(a.s.get(n), f"no sound for {n!r}")
            a.play(n, 0.0)

    # Proves: the scan of the code found a sensible number of sound names (so the other tests aren't empty).
    def test_names_found(self):
        self.assertGreaterEqual(len(self.names), 10)

    # Proves: the WAV files in assets/audio supply every sound, replacing the synthesized ones.
    def test_every_game_sound_resolves_from_files(self):
        a = audio.Audio()
        self.check(a)
        # files really replaced the synthesis: swoosh has one variant per slash hit (>4 is the synth count)
        self.assertGreater(len(a.s["swoosh"]), 4)
        self.assertIn(a.music_snd, a.s["music"])

    # Proves: the later-added power and boss sounds all exist.
    def test_new_sounds_resolve(self):
        a = audio.Audio()
        if not a.ok:
            self.skipTest("no audio device")
        for name in ("timestop", "clones", "dragonfire", "boss_hit", "boss_roar", "fever", "shuriken"):
            self.assertTrue(a.s.get(name), name)

    # Proves: those same sounds are synthesized when the audio folder is empty.
    def test_new_sound_fallbacks_with_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            a = audio.Audio(d)
            if not a.ok:
                self.skipTest("no audio device")
            for name in ("timestop", "clones", "dragonfire", "boss_hit", "boss_roar", "fever", "shuriken"):
                self.assertTrue(a.s.get(name), name)

    # Proves: each sound group has at least one built WAV file (run tools/build_audio.py if this fails).
    def test_built_assets_present(self):
        wavs = os.listdir(os.path.join(ROOT, "assets", "audio"))
        for prefix in audio.GROUPS:
            self.assertTrue(any(w.startswith(prefix) for w in wavs), prefix)

    # Proves: with no files the game falls back to its four synthesized swoosh sounds.
    def test_synth_fallback_with_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            a = audio.Audio(d)
            self.check(a)
            self.assertEqual(len(a.s["swoosh"]), 4)  # the synthesized set

    # Proves: a folder that doesn't exist at all is handled the same way, with no crash.
    def test_missing_dir_falls_back(self):
        a = audio.Audio(os.path.join(ROOT, "nope"))
        self.check(a)

    # Proves: random volume variation stays within 0..1, and fuse, music and mute can be toggled safely.
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

    # Proves: looping sounds (like fever) start, stop and survive muting, with real files and with the one-shot fallback.
    def test_loop_with_file_or_one_shot_fallback(self):
        for d in (None, os.path.join(ROOT, "nope")):  # real drum loop, then the one-shot fallback
            a = audio.Audio() if d is None else audio.Audio(d)
            if not a.ok:
                self.skipTest("no audio device")
            a.loop("fever", True); a.loop("fever", True)
            self.assertEqual(a.loop_name, "fever")
            a.quiet(); self.assertIsNone(a.loop_name)
            a.loop("fever", True); a.toggle_mute(); a.toggle_mute(); a.loop("fever", False)
            self.assertIsNone(a.loop_name)


if __name__ == "__main__":
    unittest.main()
