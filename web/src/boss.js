// Boss fruit: how it looks and the hooks Play calls (ninja/boss.py). The rules (hp, phases, when one appears) are in
// rules/boss.js. The boss is never in World.bodies, so Shadow Clones and Dragon Fire never target it, and Time Stop
// leaves it alone: the world (boss included) is frozen and slicing is blocked while time is held.
import { REGULAR, WEIGHTS } from "./config.js";
import { uniform, weighted, shade, rgb, seeded, TAU } from "./util.js";
import { makeCanvas, getCtx, makeShadow, blurCanvas, polygon, line, drawSprite, addGlow } from "./gfx.js";
import { segHitsCircle } from "./rules/collide.js";
import {
  Boss, BossDirector, BossHalf, CRACK_AT, CROWN, SPARK, BONUS, DEATH, STAMP_DELAY, easeOut3,
} from "./rules/boss.js";
import { feverCut } from "./fever.js";

/** A boss with its sprite, cracks and the split into two flying halves. */
class DrawnBoss extends Boss {
  constructor(art, name, x = null) {
    super(art, name, x);
    this.imgs = null; // stage -> [sprite with cracks, emissive crack glow or null]
  }

  /** [sprite with this stage's cracks, the cracks' emissive glow]; every stage is built on the first call, so the
   * cracks opening mid-fight never cost a frame. */
  images() {
    if (!this.imgs) {
      const base = this.art.boss[this.name];
      const w = base.width, h = base.height;
      this.shadow = makeShadow(base, 110);
      this.white = this.silhouette(base, "#fff", true); // white x coverage on black: ready to add as light
      const g = getCtx(makeCanvas(w, h));
      g.drawImage(base, 0, 0);
      const px = g.getImageData(0, 0, w, h).data;
      const top = Math.trunc(h * CROWN[this.name]); // rind only: the stem and leaves take no cracks
      this.inside = (x, y) => x >= 0 && y >= top && x < w && y < h && px[(y * w + x) * 4 + 3] > 200;
      const rng = seeded(this.name); // the same cracks every time
      this.cracks = Array.from({ length: 6 }, (_, i) => this.makeCrack(rng, base, 0.55 + 0.25 * i));
      this.imgs = { 0: [base, null], 1: this.cracked(base, this.cracks.slice(0, 3)), 2: this.cracked(base, this.cracks.slice(0, 6)) };
    }
    return this.imgs[this.stage];
  }

  silhouette(base, color, onBlack = false) {
    const c = makeCanvas(base.width, base.height), g = getCtx(c);
    if (onBlack) { g.fillStyle = "#000"; g.fillRect(0, 0, c.width, c.height); }
    const s = makeCanvas(base.width, base.height), sg = getCtx(s);
    sg.drawImage(base, 0, 0);
    sg.globalCompositeOperation = "source-in";
    sg.fillStyle = color;
    sg.fillRect(0, 0, s.width, s.height);
    g.drawImage(s, 0, 0);
    return c;
  }

  /** A jagged fissure from the rind toward the middle, with a short branch: [main polyline, branch]. */
  makeCrack(rng, base, reach) {
    const w = base.width, h = base.height;
    const cx = w / 2, cy = h / 2;
    let px = cx, py = cy;
    for (let n = 0; n < 40; n++) {
      const a = rng.uniform(0, TAU);
      px = cx + Math.cos(a) * w * 0.4; py = cy + Math.sin(a) * h * 0.4;
      while (Math.hypot(px - cx, py - cy) > 10 && !this.inside(Math.trunc(px), Math.trunc(py))) {
        px += (cx - px) * 0.06; py += (cy - py) * 0.06;
      }
      if (this.inside(Math.trunc(px), Math.trunc(py))) break;
    }
    let heading = Math.atan2(cy - py, cx - px) + rng.uniform(-0.5, 0.5);
    const main = [[px, py]];
    let length = this.r * reach * rng.uniform(0.8, 1.15);
    while (length > 0) {
      heading += rng.uniform(-0.55, 0.55);
      const step = rng.uniform(8, 15);
      px += Math.cos(heading) * step; py += Math.sin(heading) * step;
      if (!(px >= 0 && px < w && py >= 0 && py < h) || !this.inside(Math.trunc(px), Math.trunc(py))) break;
      main.push([px, py]);
      length -= step;
    }
    const lines = [main];
    if (main.length > 4) {
      let [bx, by] = main[rng.randint(1, main.length - 3)];
      let heading2 = heading + (rng.next() < 0.5 ? -1 : 1) * rng.uniform(0.6, 1.0);
      const branch = [[bx, by]];
      for (let i = 0, n = rng.randint(2, 4); i < n; i++) {
        heading2 += rng.uniform(-0.5, 0.5);
        bx += Math.cos(heading2) * rng.uniform(7, 12); by += Math.sin(heading2) * rng.uniform(7, 12);
        if (!(bx >= 0 && bx < w && by >= 0 && by < h) || !this.inside(Math.trunc(bx), Math.trunc(by))) break;
        branch.push([bx, by]);
      }
      lines.push(branch);
    }
    return lines;
  }

