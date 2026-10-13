"""Fruit Slash entry point: run `python main.py` to start the desktop game.

All the real game code lives in the `ninja` package (see ninja/game.py). This file only starts it,
plus a tiny headless self-check (`smoke`) that the packaged .exe build uses to test itself.
"""
import os
import sys

from ninja.game import App


def smoke():
    """NINJA_SMOKE=1: run 180 frames, report which bundled assets loaded, exit (checks a packaged build)."""
    import pygame
    from ninja import art, audio as snd
    app = App()
    # Step the game 180 frames with no player, just to prove everything loads and runs.
    for _ in range(180):
        app.frame_step()
    fonts = "bundled" if art.LOADED["fonts"] else "fallback"
    audio = sum(len(v) for k, v in app.audio.s.items() if k in app.audio.files and k not in snd.ALIASES)  # files read
    line = (f"SMOKE OK sprites={art.LOADED['sprites']} fonts={fonts} audio={audio} "
            f"gpu={'yes' if app.gpu else 'no'} title={pygame.display.get_caption()[0]}")
    pygame.quit()
    if sys.stdout:  # a --noconsole .exe has no stdout: NINJA_SMOKE_LOG names a file instead
        print(line)
    if os.environ.get("NINJA_SMOKE_LOG"):
        with open(os.environ["NINJA_SMOKE_LOG"], "w", encoding="utf-8") as f:
            f.write(line + "\n")


# Program entry point: running `python main.py` starts the game.
# Setting NINJA_SMOKE=1 runs the quick self-check above instead (used to test packaged builds).
if __name__ == "__main__":
    if os.environ.get("NINJA_SMOKE") == "1":
        smoke()
    else:
        App().run()
