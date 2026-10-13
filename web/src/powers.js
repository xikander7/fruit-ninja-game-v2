// powers.js - the three superpowers you unlock by filling the Ki meter.
// Ki is "energy" earned by slicing; when the meter is full you can spend it on one power.
// Each power is a small class with the same shape: update(dt) moves it, draw() paints it, fx() tweaks the screen,
// onCut() reacts to a slice, and `done` becomes true when it is over.
//
// Ki and the three superpowers: Time Stop, Shadow Clones and Dragon Fire (ninja/powers.py).
// Play owns a KiMeter (only in modes with the "powers" feature) and at most one active power, and keeps thin hooks:
// useChosenPower (keys Q/W/E, right click, the seals), tickPower once a frame, onCut from Play.hit, power.fx in
// its post-fx and power.draw in its world layer. Everything a power does or draws lives here.
import { W, H, GOLD } from "./config.js";
import { uniform, choice, shade, rgb, TAU } from "./util.js";
import { segHitsCircle } from "./rules/collide.js";
import { KI_PER_CUT } from "./rules/ki.js";
import { Trail } from "./fx.js";
import { catmullRom, addGlow, circle, line, polygon, polyline } from "./gfx.js";

/** The world's cut-effect LOD (1 at normal cut rates): power effects thin out with the juice in a cut storm. */
function cutLod(w) {
  return Math.min(1.0, w.HEAT_LOD / Math.max(1.0, w.cutHeat));
}

// Is this fruit currently inside the visible stage? Used so clones only chase fruit you can see.
const onScreen = (b) => b.alive && -b.r < b.x && b.x < W + b.r && -b.r < b.y && b.y < H;

// Base class for all powers: shared fields with safe defaults that each power overrides.
// `play` is the running game (Play in play.js).
class Power {
  constructor(play) {
    this.play = play; this.t = 0; this.done = false;
    // Colours that replace the normal blade colours while the power is active.
    this.blade = null; // [outer, mid, core, trail core]: replaces the player's blade colours while active
    this.color = GOLD; // HUD accent
    this.title = "";
    // worldScale multiplies how fast the world moves (0 freezes it). blocksSlicing stops normal slicing.
    this.worldScale = 1.0; this.blocksSlicing = false;
  }
  left() { return Math.max(0, 1 - this.t / this.DURATION); } // share of the power's time still to run (HUD bar)
  fx() {}
  onCut() {}
}

// Time Stop: freeze the world, draw a path with the pointer, then every fruit on the path is sliced.
// ---------------- Time Stop ----------------

/** The world holds its breath for 3 s: the pointer draws a path of light, then every fruit it crossed is cut in
 * the order it was touched, 40 ms apart, as the blade retraces the path. */
class TimeStop extends Power {
  constructor(play) {
    super(play);
    this.name = "timestop"; this.DURATION = 3.0; this.worldScale = 0.0; this.blocksSlicing = true;
    this.title = "TIME STOP"; this.color = [214, 222, 236];
    // Tuning: GAP is the delay between each resolution cut; INK are the three glow colours of the path.
    this.GAP = 0.04; // s between resolution cuts
    this.INK = [[14, 18, 30], [92, 108, 146], [226, 232, 248]]; // path glow: outer, body, core
    this.path = [[...play.app.mouse]];
    this.marked = []; // [body, segment, time marked], in order of first touch
    this.queue = null; // bodies to cut, filled when time resumes
    this.after = 0; // real s since time resumed
    this.nextCut = 0;
    this.retrace = 0.18;
  }