  /** Dark fissures (tapering, with a pale lip catching the light) and their glow: the flesh showing through. */
  cracked(base, cracks) {
    const w = base.width, h = base.height;
    const dark = makeCanvas(w, h), dg = getCtx(dark);
    const lit = makeCanvas(w, h), lg = getCtx(lit);
    lg.fillStyle = "#000"; lg.fillRect(0, 0, w, h);
    dg.lineCap = lg.lineCap = "round";
    for (const crack of cracks) {
      crack.forEach((ln, k) => {
        const n = ln.length;
        for (let i = 0; i < n - 1; i++) {
          const [a, b] = [ln[i], ln[i + 1]];
          const taper = 1 - i / Math.max(1, n - 1);
          const wd = Math.max(1, Math.round((k === 0 ? 7 : 4) * (0.3 + 0.7 * taper)));
          line(dg, a[0] - 1, a[1] - 1, b[0] - 1, b[1] - 1, "rgba(255,238,210,0.18)", wd);
          line(dg, a[0], a[1], b[0], b[1], "rgba(22,12,6,0.92)", wd);
          if (wd >= 3) line(lg, a[0], a[1], b[0], b[1], rgb(shade(this.flesh, 0.55)), Math.max(1, wd - 4)); // the flesh glows only deep in the wider fissures
        }
      });
    }
    dg.globalCompositeOperation = "destination-in"; // never past the rind
    dg.drawImage(base, 0, 0);
    const img = makeCanvas(w, h), ig = getCtx(img);
    ig.drawImage(base, 0, 0);
    ig.drawImage(dark, 0, 0);
    const soft = blurCanvas(lit, 2);
    const sg = getCtx(soft);
    sg.globalCompositeOperation = "lighter";
    sg.drawImage(lit, 0, 0);
    sg.globalCompositeOperation = "multiply";
    sg.drawImage(this.white, 0, 0);
    return [img, soft];
  }

  /** The killing cut: the boss (as it looks now) in two halves along the slash, flung apart. */
  split(dx, dy) {
    this.cut = [this.x, this.y, dx, dy];
    if (!this.art) return;
    const src = this.images()[0];
    const pad = Math.ceil(Math.hypot(src.width, src.height) * this.scale);
    const w = pad, h = pad;
    const img = makeCanvas(w, h);
    drawSprite(getCtx(img), src, w / 2, h / 2, this.ang, this.scale);
    const cx = w / 2, cy = h / 2, nx = -dy, ny = dx, big = w + h;
    for (const side of [1, -1]) {
      const sx = nx * side, sy = ny * side;
      const half = makeCanvas(w, h), hg = getCtx(half);
      hg.drawImage(img, 0, 0);
      hg.globalCompositeOperation = "destination-out";
      polygon(hg, [[cx + dx * big, cy + dy * big], [cx - dx * big, cy - dy * big],
        [cx - dx * big - sx * big, cy - dy * big - sy * big], [cx + dx * big - sx * big, cy + dy * big - sy * big]], "#000");
      hg.globalCompositeOperation = "source-over";
      const edge = makeCanvas(w, h), eg = getCtx(edge); // the cut face: wet flesh along the chord
      const a = [cx - dx * big, cy - dy * big], b = [cx + dx * big, cy + dy * big];
      line(eg, a[0], a[1], b[0], b[1], rgb(shade(this.flesh, 0.8)), 9);
      line(eg, a[0], a[1], b[0], b[1], rgb(this.flesh), 4);
      eg.globalCompositeOperation = "destination-in";
      eg.drawImage(half, 0, 0);
      hg.drawImage(edge, 0, 0);
      this.halves.push(new BossHalf(half, this.x + sx * 8, this.y + sy * 8, sx * uniform(340, 420) + dx * 120,
        sy * 340 - 300, side * uniform(90, 160)));
    }
  }

