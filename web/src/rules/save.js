// rules/save.js - reading and writing the player's progress (best scores, chosen blade, mute, total fruit sliced).
// Part of rules/: pure game logic with no drawing and no browser code, so it can be tested directly in Node.
// The browser's localStorage (a small key/value store that survives closing the page) is passed in as `storage`,
// so tests can use a fake one.
// The save file: the same JSON shape as the Python game's ~/.fruit_ninja_dojo.json (ninja/game.py load_save).
import { MODES, BLADES } from "../config.js";

// The name the save is stored under in localStorage.
export const SAVE_KEY = "slash-and-splash-save";

// A brand-new player's progress.
export function defaultSave() {
  return { best: Object.fromEntries(Object.keys(MODES).map((m) => [m, 0])), blade: "Moonlight", muted: false, total_sliced: 0 };
}

/** Parse saved text into a valid save; anything missing or corrupt falls back to the defaults. */
export function parseSave(text) {
  const data = defaultSave();
  try {
    // Save text can be missing, edited by hand or corrupted, so every field is checked before it is trusted.
    const raw = JSON.parse(text);
    for (const m of Object.keys(MODES)) {
      const v = raw && raw.best ? raw.best[m] : 0;
      data.best[m] = typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.trunc(v) : 0;
    }
    const blade = raw && raw.blade === "Sakura" ? "Petal Fan" : raw && raw.blade;
    if (Object.hasOwn(BLADES, blade)) data.blade = blade;
    data.muted = Boolean(raw && raw.muted);
    const n = Math.trunc(Number(raw && raw.total_sliced));
    data.total_sliced = Number.isFinite(n) ? Math.max(0, n) : 0;
  } catch (e) { /* missing or corrupt save: start fresh */ }
  return data;
}

// Read the save from `storage`. If storage is unavailable (e.g. blocked in private mode) just use defaults.
export function loadSave(storage) {
  try {
    return parseSave(storage.getItem(SAVE_KEY));
  } catch (e) {
    return defaultSave(); // no storage (private mode, blocked): the game still runs
  }
}

/** Never throws: losing a save must never crash the game. */
export function writeSave(storage, data) {
  try {
    storage.setItem(SAVE_KEY, JSON.stringify(data));
  } catch (e) { /* ignore */ }
}
