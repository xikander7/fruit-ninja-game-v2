"""Shareable editions: asset paths resolve inside a PyInstaller bundle; the browser build's frame step and save."""
import sys
import unittest
from pathlib import Path

from ninja import settings


class ResourcePath(unittest.TestCase):
    def test_repo_mode(self):
        self.assertTrue(settings.resource_path("assets", "fonts").is_dir())

    def test_frozen_mode(self):
        sys._MEIPASS = "C:/bundle"
        try:
            self.assertEqual(settings.resource_path("assets", "x.png"), Path("C:/bundle/assets/x.png"))
        finally:
            del sys._MEIPASS


if __name__ == "__main__":
    unittest.main()