  draw(L, add) {
    if (!this.art) return;
    if (this.phase === "dead") { this.drawDeath(L, add); return; }
    const [img, lit] = this.images();
    const a = this.hitAge;
    const rec = 12 * Math.exp(-a * 14) * Math.cos(a * 42); // knocked along the slash, ringing back
    const ang = this.ang + 5 * Math.exp(-a * 10) * Math.sin(a * 36) * (this.hitDir[0] >= 0 ? 1 : -1);
    const x = this.x + this.hitDir[0] * rec, y = this.y + this.hitDir[1] * rec;
    const s = this.scale * (1 - 0.035 * Math.exp(-a * 16));
    drawSprite(L, this.shadow, x + 22, y + 34, ang, 1);
    drawSprite(L, img, x, y, ang, s);
    if (lit) drawSprite(add, lit, x, y, ang, s);
    if (this.flash > 0.02) drawSprite(add, this.white, x, y, ang, s, (70 * this.flash ** 2) / 255); // the hit lands as light on the rind
  }

  drawDeath(L, add) {
    const fade = Math.max(0, Math.min(1, (DEATH - this.deadT) / 0.4));
    for (const h of this.halves) drawSprite(L, h.img, h.x, h.y, h.ang, 1, fade);
    const u = this.deadT / 0.3;
    if (this.cut && u < 1) { // the killing stroke: a long blade of light across the whole fruit
      const [x, y, dx, dy] = this.cut;
      const k = (1 - u) ** 2, reach = this.r * (2.2 + 1.2 * easeOut3(u));
      const a = [x - dx * reach, y - dy * reach], b = [x + dx * reach, y + dy * reach];
      addGlow(add, this.r * 1.4, this.flesh, 0.5 * k, x, y);
      for (const [col, wd] of [[[255, 190, 120], 9], [[255, 250, 236], 2.5]]) { // a lens of light: widest mid-fruit
        const ex = -dy * wd * k, ey = dx * wd * k;
        polygon(add, [a, [x + ex, y + ey], b, [x - ex, y - ey]], shade(col, k));
      }
    }
  }
}

export const makeBossDirector = () => new BossDirector(45.0, 45.0, (art, name) => new DrawnBoss(art, name));

// ---------------- Play hooks ----------------

/** Once a frame (outside hit-stop), `dt` in world time: Time Stop holds the boss and its timers. */
export function tickBoss(play, dt) {
  const d = play.boss;
  if (!d) return;
  if (play.state === "dying" || play.state === "ending" || play.state === "over") d.close();
  else if (play.state === "play") d.update(play.elapsed, play);
  for (const b of [d.active, d.leaving]) {
    if (b) {
      b.update(dt);
      if (b.burst) burst(play, b);
      if (b.seal && b.deadT >= STAMP_DELAY) seal(play, b);
    }
  }
  if (d.leaving && d.leaving.done) d.leaving = null;
}

/** Each slice segment crossing the boss is one hit (at most one per COOLDOWN). */
export function sliceBoss(play) {
  const d = play.boss;
  const b = d ? d.active : null;
  if (!b || play.state !== "play" || (play.power && play.power.blocksSlicing)) return;
  for (const seg of play.app.segments) {
    const [ax, ay, bx, by] = seg;
    if (segHitsCircle(ax, ay, bx, by, b.x, b.y, b.r) && b.hit(play.app.now, bx - ax, by - ay)) {
      strike(play, b, seg);
      if (b.phase === "dead") { defeat(play, b); return; }
    }
  }
}

