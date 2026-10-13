import test from "node:test";
import assert from "node:assert/strict";
import * as assets from "../src/assets.js";

// Proves: short English seal labels receive a centered, size-bounded layout instead of relying on CJK images.
test("English seal labels fit one to five Latin characters", () => {
  assert.equal(typeof assets.latinSealLayout, "function");
  for (const label of ["H", "GO", "TRY", "MENU", "COMBO"]) {
    const layout = assets.latinSealLayout(label, 100);
    assert.equal(layout.text, label);
    assert.match(layout.font, /700 .*BarlowCondensed/);
    assert.ok(layout.px >= 18 && layout.px <= 58);
    assert.equal(layout.maxWidth, 78);
    assert.deepEqual([layout.x, layout.y], [50, 52]);
  }
});

// Proves: non-Latin labels do not accidentally enter the English text rendering path.
test("English seal layout rejects non-Latin text", () => {
  assert.equal(typeof assets.latinSealLayout, "function");
  assert.equal(assets.latinSealLayout("忍", 100), null);
  assert.equal(assets.latinSealLayout("TOO-LONG", 100), null);
});
