# Fruit Ninja · Night Dojo

A fruit-slicing arcade game in Python (pygame-ce), set on the wall of a lantern-lit dojo: photoreal fruit, juice
splashes, hanko seals for every big moment, and GPU post-processing (bloom, shockwaves, slow-mo grades).

```
pip install -r requirements.txt
python main.py
```

**Play:** move the mouse fast across a fruit to slice it. There's no clicking. On the menu, slice a fruit to pick a mode.

| Mode | Rules |
|------|-------|
| Classic | 3 strikes for dropped fruit; a bomb ends the run; +1 life every 100 points |
| Arcade | 60 s; bombs cost 10; power bananas: Freeze (slow-mo), Frenzy (fruit storm), Double score; random criticals |
| Zen | 90 s, no bombs |

Slice 3+ fruit in one swipe for a combo bonus. Higher best scores unlock new blades (←/→ or mouse wheel on the menu).

Keys: `1/2/3` quick start · `Esc`/`P` pause (`Q` while paused: back to menu) · `Enter`/`R`/`Space` retry and `Esc` menu
on the results screen · `M` mute · `F11` fullscreen.

Scores are saved to `~/.fruit_ninja_dojo.json`.

## Graphics

When moderngl and OpenGL 3.3 are available, the frame is post-processed on the GPU: bloom, a filmic tonemap,
vignette, grain, combo zoom punches, bomb shockwaves with chromatic aberration, and colour grades for slow-mo and
Freeze. The HUD is drawn on its own layer on top of all that, so it never warps. Without a GPU (or with
`NINJA_NO_GPU=1`) the game uses a CPU renderer that looks nearly the same.

## Assets and tools

- The sprites (fruit, bomb, background, juice splashes) are in `assets/sprites/` and the sound effects and music are
  in `assets/audio/`.
- The fonts (Cormorant SC, Barlow Condensed, IBM Plex Mono) are under the SIL Open Font License; the licences are in
  `assets/fonts/`.
- `tools/build_sprites.py` and `tools/build_audio.py` rebuild `assets/sprites/` and `assets/audio/` from the raw
  downloads in `assets/raw/`. That folder is git-ignored and not in the repo, so a fresh clone just uses the
  committed assets. `build_audio.py` needs numpy, which is a dev-only tool dependency, not a game dependency.

## Tests

```
python -m unittest discover -s tests
```

They run headless (SDL dummy driver, CPU renderer). The GPU tests use a standalone OpenGL context and are skipped
where none is available.

## Versions

- `main`: the original browser game (`index.html`, `script.js`, `style.css`, also kept in this tree).
- `feature/pygame-ninja`: v2, the first pygame version, with procedurally drawn art and synthesized sound.
- `feature/premium-ninja`: v3 (this one).