function closest(seg, x, y) {
  const [ax, ay, bx, by] = seg;
  const dx = bx - ax, dy = by - ay;
  const L2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / L2));
  return [ax + dx * t, ay + dy * t];
}

function strike(play, b, seg) {
  const w = play.w;
  feverCut(play); // each hit grows the chain, like a cut
  const pts = play.fever ? play.fever.points(1) : 1;
  play.addScore(pts);
  const [px, py] = closest(seg, b.x, b.y);
  b.tally += pts; b.tallyT = 0; // shown by the HUD as one growing "+N" by the boss
  w.hitstop = Math.max(w.hitstop, 0.03);
  w.shake.kick(0.15);
  w.cutHeat += 0.5;
  const lod = Math.min(1.0, w.HEAT_LOD / Math.max(1.0, w.cutHeat));
  const [dx, dy] = b.hitDir;
  w.particles.sparks(px, py, SPARK, Math.round(11 * lod), 720, 0.35);
  w.particles.sparks(px, py, [255, 176, 90], Math.round(4 * lod), 420, 0.3);
  w.particles.juice(px, py, b.flesh, -dy, dx, 10, 18, lod * 0.6); // chips of flesh off the rind
  w.particles.add(px, py, 0, 0, 0.12, 40, SPARK, "glow", 0.0); // the contact itself, a pop of light
  if (CRACK_AT.includes(b.hp)) { // the rind gives: a heavier jolt as the cracks open
    w.shake.kick(0.2);
    w.particles.juice(b.x, b.y, b.flesh, -dy, dx, 24, b.r * 0.5, lod);
  }
  play.app.audio.play("boss_hit");
}

function defeat(play, b) {
  const w = play.w;
  const [x, y, dx, dy] = b.cut;
  w.flash = Math.max(w.flash, 0.6);
  w.hitstop = Math.max(w.hitstop, 0.12);
  w.shake.kick(0.6);
  w.zoomPunch(1.035);
  w.shocks.push([x, y, 0.0]);
  w.particles.splash(x, y, b.flesh, -dy, dx, b.r * 0.7);
  for (const o of [-0.6, 0.0, 0.6]) w.particles.juice(x + dx * b.r * o, y + dy * b.r * o, b.flesh, -dy, dx, 24, 30); // juice off the whole length of the cut
  w.particles.sparks(x, y, SPARK, 40, 1000, 0.6);
  w.stains.add(b.flesh, b.r, x, y);
  b.burst = true; // the fruit burst comes as the hit-stop lets go (tickBoss), not into the blade still in the cut
  const bonus = play.fever ? play.fever.points(BONUS) : BONUS;
  play.addScore(bonus);
  b.seal = `+${bonus}`; // the stamp waits for the burst to clear (tickBoss)
  play.app.audio.play("boss_roar");
}

/** The seal where the boss was: by now the burst has flown out past the rim and the halves have parted. */
function seal(play, b) {
  const [x, y] = b.cut;
  play.w.stamp("討", "Boss down", x, y - 20, 140, undefined, b.seal);
  b.seal = null;
}

/** The boss bursts into 12 regular fruit flung outward: cuttable, and never a lost life. */
function burst(play, b) {
  b.burst = false;
  const [x, y] = b.cut;
  for (let i = 0; i < 12; i++) {
    const a = -Math.PI / 2 + ((i - 5.5) / 12) * Math.PI * 1.7 + uniform(-0.1, 0.1);
    const sp = uniform(560, 900);
    const f = play.w.throw(weighted(REGULAR, WEIGHTS), x + Math.cos(a) * b.r * 0.6, y + Math.sin(a) * b.r * 0.6,
      Math.cos(a) * sp, Math.sin(a) * sp - 180);
    f.rain = true;
  }
}
