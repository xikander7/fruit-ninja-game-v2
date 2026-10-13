// Tests for the web edition's game rules (web/src/rules/*.js): collision maths, Fever, the ki meter,
// saving, bosses and hazards. These are plain logic with no browser or graphics involved.
// Run them from the web folder with:  node --test tests/
import test from "node:test";
import assert from "node:assert/strict";
import { segHitsCircle, rotateVec, depthScale, flightTime } from "../src/rules/collide.js";
import { Fever, MAX_MULT, FEVER_TIME } from "../src/rules/fever.js";
import { KiMeter, KI_MAX } from "../src/rules/ki.js";
import { parseSave, loadSave, writeSave, defaultSave, SAVE_KEY } from "../src/rules/save.js";
import { Boss, BossDirector, HP, CRACK_AT, COOLDOWN, DEATH } from "../src/rules/boss.js";
import { rollHazard, Shuriken, HAZARDS_FROM, SHURIKEN_SPEED, PARRY_BOOST } from "../src/rules/hazards.js";
import { BLADES, SUBTITLE, TITLE } from "../src/config.js";
import { Menu } from "../src/menu.js";
import * as appModule from "../src/app.js";
import * as fxModule from "../src/fx.js";

// Proves: a mobile fullscreen request that never settles cannot hold the game on the decorative boot screen.
test("mobile startup does not wait for fullscreen", () => {
  const pendingFullscreen = new Promise(() => {});
  let starts = 0;
  const app = appModule.startImmediately?.(pendingFullscreen, () => { starts += 1; return "running"; });
  assert.equal(starts, 1);
  assert.equal(app, "running");
});

// Proves: selecting each blade produces a genuinely different cutting-tool geometry, not only another colour.
test("blade skins build four different tool models", () => {
  const expected = ["katana", "fan", "cleaver", "chakram"];
  const models = Object.values(BLADES).map((blade) => fxModule.bladeToolModel?.(blade[4], 0, 1600));
  assert.ok(models.every(Boolean));
  assert.deepEqual(models.map((model) => model.kind), expected);
  assert.equal(new Set(models.map((model) => model.parts.map((part) => part.kind).join(","))).size, 4);
});

// Proves: every cutting tool has visible motion rather than being a static recoloured cursor.
test("every blade tool animates while moving", () => {
  for (const style of ["katana", "fan", "cleaver", "chakram"]) {
    assert.notDeepEqual(fxModule.bladeToolModel(style, 0, 1600), fxModule.bladeToolModel(style, 0.23, 1600));
  }
});

// Proves: the browser game presents the approved name and supporting tagline.
test("branding uses Honey’s Slash & Splash", () => {
  assert.equal(TITLE, "Honey’s Slash & Splash");
  assert.equal(SUBTITLE, "FRUIT-SLICING ARCADE");
});

// Proves: a brand-new browser player can select every blade without earning a high score first.
test("all browser blades are available to a new player", () => {
  const menu = { app: { save: { best: { classic: 0, arcade: 0, zen: 0, path: 0 } } } };
  assert.deepEqual(Menu.prototype.unlocked.call(menu), Object.keys(BLADES));
});

// Proves: the blade-segment vs fruit-circle check handles hits, near misses, segment ends and zero-length segments.
test("segHitsCircle: through, near miss, endpoint, zero-length", () => {
  assert.ok(segHitsCircle(0, 0, 100, 0, 50, 5, 10));
  assert.ok(!segHitsCircle(0, 0, 100, 0, 50, 20, 10));
  assert.ok(segHitsCircle(0, 0, 100, 0, 105, 0, 6)); // past the end: nearest point is the endpoint
  assert.ok(!segHitsCircle(0, 0, 100, 0, 120, 0, 6));
  assert.ok(segHitsCircle(5, 5, 5, 5, 8, 5, 3)); // a zero-length segment is a point
});

// Proves: rotating a vector by 90 degrees turns it counter-clockwise on screen (y grows downward).
test("rotateVec turns counter-clockwise on screen", () => {
  const [x, y] = rotateVec(10, 0, 90);
  assert.ok(Math.abs(x) < 1e-9 && Math.abs(y + 10) < 1e-9); // pointing right -> pointing up (y negative)
});

