// The world: everything that lives on the dojo wall (World in ninja/game.py).
import { W, H, GRAVITY, VIEW, WASHI, HANKO } from "./config.js";
import { uniform, shade, rgb, deg } from "./util.js";
import { Particles, Stains, Popups, Stamp, Shake } from "./fx.js";
import { Body, Half } from "./entities.js";
import { glowImg, rayBurst, drawSprite, circle } from "./gfx.js";

export class World {
  /** `bg`: a view-sized canvas to use as the wall (the blurred snapshot behind the results), else the dojo wall. */
  constructor(app, bg = null) {
    this.HEAT_TAU = 0.5; this.HEAT_LOD = 6.0; this.MAX_HALVES = 28; // cut-effect LOD: a storm of cuts gets lighter juice per cut
    this.PUNCH = 0.25; // s for a combo zoom punch to ease back
    this.SLOW_HOLD = 0.4; this.SLOW_EASE = 0.15; // slow-mo: held at full strength, then eased back to real time
    this.SHOCK = 0.6; // s for a bomb shockwave to cross the screen
    this.app = app;
    this.art = app.art;
    this.bg = bg; // null: the wall
    this.bgDraw = null; // {scale, dx, dy}: how the menu drifts and parallaxes the wall
    this.bodies = []; this.halves = [];
    this.particles = new Particles(app.art, app.touch ? 700 : 1400);
    this.stains = new Stains();
    this.popups = new Popups(app.art.fonts);
    this.stamps = [];
    this.shake = new Shake();
    this.slashes = []; this.rings = [];
    this.flash = 0;
    this.hitstop = 0;
    this.punch = [1.0, this.PUNCH]; // (peak zoom, age)
    this.slowmo = 0; // real seconds of slow-mo left
    this.shocks = []; // [x, y, age]
    this.t = 0;
    this.gflip = 1.0; // gravity sign: -1 while a chaos fruit has turned the dojo upside down
    this.powerScale = 1.0; // 0 while Time Stop holds the world still
    this.cutHeat = 0; // ~ cuts in the last HEAT_TAU s (decays exponentially on real time)
    this.moteT = 0;
    this.emberT = uniform(1.0, 3.0);
    for (let i = 0; i < 40; i++) this.particles.mote(this.viewBox()); // the dojo already has dust hanging in the lamplight
  }

  viewBox() {
    return { x: -VIEW.ox, y: -VIEW.oy, w: VIEW.w, h: VIEW.h };
  }

  throw(kind, x, y, vx, vy, isStatic = false) {
    const b = new Body(this.art, kind, x, y, vx, vy, isStatic);
    this.bodies.push(b);
    return b;
  }

  cut(b, ax, ay, bx, by) {
    b.alive = false;
    let dx = bx - ax, dy = by - ay;
    const L = Math.hypot(dx, dy) || 1;
    dx /= L; dy /= L;
    const nx = -dy, ny = dx;
    const fa = this.art.fruits[b.kind];
    for (const side of [1, -1]) {
      const sx = nx * side, sy = ny * side;
      const vx = (b.static ? 0 : b.vx * 0.6) + sx * 170 + dx * 60;
      const vy = (b.static ? 0 : b.vy * 0.6) + sy * 170 - 120;
      this.halves.push(new Half(fa, b.x + sx * b.r * 0.3, b.y + sy * b.r * 0.3, vx, vy, deg(Math.atan2(-sy, sx)), b));
    }
    if (this.halves.length > this.MAX_HALVES) this.halves.splice(0, this.halves.length - this.MAX_HALVES); // the oldest are falling away anyway
    this.cutHeat += 1; // 1 at normal cut rates; powers and fruit rain can cut dozens a second
    const lod = Math.min(1.0, this.HEAT_LOD / this.cutHeat);
    if (lod >= 1 || Math.random() < lod) this.particles.splash(b.x, b.y, b.ft.juice, nx, ny, b.r); // first, so the droplets draw over it
    this.particles.juice(b.x, b.y, b.ft.juice, nx, ny, 35, b.r * 1.1, lod); // the whole chord of the cut
    if (lod >= 0.5) this.stains.add(b.ft.juice, b.r, b.x, b.y);
    this.slashes.push([b.x, b.y, dx, dy, b.r * 1.6, 0.0]);
    this.app.audio.play("splat", 0.8);
  }

  explode(b) {
    b.alive = false;
    this.rings.push([b.x, b.y, 0.0]);
    this.shocks.push([b.x, b.y, 0.0]);
    this.flash = 0.8;
    this.hitstop = 0.12;
    this.particles.sparks(b.x, b.y, [255, 190, 90], 50, 1100, 0.7);
    this.particles.sparks(b.x, b.y, [255, 255, 230], 20, 500, 0.35);
    this.particles.smoke(b.x, b.y, 22);
    this.particles.shards(b.x, b.y, 10);
    this.particles.embers(b.x, b.y, 40);
    this.shake.kick(1.0);
    this.app.audio.play("explode");
  }

  zoomPunch(zoom) { this.punch = [zoom, 0.0]; }
  slow() { this.slowmo = this.SLOW_HOLD + this.SLOW_EASE; }

  /** 1 while slow-mo is at full strength, easing to 0 as it ends. */
  slowK() {
    if (this.slowmo <= 0) return 0.0;
    if (this.slowmo >= this.SLOW_EASE) return 1.0;
    const u = this.slowmo / this.SLOW_EASE;
    return u * u * (3 - 2 * u);
  }

  timeScale() { return (1.0 - 0.7 * this.slowK()) * this.powerScale; } // 0.3 at full slow-mo

