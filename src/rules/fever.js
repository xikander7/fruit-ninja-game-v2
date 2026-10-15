// rules/fever.js - the Fever mode rules. Part of rules/: pure game logic with no drawing and no browser code, so it can be tested directly in Node.
// Slice fruit in an unbroken chain to raise a score multiplier (x1 up to x5). At x5, Fever starts for 8 seconds
// and fruit rains from the sky. A miss or bomb breaks the chain.
// Fever: the cut chain, its score multiplier and the fruit rain once it peaks (ninja/fever.py).
import { REGULAR, WEIGHTS } from "../config.js?v=229f44b64d";
import { weighted } from "../util.js?v=229f44b64d";

// Tuning: every 10 cuts adds 1 to the multiplier; MAX_MULT is the cap; FEVER_TIME is its length in seconds.
export const CHAIN_STEP = 10; // cuts per multiplier step
export const MAX_MULT = 5; // reaching it starts Fever
export const FEVER_TIME = 8.0;
export const RAIN_EVERY = 0.12; // s between rain fruit
export const GRADE = [255, 236, 200]; // warm gold multiply over the world during Fever

// `rnd` is the random function to use; tests pass a fixed one so results are predictable.
export class Fever {
  constructor(rnd = Math.random) {
    this.rnd = rnd;
    this.chain = 0;
    this.active = false;
    this.t = 0; // Fever time left
    this.rainT = 0;
    this.pop = 0; // 1 the moment the multiplier steps up, easing to 0 (HUD badge)
  }

  // The current score multiplier (always MAX_MULT during Fever).
  get mult() {
    return this.active ? MAX_MULT : Math.min(MAX_MULT, 1 + Math.floor(this.chain / CHAIN_STEP));
  }

  // Apply the multiplier to a base score.
  points(base) {
    return base * this.mult;
  }

  /** Count a cut; true when it starts Fever. */
  cut() {
    const before = this.mult;
    this.chain += 1;
    if (this.mult > before) this.pop = 1.0;
    if (!this.active && this.mult >= MAX_MULT) {
      this.active = true;
      this.t = FEVER_TIME;
      this.rainT = 0;
      return true;
    }
    return false;
  }

  /** A miss or a bomb: the chain breaks, and a running Fever with it. */
  reset() {
    this.chain = 0;
    this.active = false;
    this.t = 0;
  }

  /** Advance by `dt` game seconds; returns the fruit kinds to rain this frame. */
  // Counts Fever down and returns the list of fruit kinds to drop this frame. Dropping is metered by RAIN_EVERY.
  update(dt) {
    this.pop = Math.max(0, this.pop - dt * 3);
    if (!this.active || dt <= 0) return []; // dt 0: Time Stop holds the clock
    // Don't rain for time that is past the end of Fever.
    const run = Math.min(dt, this.t); // no rain past the end of Fever
    this.t -= dt;
    this.rainT -= run;
    const kinds = [];
    while (this.rainT <= 0 && kinds.length < 3) { // a long frame never dumps a crate of fruit at once
      kinds.push(weighted(REGULAR, WEIGHTS, this.rnd));
      this.rainT += RAIN_EVERY;
    }
    this.rainT = Math.max(this.rainT, 0);
    if (this.t <= 0) this.reset();
    return kinds;
  }

  /** Share of Fever still to run (HUD bar). */
  left() {
    return this.active ? Math.max(0, this.t / FEVER_TIME) : 0;
  }

  /** Strength of Fever's gold grade: eased in at the start, out over the last moments. */
  grade() {
    return this.active ? Math.min(1, (FEVER_TIME - this.t) / 0.4, this.t / 0.6) : 0;
  }
}
