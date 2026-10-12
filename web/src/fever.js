// Fever's hooks into Play (ninja/fever.py). The rules (chain, multiplier, rain timing) are in rules/fever.js.
import { W, H } from "./config.js";
import { uniform } from "./util.js";

/** Before a cut is scored: the chain grows, and the cut that starts Fever already pays x5. */
export function feverCut(play) {
  const f = play.fever;
  if (f && f.cut()) {
    play.w.stamp("熱", "Fever", W / 2, H * 0.44, 120); // clear above a power stamp (H * 0.72), caption included
    play.w.shake.kick(0.25);
    play.w.zoomPunch(1.02);
  }
}

/** Once a frame: Fever's clock runs on game time (Time Stop holds it, and no rain falls into frozen time). */
export function tickFever(play, dt) {
  const f = play.fever;
  if (!f) return;
  const w = play.w;
  if (play.state === "play") {
    const sign = w.gflip > 0 ? 1 : -1; // rain falls with gravity: from the bottom while the dojo is upside down
    for (const kind of f.update(dt * w.powerScale)) {
      const b = w.throw(kind, uniform(W * 0.08, W * 0.92), sign > 0 ? -40 : H + 40, uniform(-120, 120), sign * uniform(60, 160));
      b.rain = true; b.flight = null; // never a strike; no launch arc to swell along
    }
  }
  play.app.audio.loop("fever", f.active && play.state === "play");
}

export function feverFx(play, p) {
  if (play.fever && play.fever.active) p.saturation *= 1.15;
}
