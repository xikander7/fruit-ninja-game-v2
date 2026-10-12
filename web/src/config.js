// Constants shared by every module. Mirrors ninja/settings.py and the FRUITS table in ninja/art.py.
export const W = 1280, H = 720; // the stage: all game rules work in these coordinates
export const GRAVITY = 1250;
export const SLICE_SPEED = 300; // px/s: just moving the pointer slices; a slow drift doesn't
export const MAX_JUMP = 350; // px in one motion event

// The view is the stage plus whatever extra wall the window's shape shows around it (set by app.resize).
export const VIEW = { w: W, h: H, ox: 0, oy: 0 };
export const viewLeft = () => -VIEW.ox;
export const viewRight = () => W + VIEW.ox;

export const INK = [10, 8, 8];
export const WASHI = [236, 228, 210];
export const GOLD = [226, 182, 92];
export const HANKO = [196, 40, 36];
export const STEEL = [190, 215, 235];
export const MUTED = [150, 138, 120];

export const TITLE = "Hanifa";
export const SUBTITLE = "THE FRUIT NINJA";

// name: [outer glow, mid, core, unlock score]
export const BLADES = {
  "Moonlight": [[40, 90, 170], [120, 190, 255], [255, 255, 255], 0],
  "Sakura": [[170, 40, 100], [255, 140, 195], [255, 240, 248], 100],
  "Ember": [[190, 50, 0], [255, 140, 30], [255, 240, 190], 250],
  "Gold Leaf": [[150, 100, 0], [255, 205, 70], [255, 255, 225], 500],
};

export const MODES = {
  classic: { title: "Classic", glyph: "斬", hint: "3 strikes · bombs end it" },
  arcade: { title: "Arcade", glyph: "速", hint: "60 seconds · power bananas" },
  zen: { title: "Zen", glyph: "禅", hint: "90 seconds · no bombs" },
  path: { title: "Ninja Path", glyph: "道", hint: "Endless · powers · bosses" },
};
// which systems each mode runs; every hook is a no-op when its flag is off
export const MODE_FEATURES = {
  classic: [], zen: [], arcade: ["powers", "fever"], path: ["powers", "fever", "boss", "hazards"],
};

// name, radius, juice colour, points, special
const F = (name, r, juice, points = 1, special = "") => ({ name, r, juice, points, special });
export const FRUITS = {
  watermelon: F("watermelon", 56, [225, 35, 55]),
  coconut: F("coconut", 44, [240, 240, 235]),
  orange: F("orange", 40, [255, 150, 30]),
  peach: F("peach", 38, [255, 170, 60]),
  apple: F("apple", 38, [255, 240, 200]),
  dragonfruit: F("dragonfruit", 40, [250, 120, 190], 3),
  lemon: F("lemon", 34, [250, 235, 90]),
  kiwi: F("kiwi", 34, [140, 210, 60]),
  plum: F("plum", 31, [170, 50, 120]),
  strawberry: F("strawberry", 30, [240, 40, 60]),
  banana: F("banana", 44, [255, 240, 180]),
  freeze: F("freeze", 44, [160, 220, 255], 1, "freeze"),
  frenzy: F("frenzy", 44, [255, 120, 50], 1, "frenzy"),
  double: F("double", 44, [255, 210, 60], 1, "double"),
  // only ever spawned by hazards (golden rain, chaos), never by the normal waves
  golden: F("golden", 40, [255, 210, 60], 5),
  chaos: F("chaos", 36, [170, 90, 255]),
};
export const REGULAR = ["watermelon", "coconut", "orange", "peach", "apple", "lemon", "kiwi", "plum", "strawberry", "banana", "dragonfruit"];
export const WEIGHTS = [10, 6, 12, 9, 12, 9, 9, 8, 9, 6, 3];
export const SPECIALS = ["freeze", "frenzy", "double"];
export const BOSS_R = 120;
