// rules/boss.js - the rules for the boss fruit. Part of rules/: pure game logic with no drawing and no browser code, so it can be tested directly in Node.
// A boss moves through phases: rise (comes up from below) -> hover (floats, can be hit) -> escape (leaves),
// or dead if its 30 hit points run out first. A BossDirector decides when a boss shows up.
// Boss fruit rules (ninja/boss.py): a Durian or a Pineapple King rises, hovers, and takes 30 hits to bring down.
// This file is the logic only (motion, hits, phases, when a boss appears). Drawing lives in ../boss.js.
import { W, H, GRAVITY, BOSS_R } from "../config.js";
import { sign, uniform } from "../util.js";

// Tuning numbers. HP = hit points. RISE/HOVER/ESCAPE = seconds spent in each phase.
export const HP = 30;
export const RISE = 1.2, HOVER = 8.0, ESCAPE = 1.0; // s per phase
// A single swipe can touch the boss many times; this minimum gap (seconds) keeps it to one hit per moment.
export const COOLDOWN = 0.06; // s between hits
export const DEATH = 1.4; // s for the split halves to fly clear
// When hp drops to 20 and then 10, more cracks appear on the boss.
export const CRACK_AT = [20, 10]; // hp at which each set of cracks opens
export const NAMES = ["durian", "pineapple"];
export const TITLES = { durian: "Durian", pineapple: "Pineapple King" };
// Colours: FLESH = inside colour for juice and chips; SPARK = sparks when the hard rind is hit.
export const FLESH = { durian: [238, 206, 116], pineapple: [255, 214, 86] }; // juice, chips, the glow inside the cracks
export const CROWN = { durian: 0.2, pineapple: 0.42 }; // share of the sprite height above the body: no cracks there
export const SPARK = [255, 228, 184]; // hard rind: hot, pale sparks, like steel on stone
// Bonus points for the kill. TALLY_* control the on-screen hit counter timing; STAMP_DELAY delays the victory seal.
export const BONUS = 50;
export const TALLY_HOLD = 0.6, TALLY_FADE = 0.3; // s the hit counter stays after the last hit, then fades
export const STAMP_DELAY = 0.25; // s after the kill: the seal lands once the fruit burst has spread

// Easing: starts fast and slows down toward the end (u goes 0..1).
export const easeOut3 = (u) => 1 - (1 - u) ** 3;

/** One side of the split boss: tumbling away under gravity, fading as it goes. */
export class BossHalf {
  constructor(img, x, y, vx, vy, spin) {
    Object.assign(this, { img, x, y, vx, vy, spin, ang: 0 });
  }
  update(dt) {
    this.vy += GRAVITY * 0.85 * dt;
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.ang += this.spin * dt;
  }
}

// The boss itself. `art` is the loaded images (can be null in tests), `name` is "durian" or "pineapple",
// `x` optionally forces the horizontal position. Positions are in stage pixels, angles in degrees.
export class Boss {
  constructor(art, name, x = null) {
    this.art = art;
    this.name = name;
    this.title = TITLES[name];
    this.flesh = FLESH[name];
    this.hp = HP;
    this.r = BOSS_R;
    // `shown` is what the HUD health bar displays: it chases `hp` so damage drains smoothly.
    this.shown = HP; // HUD: a pale damage trail easing down to hp
    // Which way the boss sways while hovering; it is always toward the centre so it stays on screen.
    const side = sign();
    this.x0 = x !== null ? x : W / 2 - side * uniform(0, W * 0.12);
    this.side = side; // sways toward the centre, never off screen
    this.y0 = H * 0.44;
    // y where it begins: just below the bottom of the screen.
    this.start = H + BOSS_R * 1.5;
    this.x = this.x0; this.y = this.start; this.ang = 0; this.scale = 1;
    this.phase = "rise"; this.t = 0; this.done = false;
    // Remembered position and angle where the escape begins, so the exit continues smoothly from where it was.
    this.esc = [this.x, this.y, 0]; // where (and at what angle) the escape starts
    this.lastHit = -1;
    this.hitAge = 9; this.hitDir = [1, 0]; // recoil wobble after a hit
    this.flash = 0;
    this.halves = []; this.cut = null; this.burst = false;
    this.seal = null; // the defeat stamp's bonus text, until it lands
    this.tally = 0; this.tallyT = 9; // points from the current run of hits
    this.deadT = 0;
  }

  // How many crack stages are open (0, 1 or 2), based on remaining hp.
  get stage() {
    return CRACK_AT.filter((h) => this.hp <= h).length;
  }

  /** One hit from a slice moving along (dx, dy); false while cooling down or out of reach. */
  hit(now, dx = 1, dy = 0) {
    if (!(this.phase === "rise" || this.phase === "hover") || now - this.lastHit < COOLDOWN) return false;
    this.lastHit = now;
    this.hp -= 1;
    const L = Math.hypot(dx, dy) || 1;
    this.hitDir = [dx / L, dy / L]; this.hitAge = 0; this.flash = 1;
    if (this.hp <= 0) {
      this.hp = 0; this.phase = "dead"; this.deadT = 0;
      this.split(dx / L, dy / L);
    }
    return true;
  }