  stamp(glyph, caption, x, y, size = 120, color = WASHI, bonus = null, hold = false) {
    this.stamps.push(new Stamp(this.art, glyph, caption, x, y, size, color, bonus, hold));
  }

  update(dt, realDt) {
    // camera/post effects run on real time so they play out even through hit-stop and slow-mo
    this.t += realDt;
    this.shake.update(realDt);
    this.flash = Math.max(0, this.flash - realDt * 6.0); // a sharp pop; a slow fade reads as fog
    this.slowmo = Math.max(0, this.slowmo - realDt);
    this.cutHeat *= Math.exp(-realDt / this.HEAT_TAU);
    this.punch[1] += realDt;
    for (const s of this.shocks) s[2] += realDt;
    this.shocks = this.shocks.filter((s) => s[2] < this.SHOCK);
    for (const st of this.stamps) {
      if (!st.landed && st.age >= 0.11) {
        st.landed = true;
        this.particles.ink(st.x, st.y, HANKO, 18);
        this.shake.kick(0.22);
        this.app.audio.play("stamp", 0.7);
      }
    }
    this.stamps = this.stamps.filter((s) => s.update(realDt));
    this.popups.update(realDt);
    if (this.hitstop > 0) {
      this.hitstop -= realDt;
      return;
    }
    const g = GRAVITY * this.gflip;
    for (const b of this.bodies) b.update(dt, g);
    for (const h of this.halves) h.update(dt, g);
    this.halves = this.halves.filter((h) => !h.gone());
    this.particles.update(dt);
    this.particles.blur = this.timeScale(); // slow-mo shortens streaks; freeze doesn't
    this.stains.update(dt);
    for (const s of this.slashes) s[5] += dt;
    this.slashes = this.slashes.filter((s) => s[5] < 0.16);
    for (const r of this.rings) r[2] += dt;
    this.rings = this.rings.filter((r) => r[2] < this.SHOCK);
    this.moteT -= dt;
    if (this.moteT <= 0) {
      this.moteT = uniform(0.15, 0.35);
      this.particles.mote(this.viewBox());
    }
    this.emberT -= dt;
    if (this.emberT <= 0) { // rare spark drifting up from the lanterns below
      this.emberT = uniform(2.5, 6.0);
      this.particles.lanternEmber({ x: -VIEW.ox, w: VIEW.w, bottom: H + VIEW.oy });
    }
  }

  drawBackground(L) {
    const v = this.app.art.view(VIEW.w, VIEW.h);
    const img = this.bg || v.bg;
    if (this.bgDraw) {
      const { scale, dx, dy } = this.bgDraw;
      L.save();
      L.translate(W / 2 + dx, H / 2 + dy);
      L.scale(scale, scale);
      L.drawImage(img, -VIEW.w / 2, -VIEW.h / 2, VIEW.w, VIEW.h);
      L.restore();
    } else L.drawImage(img, -VIEW.ox, -VIEW.oy, VIEW.w, VIEW.h);
  }

  /** Draw the world into the app's world layer (L) and emissive layer (add); `extra(L, add)` draws a scene's own things. */
  draw(extra = null) {
    const L = this.app.L, add = this.app.add;
    this.drawBackground(L);
    this.stains.draw(L);
    for (const h of this.halves) h.drawShadow(L);
    for (const b of this.bodies) if (b.alive) b.drawShadow(L);
    for (const h of this.halves) h.draw(L);
    for (const b of this.bodies) {
      if (!b.alive) continue;
      if (b.special) { // aura + slowly turning light rays, all emissive so the bloom picks them up
        const col = b.ft.juice;
        const pulse = 0.8 + 0.2 * Math.sin(this.t * 6);
        drawSprite(add, rayBurst(Math.trunc(b.r * 3.4), shade(col, 0.6)), b.x, b.y, this.t * 22);
        const g = glowImg(b.r * 1.9, col, 0.55 * pulse);
        add.drawImage(g, b.x - g.width / 2, b.y - g.height / 2);
      }
      b.draw(L);
    }
    if (extra) extra(L, add);
    this.particles.draw(L, add);
    for (const [x, y, dx, dy, r, age] of this.slashes) {
      const k = 1 - age / 0.16;
      add.strokeStyle = `rgb(${Math.trunc(200 * k)},${Math.trunc(200 * k)},${Math.trunc(190 * k)})`;
      add.lineWidth = Math.max(1, Math.trunc(4 * k));
      add.beginPath();
      add.moveTo(x - dx * r * 1.4, y - dy * r * 1.4);
      add.lineTo(x + dx * r * 1.4, y + dy * r * 1.4);
      add.stroke();
    }
    for (const [x, y, age] of this.rings) { // the shockwave's visible front
      const k = age / this.SHOCK;
      circle(add, x, y, 20 + k * 0.6 * H, rgb(shade([255, 190, 120], 0.55 * (1 - k) ** 2)), Math.max(1, Math.trunc(10 * (1 - k))));
    }
  }

  /** Stamps and popups are UI: they sit above the post effects, never shaken or warped. */
  drawOverlay() {
    const ui = this.app.ui;
    for (const s of this.stamps) s.draw(ui);
    this.popups.draw(ui);
  }

  /** Post effects for this frame; every value decays back to neutral on its own. */
  fxParams() {
    const k = this.slowK();
    const [z, age] = this.punch;
    const punch = age < this.PUNCH ? 1.0 + (z - 1.0) * (1 - age / this.PUNCH) ** 2 : 1.0;
    return { zoom: Math.max(punch, 1.0 + 0.03 * k), saturation: 1.0 - 0.35 * k, flash: this.flash, shake: this.shake.offset() };
  }
}