  // Phase 1 (queue is null): time is stopped, the pointer path is recorded and fruit it crosses are "marked".
  // Phase 2: time resumes and the marked fruit are cut one by one.
  update(dt) {
    const p = this.play;
    if (this.queue === null) {
      this.t += dt;
      const m = p.app.mouse, last = this.path[this.path.length - 1];
      if (m[0] !== last[0] || m[1] !== last[1]) {
        this.touch([last[0], last[1], m[0], m[1]]);
        this.path.push([m[0], m[1]]);
      }
      if (this.t >= this.DURATION) {
        this.worldScale = 1.0; this.blocksSlicing = false;
        this.queue = this.marked.map(([b, seg]) => [b, seg]);
        this.retrace = Math.max(0.18, this.GAP * this.queue.length);
        p.w.shake.kick(0.3);
        p.w.flash = Math.max(p.w.flash, 0.25);
        p.app.audio.play("swoosh");
      }
      return;
    }
    this.after += dt;
    this.nextCut -= dt;
    while (this.queue.length && this.nextCut <= 0) {
      const [b, seg] = this.queue.shift();
      if (b.alive && p.state === "play") {
        p.hit(b, seg);
        const [ax, ay, bx, by] = seg;
        const L = Math.hypot(bx - ax, by - ay) || 1;
        p.w.slashes.push([b.x, b.y, (bx - ax) / L, (by - ay) / L, b.r * 2.6, 0.0]); // a long clean stroke
        p.w.shake.kick(0.12);
      }
      this.nextCut += this.GAP;
    }
    if (!this.queue.length && this.after >= 0.3) this.done = true;
  }

  // Mark any fruit this path piece crosses (each fruit only once, in the order it was first touched).
  touch(seg) {
    for (const b of this.play.w.bodies) {
      if (b.alive && this.marked.every((m) => m[0] !== b) && segHitsCircle(...seg, b.x, b.y, b.r * 1.05)) this.marked.push([b, seg, this.t]);
    }
  }

  left() { return this.queue !== null ? 0.0 : Math.max(0, 1 - this.t / this.DURATION); }

  /** 1 while time is held (eased in), dropping fast back to 0 as it resumes. */
  strength() {
    if (this.queue === null) return Math.min(1.0, this.t / 0.12);
    return Math.max(0.0, 1 - this.after / 0.2);
  }

  // Post-effects: the screen drains of colour and zooms a touch while time is held.
  fx(params) {
    const k = this.strength();
    params.saturation = Math.min(params.saturation, 1 - 0.75 * k);
    params.zoom = Math.max(params.zoom, 1 + 0.02 * k);
  }

  // L = normal layer, add = glowing additive layer, ui = interface layer (the countdown ring is UI).
  draw(L, add, ui) {
    const app = this.play.app;
    const fade = this.queue === null ? 1.0 : Math.max(0.0, 1 - this.after / 0.3);
    if (fade > 0 && this.path.length >= 2) this.drawPath(add, fade);
    for (const [b, , tm] of this.marked) { // each fruit the path has claimed wears a thin gold ring until it is cut
      if (b.alive) {
        const u = Math.min(1.0, (this.t - tm) / 0.14);
        const r = b.r * (1.25 + 0.5 * (1 - u) ** 2);
        circle(add, b.x, b.y, r, rgb(shade(GOLD, 0.55 * fade)), 2);
        addGlow(add, b.r * 1.5, GOLD, 0.18 * fade, b.x, b.y);
      }
    }
    if (this.queue === null) this.drawCountdown(ui);
  }

