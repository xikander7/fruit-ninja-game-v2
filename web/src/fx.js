// Juice: particles, stains, blade trail, screen shake, popups and hanko stamps (ninja/fx.py).
import { W, H, GRAVITY, WASHI, GOLD } from "./config.js";
import { uniform, randint, choice, gauss, shade, tint, rgb, rgba, TAU, rad, deg } from "./util.js";
import { addGlow, softImg, catmullRom, makeCanvas, getCtx, circle, line, polygon } from "./gfx.js";
import { blit, rectAt } from "./ui.js";

const SPLASH_SCALE = 0.62;

class P {
  constructor(x, y, vx, vy, life, size, color, kind, grav) {
    this.x = x; this.y = y; this.vx = vx; this.vy = vy;
    this.life = this.max = life;
    this.size = size; this.color = color; this.kind = kind; this.grav = grav;
    this.rot = uniform(0, 360); this.vr = uniform(-200, 200);
    this.c2 = this.shape = null;
  }
}

export class Particles {
  constructor(art, cap = 1400) {
    this.art = art;
    this.CAP = cap;
    this.items = [];
    this.blur = 1.0; // slow-mo time scale: streaks shorten in slow-mo, like real motion blur
  }

  add(x, y, vx, vy, life, size, color, kind, grav = 1.0) {
    if (this.items.length < this.CAP) {
      const p = new P(x, y, vx, vy, life, size, color, kind, grav);
      this.items.push(p);
      return p;
    }
    return null;
  }

  drop(x, y, vx, vy, life, size, color) {
    const p = this.add(x, y, vx, vy, life, size, color, "drop");
    if (p) p.c2 = tint(color, 0.55); // wet highlight along the droplet
  }

  /** Juice leaves the whole cut face, flung mostly along the normal: heavy round drops, many fine ones, a brief
   * translucent sheet along the cut and a wet emissive mist. `lod` < 1 thins every count (cut storms). */
  juice(x, y, color, nx, ny, n = 35, spread = 30, lod = 1.0) {
    n = Math.round(n * lod);
    const ux = ny, uy = -nx; // along the cut
    if (lod >= 0.5) {
      for (const side of [1, -1]) { // the sheet of juice torn off the cut face; gone in ~0.15 s
        const p = this.add(x, y, 0, 0, 0.15, spread * 2.2, color, "sheet", 0.0);
        if (p) p.shape = [ux, uy, nx * side, ny * side];
      }
    }
    if (this.art.splashes.length) n = Math.trunc(n / 2); // the splash photo carries the bulk of the liquid
    const heavy = Math.max(1, Math.round(5 * lod));
    for (let i = 0; i < n + heavy; i++) {
      const side = choice([-1, 1]);
      const big = i < heavy; // a few heavy drops; the rest is fine spray
      const sp = (big ? 430 : 560) * uniform(0.35, 1.0);
      const a = Math.atan2(ny * side, nx * side) + gauss(big ? 0.3 : 0.42);
      const o = uniform(-1, 1) * spread;
      const vx = Math.cos(a) * sp, vy = Math.sin(a) * sp - 120;
      const lead = uniform(0.0, 0.05); // staggered release: juice keeps coming off the face, not in one row
      this.drop(x + ux * o + vx * lead, y + uy * o + vy * lead, vx, vy, uniform(0.5, 0.9),
        big ? uniform(2.8, 4.6) : uniform(1.3, 2.4), shade(color, uniform(0.72, 1.05)));
    }
    for (const side of [1, -1]) { // a tight jet of fine droplets off each side
      const a0 = Math.atan2(ny * side, nx * side);
      for (let i = 0; i < Math.max(1, Math.round(8 * lod)); i++) {
        const sp = 640 * uniform(0.35, 1.0);
        const a = a0 + gauss(0.22);
        const o = gauss(0.5) * spread;
        const vx = Math.cos(a) * sp, vy = Math.sin(a) * sp - 160;
        const lead = uniform(0.0, 0.04);
        this.drop(x + ux * o + vx * lead, y + uy * o + vy * lead, vx, vy, uniform(0.4, 0.7), uniform(1.3, 2.1), color);
      }
    }
    for (let i = 0; i < Math.max(2, Math.round(10 * lod)); i++) { // mist on the emissive layer: the bloom turns it into a wet glow
      const a = uniform(0, TAU), sp = uniform(90, 220);
      this.add(x + ux * uniform(-1, 1) * spread, y + uy * uniform(-1, 1) * spread, Math.cos(a) * sp, Math.sin(a) * sp,
        uniform(0.35, 0.55), uniform(16, 30), color, "glow", 0.0);
    }
  }