// Proves: the fake-3D size swells at the top of a flight and is plain 1 when there is no flight.
test("depthScale swells at the apex and is 1 with no flight", () => {
  assert.equal(depthScale(0, null), 1);
  assert.ok(Math.abs(depthScale(0, 2) - 0.9) < 1e-9);
  assert.ok(Math.abs(depthScale(1, 2) - 1.04) < 1e-9);
  assert.equal(flightTime(-800, true), null);
  assert.ok(flightTime(-1250, false) >= 2); // 2 * 1250 / 1250
});

// Proves: the multiplier rises every 10 cuts in a row and Fever starts at the top multiplier (x5).
test("Fever: multiplier steps every 10 cuts and Fever starts at x5", () => {
  const f = new Fever();
  for (let i = 0; i < 9; i++) f.cut();
  assert.equal(f.mult, 1);
  f.cut();
  assert.equal(f.mult, 2);
  assert.equal(f.pop, 1);
  let started = false;
  for (let i = 0; i < 30; i++) started = f.cut() || started;
  assert.ok(started && f.active && f.mult === MAX_MULT);
  assert.equal(f.points(10), 50);
  assert.ok(Math.abs(f.t - FEVER_TIME) < 1e-9);
});

// Proves: Fever rains bonus fruit, freezes while time is stopped (dt 0), and fully resets when it ends.
test("Fever: rain, Time Stop (dt 0) and the end", () => {
  const f = new Fever();
  for (let i = 0; i < 40; i++) f.cut();
  assert.deepEqual(f.update(0), []); // held clock: nothing falls, nothing runs down
  assert.equal(f.t, FEVER_TIME);
  const kinds = f.update(0.5);
  assert.ok(kinds.length >= 1 && kinds.length <= 3);
  f.update(100); // far past the end
  assert.equal(f.active, false);
  assert.equal(f.chain, 0);
});

// Proves: a very long frame (lag spike) can't dump more than 3 fruit at once.
test("Fever: a long frame never rains more than 3 fruit", () => {
  const f = new Fever();
  for (let i = 0; i < 40; i++) f.cut();
  assert.ok(f.update(5).length <= 3);
});

// Proves: the ki meter fills, stops at its maximum, empties when spent and ignores filling while locked.
test("KiMeter fills, caps, locks and spends", () => {
  const k = new KiMeter();
  k.add(60); k.add(60);
  assert.equal(k.value, KI_MAX);
  assert.ok(k.full);
  k.spend(); k.locked = true; k.add(50);
  assert.equal(k.value, 0);
});

// Proves: loading a save repairs bad data (invalid JSON, negative or non-number scores, unknown blade) instead of crashing.
test("save: defaults, valid, corrupt and out-of-range values", () => {
  assert.deepEqual(parseSave("not json"), defaultSave());
  const s = parseSave(JSON.stringify({ best: { classic: 120, arcade: -5, zen: "x", path: 33.9 }, blade: "Ember", muted: 1, total_sliced: 12 }));
  assert.equal(s.best.classic, 120);
  assert.equal(s.best.arcade, 0);
  assert.equal(s.best.zen, 0);
  assert.equal(s.best.path, 33);
  assert.equal(s.blade, "Ember");
  assert.equal(s.muted, true);
  assert.equal(parseSave('{"blade":"Nope"}').blade, "Moonlight");
  assert.equal(parseSave(null).blade, "Moonlight");
});

// Proves: a save written to storage loads back identically, and a blocked or broken storage never throws.
test("save: round trip through storage, and a storage that throws", () => {
  const mem = new Map();
  const storage = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  const data = defaultSave(); data.best.zen = 77; data.blade = "Sakura";
  writeSave(storage, data);
  assert.ok(mem.has(SAVE_KEY));
  assert.deepEqual(loadSave(storage), data);
  const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.deepEqual(loadSave(broken), defaultSave());
  assert.doesNotThrow(() => writeSave(broken, data));
});