  /** A brush stroke of light: thick where the hand moved slowly, thin on fast flicks, tapering at both ends.
   * Once time resumes a bright head races along it, retracing the cut. */
  drawPath(add, fade) {
    // Smooth the recorded points into a curve (Catmull-Rom spline), then measure the distance travelled along it (cum).
    const pts = catmullRom(this.path.slice(-300), 2);
    const n = pts.length;
    const cum = [0.0];
    for (let i = 1; i < n; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    const total = cum[n - 1] || 1;
    const head = this.queue === null ? null : Math.min(1.0, this.after / this.retrace) * total;
    // For each point, store the sideways offset that gives the stroke its thickness.
    const prof = []; // (x, y, unit normal * width) once; each layer scales it
    for (let i = 0; i < n; i++) {
      const [x, y] = pts[i];
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(n - 1, i + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const seg = Math.hypot(dx, dy) || 1;
      const c = cum[i];
      // Slow hand = thick wet stroke; fast flick = thin stroke.
      const speed = Math.max(0.4, Math.min(1.25, 1.45 - seg / 28)); // slow hand, wet brush
      const taper = Math.min(1.0, c / 60, ((total - c) / 90) ** 0.7 + 0.15);
      const grain = 0.82 + 0.12 * Math.sin(c / 23) + 0.06 * Math.sin(c / 6.3); // the bristles never lay down evenly
      const w = (3.2 * speed * taper * grain) / seg;
      prof.push([x, y, -dy * w, dx * w]);
    }
    const op = add.globalCompositeOperation;
    add.globalCompositeOperation = "source-over";
    // Three stacked layers (wide dark, medium, thin bright core) make a glowing brush stroke.
    [2.6, 1.0, 0.32].forEach((wk, i) => {
      const left = prof.map(([x, y, nx, ny]) => [x + nx * wk, y + ny * wk]);
      const right = prof.slice().reverse().map(([x, y, nx, ny]) => [x - nx * wk, y - ny * wk]);
      polygon(add, left.concat(right), shade(this.INK[i], fade));
    });
    add.globalCompositeOperation = op;
    if (head !== null && head < total) {
      let i = cum.findIndex((c) => c >= head);
      if (i < 0) i = n - 1;
      const [hx, hy] = pts[i];
      addGlow(add, 26, [255, 250, 235], 0.9 * fade, hx, hy);
      const tail = pts.slice(Math.max(0, i - 24), i + 1);
      if (tail.length >= 2) polyline(add, tail, [255, 252, 240], 3);
    }
  }

  /** A thin ring beside the cursor, unwinding as the held breath runs out. */
  drawCountdown(ui) {
    const [mx, my] = this.play.app.mouse;
    const cx = mx + 30, cy = my - 30, R = 13;
    ui.save();
    ui.lineWidth = 1;
    ui.strokeStyle = "rgba(236,228,210,0.24)";
    ui.beginPath(); ui.arc(cx, cy, R, 0, TAU); ui.stroke();
    const left = this.left();
    if (left > 0) {
      ui.lineWidth = 2;
      ui.strokeStyle = rgb(GOLD);
      ui.beginPath(); ui.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + TAU * left); ui.stroke();
    }
    ui.restore();
  }
}

// Shadow Clones: three ghost blades chase fruit automatically for 5 seconds.
// ---------------- Shadow Clones ----------------

// One ghost blade: position (x, y), velocity (vx, vy), the fruit it is chasing, and its trail.
class Clone {
  constructor(i, x, y, vx, vy) {
    Object.assign(this, { i, x, y, vx, vy, target: null, trail: new Trail() });
  }
}

/** Three ghost blades leave the cursor and hunt fruit on their own for 5 s. They never touch bombs or hazards. */
class ShadowClones extends Power {
  constructor(play) {
    super(play);
    this.name = "clones"; this.DURATION = 5.0;
    this.title = "SHADOW CLONES"; this.color = [176, 150, 232];
    // Tuning: N clones, SPEED in pixels per second, FADE seconds to fade out at the end, GHOST are the purple trail colours.
    this.N = 3; this.SPEED = 1600; this.FADE = 0.3;
    this.GHOST = [[48, 26, 92], [104, 70, 178], [196, 172, 250], [206, 186, 255]];
    this.EMERGE = 0.22; // s the clones fan out of the cursor before they start hunting
    const [mx, my] = play.app.mouse;
    this.clones = [];
    for (let i = 0; i < this.N; i++) { // fanned out of the cursor, so they curve away before turning onto their targets
      // Spread the three clones out in a fan, starting from pointing up.
      const a = -Math.PI / 2 + (i - 1) * 2.1;
      this.clones.push(new Clone(i, mx, my, Math.cos(a) * this.SPEED * 0.7, Math.sin(a) * this.SPEED * 0.7));
    }
    const w = play.w;
    w.particles.sparks(mx, my, this.GHOST[2], 26, 520, 0.45);
    for (let i = 0; i < 8; i++) {
      const a = uniform(0, TAU);
      w.particles.add(mx, my, Math.cos(a) * 140, Math.sin(a) * 140, 0.45, 26, this.GHOST[1], "glow", 0.0);
    }
  }

  /** Nearest fruit on screen, preferring one no other clone is already chasing. */
  pick(c) {
    const mine = this.play.w.bodies.filter((b) => onScreen(b) && !b.bomb && b.hazard === "");
    if (!mine.length) return null;
    const taken = new Set(this.clones.filter((o) => o !== c && o.target).map((o) => o.target));
    const free = mine.filter((b) => !taken.has(b));
    const pool = free.length ? free : mine;
    let best = null, bd = Infinity;
    for (const b of pool) {
      const d = (b.x - c.x) ** 2 + (b.y - c.y) ** 2;
      if (d < bd) { bd = d; best = b; }
    }
    return best;
  }