  /** One photographed splash at the cut, flung along the cut normal (either side); a crown a quarter of the time. */
  splash(x, y, color, nx, ny, r) {
    const art = this.art;
    if (!art.splashes.length) return null;
    const radial = [], directional = [];
    art.splashDirs.forEach((d, i) => (d === null ? radial : directional).push(i));
    const side = choice([1, -1]);
    let i, angle;
    if (radial.length && (!directional.length || Math.random() < 0.25)) {
      i = choice(radial);
      angle = uniform(-20, 20); // a crown seen from the side: only tilt it a little
      x += nx * side * 0.6 * r; y += ny * side * 0.6 * r;
    } else {
      i = choice(directional);
      angle = deg(Math.atan2(-ny * side, nx * side)) - art.splashDirs[i];
    }
    const k = ((2.2 * r) / 300) * uniform(0.9, 1.2);
    const d = art.splashDirs[i];
    const src = art.splashes[i].img;
    if (d !== null) { // the photo's stream starts at its edge: push it forward so it leaves from the fruit
      const a = rad(d);
      const reach = 0.4 * k * (Math.abs(src.width * Math.cos(a)) + Math.abs(src.height * Math.sin(a)));
      x += nx * side * reach; y += ny * side * reach;
    }
    const p = this.add(x, y, 0, 0, 0.35, k, color, "splash", 0.0);
    if (p) {
      p.vr = 0;
      // the tinted sprite (at SPLASH_SCALE of the photo), the angle to turn it, and its final scale
      p.shape = { img: art.splash(i, color), angle, scale: (k * 1.25) / SPLASH_SCALE };
    }
    return p;
  }

  sparks(x, y, color, n = 30, speed = 700, life = 0.6) {
    for (let i = 0; i < n; i++) {
      const a = uniform(0, TAU), sp = uniform(0.2, 1) * speed;
      this.add(x, y, Math.cos(a) * sp, Math.sin(a) * sp, uniform(0.3, 1) * life, uniform(1.5, 3.5), color, "spark", 0.5);
    }
  }

  smoke(x, y, n = 18) {
    for (let i = 0; i < n; i++) {
      const a = uniform(0, TAU), sp = uniform(30, 220), g = randint(40, 80);
      this.add(x, y, Math.cos(a) * sp, Math.sin(a) * sp - 40, uniform(0.8, 1.6), uniform(18, 46), [g, g - 6, g - 10], "smoke", -0.05);
    }
  }

  ink(x, y, color, n = 16) {
    for (let i = 0; i < n; i++) {
      const a = uniform(0, TAU), sp = uniform(150, 480);
      this.drop(x, y, Math.cos(a) * sp, Math.sin(a) * sp, uniform(0.25, 0.5), uniform(2, 4), color);
    }
  }

  /** Dark casing fragments of a bomb: tumbling polygons with gravity and a cooling hot edge. */
  shards(x, y, n = 10) {
    for (let i = 0; i < n; i++) {
      const a = uniform(0, TAU), sp = uniform(350, 900);
      const p = this.add(x, y, Math.cos(a) * sp, Math.sin(a) * sp - 250, uniform(0.9, 1.4), uniform(6, 13), [255, 120, 40], "shard", 1.0);
      if (p) {
        p.vr = uniform(-720, 720);
        const m = randint(4, 6);
        p.shape = Array.from({ length: m }, (_, k) => [uniform(0.45, 1.0), (k * TAU) / m + uniform(-0.3, 0.3)]);
      }
    }
  }

  embers(x, y, n = 40, speed = 650) {
    const cols = [[255, 150, 50], [255, 190, 90], [255, 110, 30]];
    for (let i = 0; i < n; i++) {
      const a = uniform(0, TAU), sp = uniform(0.15, 1) * speed;
      this.add(x, y, Math.cos(a) * sp, Math.sin(a) * sp - 120, uniform(0.7, 1.6), uniform(1.5, 3), choice(cols), "ember", 0.35);
    }
  }