// Proves: a boss takes 30 hits, ignores hits inside the cooldown, cracks in stages, splits on the last hit and then finishes.
test("Boss: 30 hits, 60 ms cooldown, crack stages, split on the last", () => {
  const b = new Boss(null, "durian");
  assert.equal(b.hp, HP);
  assert.ok(b.hit(0, 1, 0));
  assert.ok(!b.hit(COOLDOWN / 2, 1, 0)); // inside the cooldown
  assert.equal(b.hp, HP - 1);
  let now = 1;
  while (b.hp > CRACK_AT[0]) { b.hit(now, 1, 0); now += 0.1; }
  assert.equal(b.stage, 1);
  while (b.hp > CRACK_AT[1]) { b.hit(now, 1, 0); now += 0.1; }
  assert.equal(b.stage, 2);
  while (b.phase !== "dead") { b.hit(now, 0, 1); now += 0.1; }
  assert.equal(b.hp, 0);
  assert.ok(b.cut && b.cut[3] === 1);
  assert.ok(!b.hit(now + 1, 1, 0)); // dead: no more hits
  b.update(DEATH + 0.1);
  assert.ok(b.done);
});

// Proves: a boss rises, hovers, then escapes if left alone, can't be hit while fleeing, and can be told to flee.
test("Boss: rises, hovers, then escapes and is done; a fleeing boss can't be hit", () => {
  const b = new Boss(null, "pineapple", 640);
  b.update(1.3);
  assert.equal(b.phase, "hover");
  b.update(8.0);
  assert.equal(b.phase, "escape");
  assert.ok(!b.hit(100, 1, 0));
  b.update(1.1);
  assert.ok(b.done);
  const c = new Boss(null, "durian", 640);
  c.update(2);
  c.flee();
  assert.equal(c.phase, "escape");
});

// Proves: the first boss (durian) comes at 45 s, only one at a time, the next (pineapple) 45 s after one ends, and closing makes it flee.
test("BossDirector: first at 45 s (Durian), next 45 s after it ends, closed stops it", () => {
  const d = new BossDirector();
  assert.equal(d.update(44.9, null), null);
  const b = d.update(45, null);
  assert.equal(b.name, "durian");
  assert.ok(d.pauseWaves);
  assert.equal(d.update(46, null), null); // one at a time
  b.done = true;
  assert.equal(d.update(60, null), null); // cooling down until 60 + 45
  assert.equal(d.active, null);
  const b2 = d.update(105, null);
  assert.equal(b2.name, "pineapple");
  d.close();
  assert.equal(d.active, null);
  assert.equal(d.leaving, b2);
  assert.equal(b2.phase, "escape");
  assert.equal(d.update(999, null), null);
  assert.ok(d.pauseWaves);
});

// Proves: no hazards before 20 s, and afterwards each random roll picks the expected hazard (or none).
test("rollHazard: none before 20 s, odds after", () => {
  assert.equal(rollHazard(() => 0, HAZARDS_FROM - 1), null);
  assert.equal(rollHazard(() => 0.0, HAZARDS_FROM), "shuriken");
  assert.equal(rollHazard(() => 0.09, HAZARDS_FROM), "icebomb");
  assert.equal(rollHazard(() => 0.14, HAZARDS_FROM), "golden");
  assert.equal(rollHazard(() => 0.17, HAZARDS_FROM), "chaos");
  assert.equal(rollHazard(() => 0.5, HAZARDS_FROM), null);
});

// Proves: a shuriken flies straight at its target at full speed, keeps a short trail, speeds up when parried and knows when it is off screen.
test("Shuriken: flies at the target at 700 px/s, parry reflects at 1.3x, trail keeps 4", () => {
  const s = new Shuriken(0, 0, 100, 0);
  assert.ok(Math.abs(s.vx - SHURIKEN_SPEED) < 1e-6 && Math.abs(s.vy) < 1e-6);
  for (let i = 0; i < 10; i++) s.update(0.01);
  assert.equal(s.trail.length, 4);
  assert.ok(Math.abs(s.x - 70) < 1e-6);
  s.parry(0, 100); // blade swinging straight down
  assert.ok(s.parried);
  assert.ok(Math.abs(Math.hypot(s.vx, s.vy) - SHURIKEN_SPEED * PARRY_BOOST) < 1e-6);
  assert.ok(s.vy > 0); // carried along the swing
  const t = new Shuriken(-40, 300, 600, 300);
  assert.ok(!t.gone());
  const away = new Shuriken(1400, 300, 2000, 300);
  assert.ok(away.gone());
  assert.ok(!away.gone(0, 1700)); // inside a wider view it is still on screen
});