  // Steering: each clone accelerates toward its target. It aims at a point, turns its velocity toward it, and the cut happens
  // when its path this frame passes through the fruit.
  update(dt) {
    this.t += dt;
    const hunting = this.EMERGE <= this.t && this.t < this.DURATION;
    const [mx, my] = this.play.app.mouse;
    for (const c of this.clones) {
      if (hunting && (c.target === null || !onScreen(c.target))) c.target = this.pick(c);
      const tgt = hunting ? c.target : null;
      let tx, ty;
      if (tgt !== null) { tx = tgt.x; ty = tgt.y; }
      else { // nothing to cut: drift in a loose ring around the cursor
        const a = this.t * 3 + (c.i * TAU) / this.N;
        tx = mx + Math.cos(a) * 80; ty = my + Math.sin(a) * 50;
      }
      let dx = tx - c.x, dy = ty - c.y;
      let d = Math.hypot(dx, dy) || 1;
      let sp = tgt !== null ? this.SPEED : Math.min(this.SPEED * 0.6, d * 5);
      if (this.t < this.EMERGE) { // still fanning out: keep the launch heading, slowing to a poise
        sp = this.SPEED * 0.7 * (1 - this.t / this.EMERGE) + 120; dx = c.vx; dy = c.vy; d = Math.hypot(c.vx, c.vy) || 1;
      }
      // steering tightens as the target nears, so a clone curves in instead of orbiting it
      const k = Math.min(1.0, dt * Math.max(7.0, (2.2 * this.SPEED) / d));
      c.vx += ((dx / d) * sp - c.vx) * k;
      c.vy += ((dy / d) * sp - c.vy) * k;
      const v = Math.hypot(c.vx, c.vy) || 1;
      if (tgt !== null) { c.vx = (c.vx / v) * sp; c.vy = (c.vy / v) * sp; }
      const px = c.x, py = c.y;
      c.x += c.vx * dt;
      c.y += c.vy * dt;
      if (tgt !== null && segHitsCircle(px, py, c.x, c.y, tgt.x, tgt.y, tgt.r)) this.cut(c, tgt);
      c.trail.add(c.x, c.y, this.t);
      c.trail.update(this.t);
    }
    if (this.t >= this.DURATION + this.FADE) this.done = true;
  }

  // A clone slices fruit `b`: build a short blade segment along the clone's direction and score it like a normal hit.
  cut(c, b) {
    const v = Math.hypot(c.vx, c.vy) || 1;
    const ux = c.vx / v, uy = c.vy / v;
    const r = b.r * 1.5;
    this.play.hit(b, [b.x - ux * r, b.y - uy * r, b.x + ux * r, b.y + uy * r]);
    this.play.w.particles.sparks(b.x, b.y, this.GHOST[2], Math.round(10 * cutLod(this.play.w)), 420, 0.35);
    c.target = null;
  }

  // Each clone is a glowing trail with a short bright blade at its head.
  draw(L, add) {
    const fade = Math.min(1.0, this.t / 0.1, Math.max(0.0, (this.DURATION + this.FADE - this.t) / this.FADE));
    if (fade <= 0) return;
    const cols = this.GHOST.map((col) => shade(col, 0.8 * fade)); // ghosts: never as solid as the real blade
    for (const c of this.clones) {
      c.trail.draw(add, cols, this.t, true);
      addGlow(add, 30, this.GHOST[1], 0.6 * fade, c.x, c.y);
      const v = Math.hypot(c.vx, c.vy) || 1; // the ghost blade itself: a short edge of light along its heading
      const ux = (c.vx / v) * 16, uy = (c.vy / v) * 16;
      line(add, c.x - ux, c.y - uy, c.x + ux, c.y + uy, cols[2], 3);
      circle(add, c.x + ux, c.y + uy, 2, rgb(cols[3]));
    }
  }
}

// Dragon Fire: the blade burns, and each fruit it cuts explodes in flames that set nearby fruit alight too.
// ---------------- Dragon Fire ----------------

/** For 6 s the blade burns: a fruit it cuts flares and bursts after 0.15 s, and the burst sets every fruit
 * within 140 px alight in turn. Fire never touches bombs. */
class DragonFire extends Power {
  constructor(play) {
    super(play);
    this.name = "dragonfire"; this.DURATION = 6.0;
    this.title = "DRAGON FIRE"; this.color = [255, 146, 60];
    // Tuning: IGNITE_DELAY is the pause before a cut fruit bursts; RADIUS (pixels) is how far the fire spreads.
    this.IGNITE_DELAY = 0.15; this.RADIUS = 140;
    this.RING = 0.4; // s for a fire ring to spread
    this.blade = [[150, 26, 0], [255, 96, 14], [255, 196, 96], [255, 226, 160]];
    this.FLAME = [[255, 120, 30], [255, 90, 20], [255, 160, 60]];
    // Bookkeeping for effects in flight (see each comment). `emit` carries leftover fractions of a particle between frames.
    this.pending = []; // [x, y, delay left, r]: cut fruit about to burst
    this.rings = []; // [x, y, age]
    this.jumps = []; // [x0, y0, x1, y1, age, bend]: the fire leaping to the next fruit
    this.emit = 0;
    this.burst(...play.app.mouse, false);
  }