  /** Dust hanging in the lantern light: tiny, slow, twinkling. `box` is the area to scatter it over. */
  mote(box = { x: 0, y: 0, w: W, h: H }) {
    const cols = [[255, 214, 160], [230, 200, 170], [255, 190, 130]];
    const p = this.add(box.x + uniform(0, box.w), box.y + uniform(0, box.h), uniform(-8, 8), uniform(-10, 4), uniform(7, 13),
      choice([1, 1, 2]), choice(cols), "mote", 0.0);
    if (p) p.vr = uniform(1.5, 4.0); // twinkle rate
  }

  lanternEmber(box = { x: 0, w: W, bottom: H }) {
    const p = this.add(box.x + uniform(box.w * 0.05, box.w * 0.95), box.bottom + 10, uniform(-20, 20), uniform(-110, -60),
      uniform(4, 7), 2, [255, 140, 50], "ember", -0.01);
    if (p) p.vr = uniform(2, 5);
  }

  update(dt) {
    const alive = [];
    for (const p of this.items) {
      p.life -= dt;
      if (p.life <= 0) continue;
      const k = p.kind;
      p.vy += GRAVITY * p.grav * dt;
      if (k === "smoke") {
        p.vx *= 0.96; p.vy *= 0.96; p.size += 18 * dt;
      } else if (k === "drop") {
        const d = 1 - 0.8 * dt; // a little air drag so sprays curl over instead of flying straight
        p.vx *= d; p.vy *= d;
      } else if (k === "ember") {
        const d = 1 - 1.5 * dt;
        p.vx = p.vx * d + Math.sin(p.life * 3 + p.rot) * 40 * dt;
        p.vy *= d;
      } else if (k === "mote") {
        p.vx += Math.sin(p.life * 0.7 + p.rot) * 6 * dt;
        p.vy += Math.cos(p.life * 0.5 + p.rot) * 4 * dt;
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      if (k !== "mote" && k !== "ember") p.rot += p.vr * dt;
      if (p.y < H + 60) alive.push(p);
    }
    this.items = alive;
  }

  draw(L, add) {
    L.lineCap = "round";
    for (const p of this.items) {
      const k = p.kind, t = p.life / p.max;
      if (k === "drop") this.drawDrop(L, p, t);
      else if (k === "mote") {
        const tw = 0.55 + 0.45 * Math.sin(p.life * p.vr + p.rot);
        const fade = Math.min(1, t * 4, (1 - t) * 4);
        add.fillStyle = rgb(shade(p.color, 0.5 * tw * fade));
        add.fillRect(p.x, p.y, p.size, p.size);
      } else if (k === "spark") {
        line(add, p.x, p.y, p.x - p.vx * 0.03, p.y - p.vy * 0.03, shade(p.color, t), Math.max(1, Math.trunc(p.size)));
      } else if (k === "ember") {
        const fl = (0.7 + 0.3 * Math.sin(p.life * 23 + p.rot)) * Math.min(1, t * 2.5);
        addGlow(add, 9, p.color, fl * 0.45, p.x, p.y);
        add.fillStyle = rgb(tint(shade(p.color, fl), 0.3 * fl));
        add.fillRect(p.x - 1, p.y - 1, p.size, p.size);
      } else if (k === "glow") {
        // peaks mid-life, once it has drifted off the fruit, so the fruit itself doesn't light up
        addGlow(add, p.size, p.color, 0.45 * t * Math.min(1, (1 - t) * 2.5), p.x, p.y);
      } else if (k === "shard") this.drawShard(L, add, p, t);
      else if (k === "sheet") this.drawSheet(L, p, t);
      else if (k === "splash") {
        const u = 1 - t;
        const g = (1 + 0.25 * (1 - (1 - u) ** 3)) / 1.25; // grows to 1.25x, ease-out
        const { img, angle, scale } = p.shape;
        L.save();
        L.translate(p.x, p.y);
        L.rotate(rad(-angle));
        L.scale(scale * g, scale * g);
        L.globalAlpha = (230 / 255) * (1 - u * u); // fades out, ease-in
        L.drawImage(img, -img.width / 2, -img.height / 2);
        L.restore();
      } else if (k === "smoke") {
        const img = softImg(p.size, p.color);
        L.globalAlpha = t;
        L.drawImage(img, p.x - img.width / 2, p.y - img.height / 2);
        L.globalAlpha = 1;
      }
    }
  }

  drawDrop(L, p, t) {
    let col = p.color, c2 = p.c2, r;
    if (p.size >= 2.8) { // heavy drop: shrinks away and sinks into the dark wall instead of popping off
      r = p.size * t ** 0.6;
      col = shade(col, 0.35 + 0.65 * t); c2 = shade(c2, 0.35 + 0.65 * t);
    } else r = p.size * (0.4 + 0.6 * t);
    const vx = p.vx, vy = p.vy;
    const sp = Math.hypot(vx, vy) || 1;
    const dx = vx / sp, dy = vy / sp;
    const Ln = Math.max(2.0, sp * 0.018 * this.blur);
    const tx = p.x - dx * Ln, ty = p.y - dy * Ln;
    if (r < 1.2) { line(L, tx, ty, p.x, p.y, col, 2); return; }
    const css = rgb(col);
    if (r >= 2.2) { // heavy drop: round head, short tail with a rounded end (a pointed one reads as an arrow)
      const tl = r * 0.8 + Math.min(Ln, r * 2.5), tr = r * 0.45;
      const hx = p.x - dx * tl, hy = p.y - dy * tl;
      polygon(L, [[p.x - dy * r, p.y + dx * r], [hx - dy * tr, hy + dx * tr], [hx + dy * tr, hy - dx * tr], [p.x + dy * r, p.y - dx * r]], css);
      circle(L, hx, hy, tr, css);
      circle(L, p.x, p.y, r, css);
      circle(L, p.x - r * 0.3, p.y - r * 0.35, r * 0.45, rgb(c2)); // lit side of the bead
      circle(L, p.x - r * 0.38, p.y - r * 0.42, Math.max(1, r * 0.16), rgb(tint(col, 0.8)));
      return;
    }
    // velocity-stretched capsule: round head, thinner tail, light core line along it
    line(L, tx, ty, p.x, p.y, css, Math.max(2, Math.trunc(r * 1.7)));
    circle(L, p.x, p.y, r, css);
    circle(L, tx, ty, r * 0.6, css);
    line(L, tx, ty, p.x - (vx / sp) * r * 0.4, p.y - (vy / sp) * r * 0.4, rgb(c2), Math.max(1, Math.trunc(r * 0.5)));
  }

  drawShard(L, add, p, t) {
    const a = rad(p.rot);
    const pts = p.shape.map(([rr, aa]) => [p.x + Math.cos(a + aa) * rr * p.size, p.y + Math.sin(a + aa) * rr * p.size]);
    polygon(L, pts, "rgb(34,32,36)");
    const glint = 45 + Math.trunc(70 * Math.abs(Math.cos(a * 2))); // one facet catching the lantern light as it tumbles
    line(L, pts[0][0], pts[0][1], pts[1][0], pts[1][1], `rgb(${glint},${glint - 4},${glint - 10})`, 2);
    const heat = t * t;
    if (heat > 0.05) line(add, pts[1][0], pts[1][1], pts[2][0], pts[2][1], shade(p.color, heat * 0.7), 2); // still hot, cooling as it flies
  }

  /** The translucent fan of juice torn off the cut face: grows outward from the cut line, fades fast. */
  drawSheet(L, p, t) {
    const [ux, uy, nx, ny] = p.shape;
    const age = p.max - p.life;
    const h = p.size / 2, d = 6 + 520 * age;
    const pts = [[p.x - ux * h, p.y - uy * h]];
    for (let i = 1; i < 8; i++) {
      const u = (i / 8) * 2 - 1;
      const reach = d * Math.sqrt(1 - u * u);
      pts.push([p.x + ux * h * u * (1 + age * 3) + nx * reach, p.y + uy * h * u * (1 + age * 3) + ny * reach]);
    }
    pts.push([p.x + ux * h, p.y + uy * h]);
    polygon(L, pts, rgba(p.color, (110 * t) / 255));
  }
}

// ---------------- stains ----------------

const STAIN_CACHE = new Map();

/** A juice splash: a translucent tinted blob with a darker rim where the juice pools, a few specular glints. */
function wetStain(color, r, variant) {
  const key = `${color}|${r}|${variant}`;
  let v = STAIN_CACHE.get(key);
  if (v) return v;
  const k = 2; // supersample
  const size = Math.trunc(r * 5), hgt = Math.trunc(r * 6.2);
  const s = makeCanvas(size * k, hgt * k), g = getCtx(s);
  const c = size / 2;
  const blobs = [[c, c, r * 0.72]];
  for (let i = 0, n = randint(8, 12); i < n; i++) {
    const a = uniform(0, TAU), d = uniform(0.35, 0.85) * r;
    blobs.push([c + Math.cos(a) * d, c + Math.sin(a) * d, uniform(0.18, 0.36) * r]);
  }
  for (let i = 0, n = randint(14, 22); i < n; i++) { // small lobes break up the edge so it isn't a ring of bubbles
    const a = uniform(0, TAU), d = uniform(0.8, 1.2) * r;
    blobs.push([c + Math.cos(a) * d, c + Math.sin(a) * d, uniform(0.04, 0.12) * r]);
  }
  const flecks = [];
  for (let i = 0, n = randint(14, 24); i < n; i++) { // fine spatter thrown further out
    const a = uniform(0, TAU), d = uniform(1.25, 2.2) * r;
    flecks.push([c + Math.cos(a) * d, c + Math.sin(a) * d, uniform(0.025, 0.07) * r]);
  }
  const rim = rgba(shade(color, 0.4), 225 / 255), body = rgba(shade(color, 0.85), 120 / 255);
  for (const [x, y, br] of [...blobs, ...flecks]) circle(g, x * k, y * k, (br + Math.max(1.5, br * 0.16)) * k, rim);
  for (const [x, y, br] of blobs) circle(g, x * k, y * k, br * k, body);
  const sample = [...blobs.slice(0, 12)].sort(() => Math.random() - 0.5).slice(0, randint(2, 4));
  for (const [x, y, br] of sample) { // glints up-left: the lanterns are above
    circle(g, (x - br * 0.35) * k, (y - br * 0.4) * k, Math.max(1.2, br * 0.13) * k, "rgba(255,248,235,0.47)");
    circle(g, (x - br * 0.37) * k, (y - br * 0.42) * k, Math.max(0.8, br * 0.06) * k, "rgba(255,255,255,0.9)");
  }
  const img = makeCanvas(size, hgt);
  const ig = getCtx(img);
  ig.imageSmoothingQuality = "high";
  ig.drawImage(s, 0, 0, size, hgt);
  const drips = [];
  for (let i = 0, n = randint(2, 4); i < n; i++) {
    drips.push([c + uniform(-0.55, 0.55) * r, c + r * 0.3, uniform(0.6, 1.8) * r, uniform(0.06, 0.11) * r]);
  }
  v = { img, drips };
  if (STAIN_CACHE.size > 120) STAIN_CACHE.clear();
  STAIN_CACHE.set(key, v);
  return v;
}

/** Wet juice splashes on the dojo wall: drips run down for 1.2 s, then the stain fades over 8 s. */
export class Stains {
  constructor() {
    this.GROW = 1.2; this.FADE = 8.0;
    this.items = [];
  }

