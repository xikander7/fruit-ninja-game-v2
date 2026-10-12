# Fruit Ninja · Night Dojo

A fruit-slicing arcade game in Python (pygame-ce). All art and sound are generated in code at startup, so there are no asset files.

```
pip install -r requirements.txt
python main.py
```

**Play:** hold the left mouse button and swipe. Slice a fruit on the menu to pick a mode.

| Mode | Rules |
|------|-------|
| Classic | 3 strikes for dropped fruit; a bomb ends the run; +1 life every 100 points |
| Arcade | 60 s; bombs cost 10; power bananas: Freeze (slow-mo), Frenzy (fruit storm), Double score; random criticals |
| Zen | 90 s, no bombs |

Slice 3+ fruit in one swipe for a combo bonus. Higher best scores unlock new blades (←/→ or mouse wheel on the menu).
Keys: `1/2/3` quick start · `Esc`/`P` pause · `M` mute · `F11` fullscreen.

Scores are saved to `~/.fruit_ninja_dojo.json`. Tests: `python -m unittest tests.test_game`.

The original browser version (`index.html`, `script.js`, `style.css`) is still in the repo.