  // Called for every cut while the power is on: queue a burst (but never ignite bombs).
  onCut(b) {
    if (this.t < this.DURATION && !b.bomb) this.pending.push([b.x, b.y, this.IGNITE_DELAY, b.r]);
  }

  // Each frame: shed flame while the blade moves fast (app.speed in pixels/second), then count down pending bursts and age the rings and flame jumps.
  update(dt) {
    this.t += dt;
    const app = this.play.app, w = this.play.w;
    if (this.t < this.DURATION && app.speed > 250) { // the blade sheds flame and embers as it moves
      // 160 particles per second, accumulated as a fraction and spent one whole particle at a time.
      this.emit += dt * 160;
      const [mx, my] = app.mouse;
      while (this.emit >= 1) {
        this.emit -= 1;
        const a = uniform(0, TAU), sp = uniform(20, 120);
        w.particles.add(mx, my, Math.cos(a) * sp, Math.sin(a) * sp - 60, uniform(0.16, 0.3), uniform(12, 22), choice(this.FLAME), "glow", -0.12);
        if (Math.random() < 0.5) {
          w.particles.add(mx, my, Math.cos(a) * sp * 2, Math.sin(a) * sp * 2 - 140, uniform(0.5, 1.0), uniform(1.5, 2.5), choice(this.FLAME), "ember", -0.25);
        }
      }
    }
    for (const q of this.pending) q[2] -= dt;
    const ready = this.pending.filter((q) => q[2] <= 0);
    this.pending = this.pending.filter((q) => q[2] > 0);
    for (const [x, y] of ready) this.burst(x, y);
    for (const r of this.rings) r[2] += dt;
    this.rings = this.rings.filter((r) => r[2] < this.RING);
    for (const j of this.jumps) j[4] += dt;
    this.jumps = this.jumps.filter((j) => j[4] < 0.22);
    if (this.t >= this.DURATION && !this.pending.length && !this.rings.length) this.done = true;
  }

  // Explosion of fire at (x, y). With spread=true it also ignites fruit within RADIUS by cutting them.
  burst(x, y, spread = true) {
    const w = this.play.w;
    // In a storm of cuts, use fewer particles so the game does not slow down.
    const lod = cutLod(w);
    this.rings.push([x, y, 0.0]);
    w.particles.embers(x, y, Math.round(24 * lod * lod), 480); // embers linger: thin them hardest
    w.particles.sparks(x, y, [255, 170, 70], Math.round(16 * lod), 600, 0.4);
    for (let i = 0; i < Math.max(1, Math.round(12 * lod)); i++) { // the fireball: soft flame blobs rolling outward and up
      const a = uniform(0, TAU), sp = uniform(60, 260);
      w.particles.add(x, y, Math.cos(a) * sp, Math.sin(a) * sp - 60, uniform(0.3, 0.5), uniform(28, 50) * (0.6 + 0.4 * lod), choice(this.FLAME), "glow", -0.15);
    }
    if (!spread) return;
    w.shake.kick(0.18);
    for (const b of [...w.bodies]) {
      if (b.alive && !b.bomb && b.hazard === "" && Math.hypot(x - b.x, y - b.y) <= this.RADIUS) {
        const dx = b.x - x, dy = b.y - y;
        const d = Math.hypot(dx, dy) || 1;
        this.jumps.push([x, y, b.x, b.y, 0.0, choice([-1, 1]) * uniform(0.15, 0.3)]);
        const r = b.r * 1.5; // cut across the line the fire travelled
        this.play.hit(b, [b.x - (dy / d) * r, b.y + (dx / d) * r, b.x + (dy / d) * r, b.y - (dx / d) * r]);
        if (this.play.state !== "play") return;
      }
    }
  }

