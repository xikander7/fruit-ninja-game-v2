"""The desktop edition exposes English-only interface labels."""
import ast
from pathlib import Path

from ninja import powers, settings


ROOT = Path(__file__).resolve().parents[1]
UI_MODULES = (
    "ninja/settings.py", "ninja/title.py", "ninja/game.py", "ninja/fever.py",
    "ninja/hazards.py", "ninja/hud.py", "ninja/powers.py", "ninja/boss.py",
)


def test_desktop_interface_string_literals_contain_no_japanese_characters():
    for relative in UI_MODULES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        visible_strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert not [s for s in visible_strings if any("\u3400" <= c <= "\u9fff" for c in s)], relative


def test_desktop_interface_uses_approved_english_labels():
    assert [(m["title"], m["glyph"]) for m in settings.MODES.values()] == [
        ("Classic", "C"), ("Arcade", "A"), ("Zen", "Z"), ("Hero Path", "H")]
    assert "Petal Fan" in settings.BLADES
    assert powers.STAMPS == {
        "timestop": ("STOP", "Time stop"),
        "clones": ("COPY", "Shadow clones"),
        "dragonfire": ("FIRE", "Dragon fire"),
    }
    assert '"POWER"' in (ROOT / "ninja/hud.py").read_text(encoding="utf-8")