  add(color, r, x, y) {
    const { img, drips } = wetStain(color, r, randint(0, 2));
    const own = makeCanvas(img.width, img.height); // each stain grows its own drips
    this.items.push({ base: img, own, drips, x, y, age: 0, col: rgba(shade(color, 0.6), 170 / 255), dirty: true });
    if (this.items.length > 30) this.items.shift();
  }

  update(dt) {
    for (const s of this.items) s.age += dt;
    this.items = this.items.filter((s) => s.age < this.GROW + this.FADE);
  }

  draw(L) {
    for (const s of this.items) {
      if (s.age < this.GROW + 0.05 || s.dirty) { // drips only grow, so redrawing base + drips each frame is idempotent
        s.dirty = false;
        const g = getCtx(s.own);
        g.clearRect(0, 0, s.own.width, s.own.height);
        g.drawImage(s.base, 0, 0);
        const e = 1 - (1 - Math.min(1, s.age / this.GROW)) ** 3;
        for (const [dx, dy, Ln, wd] of s.drips) {
          const end = dy + Ln * e;
          const tip = wd * (1 - 0.35 * e); // a running drip thins as it goes, then beads at the end
          polygon(g, [[dx - wd, dy], [dx + wd, dy], [dx + tip, end], [dx - tip, end]], s.col);
          circle(g, dx, end, tip * 1.35, s.col);
        }
      }
      const k = s.age < this.GROW ? 0 : (s.age - this.GROW) / this.FADE;
      L.globalAlpha = 1 - k * k;
      L.drawImage(s.own, Math.round(s.x - s.own.width / 2), Math.round(s.y - s.own.width / 2));
    }
    L.globalAlpha = 1;
  }
}

// ---------------- blade trail ----------------

export class Trail {
  constructor() {
    this.LIFE = 0.13;
    this.pts = [];
  }
  add(x, y, t) { this.pts.push([x, y, t]); }
  cut() { this.pts.push(null); } // break between swipes
  update(now) {
    while (this.pts.length && (this.pts[0] === null || now - this.pts[0][2] > this.LIFE)) this.pts.shift();
  }
  runs() {
    const runs = [];
    let cur = [];
    for (const p of this.pts) {
      if (p === null) { runs.push(cur); cur = []; } else cur.push(p);
    }
    runs.push(cur);
    return runs.filter((r) => r.length >= 2);
  }

