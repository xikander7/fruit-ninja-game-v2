// The save file: the same JSON shape as the Python game's ~/.fruit_ninja_dojo.json (ninja/game.py load_save).
import { MODES, BLADES } from "../config.js";

export const SAVE_KEY = "hanifa-fruit-ninja-save";

export function defaultSave() {
  return { best: Object.fromEntries(Object.keys(MODES).map((m) => [m, 0])), blade: "Moonlight", muted: false, total_sliced: 0 };
}

/** Parse saved text into a valid save; anything missing or corrupt falls back to the defaults. */
export function parseSave(text) {
  const data = defaultSave();
  try {
    const raw = JSON.parse(text);
    for (const m of Object.keys(MODES)) {
      const v = raw && raw.best ? raw.best[m] : 0;
      data.best[m] = typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.trunc(v) : 0;
    }
    if (raw && Object.hasOwn(BLADES, raw.blade)) data.blade = raw.blade;
    data.muted = Boolean(raw && raw.muted);
    const n = Math.trunc(Number(raw && raw.total_sliced));
    data.total_sliced = Number.isFinite(n) ? Math.max(0, n) : 0;
  } catch (e) { /* missing or corrupt save: start fresh */ }
  return data;
}

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