  draw(L, add) {
    // "Licks" are the small flame blobs drawn around each expanding fire ring.
    const licks = Math.max(4, Math.round(24 * cutLod(this.play.w)));
    for (const [x, y, left, r] of this.pending.slice(-6)) { // the cut fruit flares up before it bursts (in a firestorm, the newest)
      const u = 1 - left / this.IGNITE_DELAY;
      addGlow(add, r * (1.5 + 0.9 * u), [255, 120, 30], (0.5 + 0.5 * u) * uniform(0.85, 1.0), x, y);
    }
    this.rings.forEach(([x, y, age], n) => {
      const u = age / this.RING;
      const e = 1 - (1 - u) ** 3;
      const rad = this.RADIUS * (0.2 + 0.8 * e);
      const k = 1 - u * u;
      if (n >= this.rings.length - 6) addGlow(add, rad * 0.9, [255, 110, 30], 0.45 * k, x, y); // the big inner glow is the costly part
      for (let i = 0; i < licks; i++) { // the flame front: licks of fire riding the ring, flickering
        const a = (i * TAU) / licks + age * 2.5;
        const rr = rad * uniform(0.93, 1.04);
        addGlow(add, 14 + 20 * k, choice(this.FLAME), k * uniform(0.6, 1.0), x + Math.cos(a) * rr, y + Math.sin(a) * rr);
      }
      circle(add, x, y, rad, rgb(shade([255, 222, 160], k)), Math.max(1, Math.trunc(3 * k)));
    });
    for (const [x0, y0, x1, y1, age, bend] of this.jumps) { // a curling tongue of flame, gone in a blink
      const k = 1 - age / 0.22;
      const nx = -(y1 - y0) * bend, ny = (x1 - x0) * bend;
      const pts = [];
      for (let i = 0; i < 9; i++) {
        const t = i / 8, s = 4 * t * (1 - t);
        pts.push([x0 + (x1 - x0) * t + nx * s + uniform(-2, 2), y0 + (y1 - y0) * t + ny * s + uniform(-2, 2)]);
      }
      polyline(add, pts, shade([255, 90, 20], 0.8 * k), 7);
      polyline(add, pts, shade([255, 220, 150], k), 2);
    }
  }
}

// The functions below are what Play calls. Everything above stays inside this file.
// ---------------- Play hooks ----------------

// Lookup tables: name -> class, key -> name, name -> [seal symbol, caption].
const POWERS = { timestop: TimeStop, clones: ShadowClones, dragonfire: DragonFire };
export const KEYS = { q: "timestop", w: "clones", e: "dragonfire" };
const STAMPS = { timestop: ["STOP", "Time stop"], clones: ["COPY", "Shadow clones"], dragonfire: ["FIRE", "Dragon fire"] };

/** Start a power: only in play, unpaused, with a full meter and nothing already running. */
export function usePower(play, name) {
  const ki = play.ki;
  if (!ki || play.state !== "play" || play.paused || !ki.full || play.power !== null) return false;
  ki.spend();
  ki.locked = true;
  play.power = new POWERS[name](play);
  play.lastPower = name;
  play.app.audio.play(name);
  play.w.stamp(...STAMPS[name], W / 2, H * 0.72, 110); // low: the action is up in the fruit's arcs
  play.w.shake.kick(0.25);
  return true;
}

/** Run the active power for a real-time frame; end it (unlocking Ki) once it's done and its combo is tallied,
 * or as soon as the run stops being played. */
export function tickPower(play, dt) {
  const pw = play.power;
  if (pw !== null) {
    if (play.state === "play") pw.update(dt);
    if ((pw.done && !play.combo) || play.state !== "play") {
      play.power = null;
      play.ki.locked = false;
    }
  }
  play.w.powerScale = play.power ? play.power.worldScale : 1.0;
}

// Called by Play for every normal cut: earns Ki and lets the active power react.
export function onCut(play, b) {
  if (play.ki) play.ki.add(KI_PER_CUT);
  if (play.power) play.power.onCut(b);
}