  /** Smoothed ribbon: a halo, a blade-coloured body and a core (an optional 4th colour replaces the white core). */
  draw(ctx, colors, now, outer = true) {
    const op = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = "source-over"; // each narrower layer replaces the wider one under it (halo, body, core)
    const core = colors.length > 3 ? colors[3] : [255, 255, 255];
    const layers = (outer ? [[colors[0], 18]] : []).concat([[colors[1], 12], [core, 4.5]]);
    for (let run of this.runs()) {
      run = catmullRom(run, 4);
      const n = run.length;
      for (const [color, width] of layers) {
        const left = [], right = [];
        for (let i = 0; i < n; i++) {
          const [x, y, t] = run[i];
          const a = run[Math.max(0, i - 1)], b = run[Math.min(n - 1, i + 1)];
          const dx = b[0] - a[0], dy = b[1] - a[1];
          const L = Math.hypot(dx, dy) || 1;
          const age = 1 - (now - t) / this.LIFE;
          const w = width * Math.max(0, age) * (i / (n - 1)) ** 0.6;
          left.push([x - (dy / L) * w, y + (dx / L) * w]);
          right.push([x + (dy / L) * w, y - (dx / L) * w]);
        }
        polygon(ctx, left.concat(right.reverse()), color);
        const hw = Math.hypot(left[n - 1][0] - right[0][0], left[n - 1][1] - right[0][1]) / 2; // round the leading edge
        if (hw >= 1) circle(ctx, run[n - 1][0], run[n - 1][1], hw, color);
      }
    }
    ctx.globalCompositeOperation = op;
  }
}

// ---------------- screen shake ----------------

export class Shake {
  constructor() { this.trauma = 0; this.t = 0; }
  kick(amount) { this.trauma = Math.min(1, this.trauma + amount); }
  update(dt) { this.t += dt; this.trauma = Math.max(0, this.trauma - dt * 1.6); }
  offset() {
    const k = this.trauma ** 2 * 26;
    return [k * Math.sin(this.t * 71.3) * Math.cos(this.t * 13.1), k * Math.sin(this.t * 59.7 + 1.3)];
  }
}

// ---------------- popups and stamps ----------------

/** Floating score numbers: Barlow numerals with a soft shadow, rising and fading. */
export class Popups {
  constructor(fonts) { this.fonts = fonts; this.items = []; }
  add(text, x, y, color = WASHI, big = false) {
    const f = this.fonts, font = big ? f.bonus : f.pop;
    this.items.push({ text, font, color, x, y, age: 0 });
  }
  update(dt) {
    for (const p of this.items) { p.y -= 60 * dt; p.age += dt; }
    this.items = this.items.filter((p) => p.age < 0.9);
  }
  draw(ui) {
    const f = this.fonts;
    for (const p of this.items) {
      const a = Math.min(1, p.age / 0.05, (0.9 - p.age) / 0.4);
      const k = 1 + Math.max(0, 0.12 - p.age) * 2.5; // a short pop in
      for (const [img, dy] of [[f.shadow(p.font, p.text), 3], [f.text(p.font, p.text, p.color), 0]]) {
        const w = img.lw * k, h = img.lh * k;
        blit(ui, img, p.x - w / 2, p.y + dy - h / 2, a, k);
      }
    }
  }
}

/** Seal drop: 1.8 -> 1.0 in 0.11 s, accelerating like a hand pressing down, then a 0.92 undershoot as the stone
 * bites, settling back to 1.0. */
export function stampScale(age) {
  if (age < 0.11) { const u = age / 0.11; return 1.8 - 0.8 * u * u; }
  if (age < 0.16) { const u = (age - 0.11) / 0.05; return 1.0 - 0.08 * (1 - (1 - u) ** 2); }
  if (age < 0.28) { const u = (age - 0.16) / 0.12; return 0.92 + 0.08 * u * u * (3 - 2 * u); }
  return 1.0;
}

/** A hanko seal that slams onto the screen over its own ink bleed. The game's signature beat. */
export class Stamp {
  constructor(art, glyph, caption, x, y, size = 120, color = WASHI, bonus = null, hold = false) {
    this.DUR = 1.4; this.LAND = 0.11;
    const f = art.fonts;
    this.fonts = f;
    this.seal = art.seal(glyph, size);
    this.blot = art.blot(size);
    this.caption = caption; this.bonus = bonus; this.color = color;
    const cw = (caption ? f.text(f.caption, caption, color, 2).lw : 0) + (bonus ? f.text(f.bonus, bonus, GOLD).lw + 14 : 0);
    const mx = Math.max(size * 0.8, cw / 2 + 24);
    this.x = Math.min(Math.max(x, mx), W - mx);
    this.y = Math.min(Math.max(y, size * 0.75), H - size * 0.5 - 80);
    this.size = size;
    this.rot = uniform(-6, 6);
    this.age = 0;
    this.landed = false;
    this.hold = hold; // stays on screen (results) instead of fading after DUR
  }