  /** The killing cut. The drawn subclass also builds the two flying halves. */
  split(dx, dy) {
    this.cut = [this.x, this.y, dx, dy];
  }

  /** The run is over: leave the stage, untouchable. */
  flee() {
    if (this.phase === "rise" || this.phase === "hover") {
      this.phase = "escape"; this.t = 0; this.esc = [this.x, this.y, this.ang];
    }
  }

  // Move the boss forward by dt seconds. This is a small state machine: phase changes when its timer `t` passes the phase length.
  update(dt) {
    this.shown = Math.max(this.hp, this.shown - dt * 6 * Math.max(1, this.shown - this.hp));
    this.flash = Math.max(0, this.flash - dt * 10);
    this.hitAge += dt;
    this.tallyT += dt;
    if (this.tally && this.tallyT >= TALLY_HOLD + TALLY_FADE) this.tally = 0; // faded out: the next hit starts a fresh count
    if (this.phase === "dead") {
      this.deadT += dt;
      for (const h of this.halves) h.update(dt);
      this.done = this.deadT >= DEATH;
      return;
    }
    this.t += dt;
    if (this.phase === "rise" && this.t >= RISE) { this.phase = "hover"; this.t -= RISE; }
    if (this.phase === "hover" && this.t >= HOVER) {
      this.phase = "escape"; this.t -= HOVER;
      this.esc = [...this.hoverPos(HOVER), this.hoverAng(HOVER)];
    }
    if (this.phase === "escape" && this.t >= ESCAPE) this.done = true;
    // Position and tilt for each phase; the formulas are just easing curves so the motion feels heavy, not robotic.
    if (this.phase === "rise") { // heavy: fast off the floor, settling into place
      const e = easeOut3(this.t / RISE);
      this.x = this.x0; this.y = this.start + (this.y0 - this.start) * e;
      this.ang = 7 * (1 - e) * this.side; this.scale = 0.94 + 0.06 * e;
    } else if (this.phase === "hover") {
      [this.x, this.y] = this.hoverPos(this.t); this.ang = this.hoverAng(this.t); this.scale = 1;
    } else { // gathers itself, then is gone over the top
      const u = Math.min(1, this.t / ESCAPE);
      const [ex, ey, ea] = this.esc;
      this.x = ex; this.y = ey - (ey + this.r * 2.2) * u ** 2.2;
      this.ang = ea - 10 * u * this.side; this.scale = 1 - 0.08 * u;
    }
  }

  // Where the boss is `h` seconds into the hover phase.
  hoverPos(h) {
    // 1 - cos: the bob and sway start from rest, so the rise flows into the hover without a kink
    return [this.x0 + this.side * 70 * (1 - Math.cos(h * 0.8)), this.y0 + 16 * (1 - Math.cos(h * 1.7))];
  }

  // Its gentle rocking angle at that moment (degrees).
  hoverAng(h) {
    return 4.5 * Math.sin(h * 1.1);
  }
}

// Constructor: `make` builds a Boss; tests can pass a simpler one so no drawing code is needed.
/** First boss at `firstAt` s of game time, the next `every` s after the previous one ends; Durian first. */
export class BossDirector {
  constructor(firstAt = 45.0, every = 45.0, make = (art, name) => new Boss(art, name)) {
    this.nextAt = firstAt; this.every = every; this.make = make;
    this.active = null; this.leaving = null;
    this.count = 0;
    this.closed = false; // the run is over: no more bosses, and the waves stay paused
  }

  // True when normal fruit waves should stop (a boss is up, or the run is closing).
  get pauseWaves() {
    return this.closed || this.active !== null;
  }

  // Call every frame. Starts the next boss when its time arrives; returns the new boss or null.
  update(gameTime, play) {
    if (this.active !== null && this.active.done) {
      this.active = null; this.nextAt = gameTime + this.every;
    }
    if (this.closed || this.active !== null || gameTime < this.nextAt) return null;
    // Bosses alternate: durian, pineapple, durian...
    const name = NAMES[this.count % NAMES.length];
    this.count += 1;
    this.active = this.make(play ? play.app.art : null, name);
    if (play) {
      const w = play.w;
      w.stamp("鬼", this.active.title, W / 2, H * 0.8, 120); // below the boss, clear of its rise
      w.shake.kick(0.35);
      play.app.audio.play("boss_roar");
    }
    return this.active;
  }

  /** The run has ended with the boss still up: it leaves (no longer hittable) and nothing returns. */
  close() {
    this.closed = true;
    if (this.active !== null) {
      this.active.flee();
      this.leaving = this.active; this.active = null;
    }
  }
}
