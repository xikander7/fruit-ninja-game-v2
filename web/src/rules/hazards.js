// rules/hazards.js - rules for the extra dangers and special fruit in Ninja Path mode. Part of rules/: pure game logic with no drawing and no browser code, so it can be tested directly in Node.
// Ninja Path hazards and special fruit rules (ninja/hazards.py): shuriken, ice bomb, golden fruit, chaos fruit.
import { W, H } from "../config.js";
import { uniform, sign } from "../util.js";

// Chance (0.08 = 8%) that any item in a wave is replaced by that hazard once the game is old enough.
export const HAZARD_ODDS = { shuriken: 0.08, icebomb: 0.05, golden: 0.03, chaos: 0.03 };
export const HAZARDS_FROM = 20.0; // s of game time before the first hazard
// Tuning for shuriken (throwing stars): speed in px/s, hit and size radius in px; parry numbers are for knocking them back with the blade.
export const SHURIKEN_SPEED = 700.0, SHURIKEN_HIT = 22.0, SHURIKEN_R = 26.0;
export const PARRY_SPEED = 1500.0, PARRY_POINTS = 2, PARRY_BOOST = 1.3;
// How long the ice bomb freezes your blade, and how long the chaos fruit flips gravity (seconds).
export const FREEZE_TIME = 2.0, FLIP_TIME = 5.0;
// The golden fruit takes several hits: GOLD_HITS of them, at least GOLD_GAP seconds apart, worth points each plus a bonus.
export const GOLD_HITS = 5, GOLD_GAP = 0.08, GOLD_HIT_POINTS = 5, GOLD_BONUS = 25;
export const ICE = [170, 215, 250];
export const VIOLET = [170, 100, 255];
export const ICE_BLADE = [[30, 60, 90], [80, 120, 155], [130, 165, 195], [120, 155, 185]]; // pale and dim: it cannot cut

// Roll one random number and walk through the odds list like a number line; whichever slot it lands in wins.
/** The hazard (or special fruit) to put in place of one wave item, or null. */
export function rollHazard(rnd, gameTime) {
  if (gameTime < HAZARDS_FROM) return null;
  let r = rnd();
  for (const [kind, p] of Object.entries(HAZARD_ODDS)) {
    if (r < p) return kind;
    r -= p;
  }
  return null;
}

// (x, y) is where it starts, (tx, ty) is where it is aimed. It flies in a straight line.
/** A throwing star: straight at its target at 700 px/s, spinning, no gravity. */
export class Shuriken {
  constructor(x, y, tx, ty) {
    const d = Math.hypot(tx - x, ty - y) || 1;
    this.x = x; this.y = y;
    this.vx = ((tx - x) / d) * SHURIKEN_SPEED;
    this.vy = ((ty - y) / d) * SHURIKEN_SPEED;
    // ang is rotation in degrees, spin is degrees per second. parried/struck are one-way flags.
    this.ang = uniform(0, 90); this.spin = sign() * 1260;
    this.parried = this.struck = false;
    this.trail = []; // recent positions, newest last
    this.age = 0;
  }

  update(dt) {
    if (dt <= 0) return;
    this.trail = [...this.trail, [this.x, this.y, this.ang]].slice(-4);
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.ang += this.spin * dt;
    this.age += dt;
  }

  // The `||` and `&&` mix means: past an edge AND moving further away, so a star just entering the screen is not removed.
  /** Off screen and still heading away (it starts just off an edge, heading in). left/right are the view's edges. */
  gone(left = 0, right = W) {
    return (this.x < left - 80 && this.vx <= 0 || this.x > right + 80 && this.vx >= 0 ||
      this.y < -80 && this.vy <= 0 || this.y > H + 80 && this.vy >= 0);
  }

  // Is the point (px, py) close enough to touch it? Used for the player's pointer.
  near(px, py) {
    return Math.hypot(px - this.x, py - this.y) < SHURIKEN_HIT;
  }

  /** Knocked away by the blade (moving along dx, dy): reflects off the blade's edge, is pushed along the swing, leaves 1.3x faster. */
  parry(dx = 0, dy = 0) {
    this.parried = true;
    const L = Math.hypot(dx, dy);
    let vx = this.vx, vy = this.vy;
    if (L > 0) {
      const ux = dx / L, uy = dy / L;
      const nx = -uy, ny = ux;
      const dot = vx * nx + vy * ny;
      vx -= 2 * dot * nx; vy -= 2 * dot * ny; // mirror off the edge...
      const sp = Math.hypot(vx, vy) || 1;
      vx = vx / sp + ux * 1.2; vy = vy / sp + uy * 1.2; // ...and carried along the swing
    } else {
      vx = -vx; vy = -vy;
    }
    const sp = Math.hypot(vx, vy) || 1;
    this.vx = (vx / sp) * SHURIKEN_SPEED * PARRY_BOOST;
    this.vy = (vy / sp) * SHURIKEN_SPEED * PARRY_BOOST;
    this.spin *= -1.6;
  }
}

/** Per-run hazard state on Play (`play.hz`). */
export class Hazards {
  constructor() {
    this.shurikens = [];
    this.flipT = 0; // gravity-flip time left (game seconds)
    this.punch = 0; // violet pulse on a flip / flip back: 1 easing to 0
    this.red = 0; // red flash after a shuriken hit
    this.rings = []; // [x, y, age]: metallic ring of a parry
    this.mistT = 0;
  }
}