  update(dt) {
    this.age += dt;
    return this.hold || this.age < this.DUR;
  }

  draw(ui) {
    const a = this.age, f = this.fonts;
    const fade = this.hold ? 1.0 : Math.min(1.0, (this.DUR - a) / 0.35);
    if (a >= this.LAND) { // the ink bleeds out from under the stone on impact
      const u = Math.min(1.0, (a - this.LAND) / 0.12);
      const k = 0.82 + 0.18 * (1 - (1 - u) ** 3);
      ui.save();
      ui.translate(this.x, this.y);
      ui.rotate(rad(-this.rot * 0.5));
      ui.scale(k, k);
      ui.globalAlpha = 0.6 * fade;
      ui.drawImage(this.blot, -this.blot.width / 2, -this.blot.height / 2);
      ui.restore();
    }
    const k = stampScale(a);
    ui.save();
    ui.translate(this.x, this.y);
    ui.rotate(rad(-this.rot));
    ui.scale(k, k);
    ui.globalAlpha = Math.min(1.0, a / 0.05, fade);
    ui.drawImage(this.seal, -this.seal.width / 2, -this.seal.height / 2);
    ui.restore();
    if (this.caption && a > 0.14) {
      const u = Math.min(1.0, (a - 0.14) / 0.2);
      const alpha = Math.min(u, fade);
      const y = this.y + this.size * 0.5 + 34 + 8 * (1 - u) ** 2;
      const cap = f.text(f.caption, this.caption, this.color, 2);
      const bon = this.bonus ? f.text(f.bonus, this.bonus, GOLD) : null;
      let x = this.x - (cap.lw + (bon ? bon.lw + 14 : 0)) / 2;
      for (const [img, sh] of [[cap, f.shadow(f.caption, this.caption, 2)], [bon, bon ? f.shadow(f.bonus, this.bonus) : null]]) {
        if (!img) continue;
        const r = rectAt(img.lw, img.lh, "midleft", [x, y]);
        blit(ui, sh, r.centerx - sh.lw / 2, r.centery + 3 - sh.lh / 2, alpha);
        blit(ui, img, r.x, r.y, alpha);
        x = r.right + 14;
      }
    }
  }
}
