import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { BLADES, MODES } from "../src/config.js";
import { POWER_ORDER } from "../src/hud.js";
import { GLYPH_HEX } from "../src/assets.js";

const UI_MODULES = [
  "config.js", "title.js", "play.js", "gameover.js", "fever.js", "hazards.js",
  "hud.js", "powers.js", "boss.js", "rules/boss.js",
];

// Proves: no reachable browser UI module contains a CJK character that could appear on screen.
test("browser interface contains no Japanese characters", () => {
  for (const name of UI_MODULES) {
    const text = readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
    assert.doesNotMatch(text, /[\u3400-\u9fff\uf900-\ufaff]/u, name);
  }
});

// Proves: the main menu, blade picker and power buttons use the approved English labels.
test("browser interface uses English mode, blade and power labels", () => {
  assert.deepEqual(Object.values(MODES).map((mode) => [mode.title, mode.glyph]), [
    ["Classic", "C"], ["Arcade", "A"], ["Zen", "Z"], ["Hero Path", "H"],
  ]);
  assert.ok(Object.hasOwn(BLADES, "Petal Fan"));
  assert.deepEqual(POWER_ORDER, [["timestop", "STOP"], ["clones", "COPY"], ["dragonfire", "FIRE"]]);
  const hud = readFileSync(fileURLToPath(new URL("../src/hud.js", import.meta.url)), "utf8");
  assert.match(hud, /"POWER"/);
  assert.deepEqual(GLYPH_HEX, [], "Japanese glyph assets must not be loaded by the English-only build");
});
