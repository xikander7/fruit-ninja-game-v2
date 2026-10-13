// title.js - the animated title shown at the top of the menu.
// It is a short scripted animation, driven by one timer `t`: every constant below is a moment (in seconds) on that
// timeline. Nothing here is physics except the cut itself, which reuses World.cut from world.js.
//
// The menu's title intro: a watermelon is tossed up, cut at its apex, and the game name is signed in its juice
// (ninja/title.py). Plays once per Menu entry (~1.6 s), skippable; afterwards the name holds with a slow light
// sweep now and then. The name is art on the wall (drawn into the world layer, so the juice droplets fly over it);
// the subtitle and the seal are UI.
import { W, H, FRUITS, WASHI, GOLD, HANKO, BLADES, TITLE, SUBTITLE } from "./config.js";
import { shade, rgb, rgba, easeOut, rad } from "./util.js";
import { makeCanvas, getCtx, blurCanvas, polygon, circle } from "./gfx.js";
import { stampScale } from "./fx.js";
import { label, rectAt } from "./ui.js";

// Timeline (seconds from the start). *_AT = when a step begins; the other number = how long it lasts.
const TOSS = 0.42; // s: the melon rises from below the screen to its apex, where the blade meets it
const SLASH = 0.32; // s the blade streak takes to draw across and burn out
const REVEAL_AT = 0.5, REVEAL = 0.5; // the name is signed left to right
const SWASH_AT = 0.86, SWASH = 0.26; // the brush underline
const SUB_AT = 0.98, SUB = 0.38; // the subtitle slides in
const SEAL_AT = 1.22; // the hanko lands
export const DONE = 1.6; // settled
const SETTLE = 0.9; // s for the wet juice under the name to dry back
const SWEEP_FIRST = 2.0, SWEEP_EVERY = 6.0, SWEEP = 0.9; // idle light sweep
// Layout: CY = vertical centre of the title text, APEX = height where the melon is cut.
const CY = 118; // the name's centre line
const APEX = 124;
// The title leans to the right like brush handwriting: each pixel of height shifts the text sideways by 0.17px.
const SLANT = 0.17; // signature lean (horizontal px per px of height)
const EDGE = 36; // px of feathered edge on the brush's leading front
const TITLE_MAX_W = W - 2 * (24 + 4 + 44); // stage margin + seal gap + 44 px seal, on both sides for centring

/** The name drawn in `color`, sheared to the right (the signature lean): x moves right by (h - y) * SLANT. */
function slantedText(fonts, text, color, pad = 0, font = fonts.display150) {
  // A tiny throw-away canvas, only used to measure how wide the text will be.
  const probe = getCtx(makeCanvas(4, 4));
  probe.font = fonts.css(font, 1);
  const tw = Math.ceil(probe.measureText(text).width);
  const lm = fonts.lineMetrics(font);
  const h = Math.ceil(lm.h);
  const c = makeCanvas(tw + Math.ceil(h * SLANT) + 1 + pad * 2, h + pad * 2);
  const g = getCtx(c);
  // setTransform(a, b, c, d, e, f): the third value (c = -SLANT) is the horizontal shear; e and f shift the result.
  g.setTransform(1, 0, -SLANT, 1, SLANT * h + pad, pad);
  g.font = fonts.css(font, 1);
  g.fillStyle = rgb(color);
  g.textBaseline = "alphabetic";
  g.fillText(text, 0, lm.asc);
  return c;
}

/** A slanted blade of light: a hot core with a soft falloff, fading out at both tips (opaque on black, for adding). */
// Built once into a hidden canvas. Drawn with additive blending, so black means "nothing" and bright means "glow".
function makeStreak(h) {
  const w = 48;
  const s = makeCanvas(w, h), g = getCtx(s);
  g.fillStyle = "#000";
  g.fillRect(0, 0, w, h);
  for (let dx = -w / 2; dx < w / 2; dx++) {
    // A narrow bright core plus a wider soft glow, each a bell curve (Gaussian) across the streak's width.
    const k = Math.exp(-((dx / 3.0) ** 2)) + 0.35 * Math.exp(-((dx / 11.0) ** 2));
    g.fillStyle = rgb(shade([255, 236, 205], Math.min(1, k)));
    g.fillRect(w / 2 + dx, 0, 1, h);
  }
  // "multiply" darkens by the gradient, so the streak fades out at both tips.
  g.globalCompositeOperation = "multiply";
  const fade = g.createLinearGradient(0, 0, 0, h);
  for (let i = 0; i <= 12; i++) {
    const v = Math.sin(Math.PI * (i / 12)) ** 0.8;
    fade.addColorStop(i / 12, `rgb(${(v * 255) | 0},${(v * 255) | 0},${(v * 255) | 0})`);
  }
  g.fillStyle = fade;
  g.fillRect(0, 0, w, h);
  const out = makeCanvas(w + h * 0.3, h + w * 0.3);
  const og = getCtx(out);
  og.fillStyle = "#000";
  og.fillRect(0, 0, out.width, out.height);
  og.translate(out.width / 2, out.height / 2);
  og.rotate(rad(14)); // pygame rotate(-14) turns clockwise
  og.drawImage(s, -w / 2, -h / 2);
  return out;
}

/** A tapered brush underline with a gentle sag. */
// Draws a row of circles whose radius rises then falls, which looks like one tapered brush stroke.
function makeSwash(w, color) {
  const h = 26;
  const s = makeCanvas(w, h), g = getCtx(s);
  const n = Math.trunc(w / 2);
  for (let i = 0; i <= n; i++) {
    const u = i / n;
    const r = 1.0 + 5.2 * Math.sin(Math.PI * u ** 0.8) ** 0.7; // thick early, a long thin tail like a lifted brush
    circle(g, 6 + u * (w - 12), h / 2 + 5 * Math.sin(Math.PI * u) - 4 * u, r, rgb(color));
  }
  return s;
}

// Created by the Menu. `world` is the menu's World, so the melon and its juice use the normal fruit systems.
export class TitleIntro {
  constructor(app, world) {
    this.app = app; this.w = world;
    this.t = 0;
    this.cut = false;
    this.sealed = false;
    const f = app.art.fonts;
    this.juice = FRUITS.watermelon.juice;
    let titleFont = f.display150;
    this.ink = slantedText(f, TITLE, WASHI, 0, titleFont);
    if (this.ink.width > TITLE_MAX_W) {
      const size = Math.floor(titleFont.size * TITLE_MAX_W / this.ink.width);
      titleFont = { ...titleFont, id: `${titleFont.family}${size}`, size };
      this.ink = slantedText(f, TITLE, WASHI, 0, titleFont);
    }
    // The "wet juice" layer: the title in juice colour, smeared in 9 directions to fatten it, then blurred.
    const red = slantedText(f, TITLE, this.juice, 0, titleFont);
    const wet = makeCanvas(red.width + 12, red.height + 12), wg = getCtx(wet);
    for (const [dx, dy] of [[0, 0], [3, 0], [-3, 0], [0, 3], [0, -3], [2, 2], [-2, 2], [2, -2], [-2, -2]]) wg.drawImage(red, 6 + dx, 6 + dy);
    this.wet = blurCanvas(wet, 2);
    this.shadow = blurCanvas(slantedText(f, TITLE, [0, 0, 0], 6, titleFont), 5);
    this.glint = slantedText(f, TITLE, [255, 240, 214], 0, titleFont);
    this.rect = rectAt(this.ink.width, this.ink.height, "center", [W / 2, CY]);
    this.swash = makeSwash(Math.trunc(this.rect.w * 0.86), shade(HANKO, 1.05));
    this.streak = makeStreak(this.rect.h + 70);
    this.seal = app.art.seal("H", 44);
    this.blade = BLADES[app.save.blade].slice(0, 3);
    app.audio.play("throw", 0.8);
    this.melon = world.throw("watermelon", W / 2, 0, 0, 0);
    // `flight` and `spin` are Body settings (entities.js) that make the melon swell and turn as it is tossed.
    this.melon.flight = 2 * TOSS; // swells toward the camera at the apex; the halves carry the arc on
    this.melon.spin = 260;
    this.placeMelon();
  }

  // True when the animation has finished and the title is just sitting there.
  get done() { return this.t >= DONE; }

  // Jump to the finished state (any key press, click or fast swipe). Removes the melon if it has not been cut yet.
  skip() {
    if (this.done) return;
    this.t = DONE;
    if (this.melon.alive) { // skipped before the cut: the melon just isn't there any more
      this.melon.alive = false;
      const i = this.w.bodies.indexOf(this.melon);
      if (i >= 0) this.w.bodies.splice(i, 1);
    }
    this.sealed = true;
  }

  /** The toss is scripted, not simulated: an eased rise lands it exactly on the apex at the cut. */
  placeMelon() {
    const b = this.melon;
    const u = Math.min(1.0, this.t / TOSS);
    // easeOut gives a rise that starts fast and slows to a stop exactly at the apex.
    const y0 = H + 90;
    b.x = W / 2; b.y = y0 + (APEX - y0) * easeOut(u, 2);
    b.vx = 0.0; b.vy = ((-2 * (y0 - APEX)) / TOSS) * (1 - u); // d/dt of the curve: drives the motion blur
  }

  // Advances the timer; at TOSS the melon is cut with a big diagonal slash, then the seal stamp lands at SEAL_AT.
  update(dt) {
    this.t += dt;
    const w = this.w;
    if (!this.cut && this.melon.alive) {
      if (this.t < TOSS) this.placeMelon();
      else {
        this.cut = true;
        this.placeMelon();
        const [ax, ay, bx, by] = TitleIntro.slashLine();
        const n = w.halves.length;
        w.cut(this.melon, ax, ay, bx, by);
        // slice(n) picks only the two halves just created by the cut above.
        for (const h of w.halves.slice(n)) { // a hero cut: the halves part harder than a menu fruit's
          h.vx *= 2.4;
          h.vy -= 260;
        }
        const i = w.bodies.indexOf(this.melon);
        if (i >= 0) w.bodies.splice(i, 1);
        w.particles.sparks(W / 2, APEX, this.blade[1], 26, 650, 0.45);
        w.zoomPunch(1.035);
        w.shake.kick(0.35);
        w.flash = Math.max(w.flash, 0.22);
        this.app.audio.play("swoosh", 1.0);
      }
    }
    if (!this.sealed && this.t >= SEAL_AT) {
      this.sealed = true;
      const [x, y] = this.sealPos();
      w.particles.ink(x, y, HANKO, 14);
      this.app.audio.play("stamp", 0.6);
    }
  }

  // A static method belongs to the class itself, not to an instance. The slash goes from lower-left to upper-right through the apex.
  static slashLine() { return [W / 2 - 300, APEX + 120, W / 2 + 300, APEX - 120]; }
  sealPos() { return [this.rect.right + 4, this.rect.bottom - 30]; }

  // ---------------- drawing ----------------

  /** World-layer part (passed to World.draw as `extra`): the blade streak and the signed name. */
  drawWorld(L, add) {
    const t = this.t;
    if (this.cut && t < TOSS + SLASH) this.drawSlash(add, (t - TOSS) / SLASH);
    const u = (t - REVEAL_AT) / REVEAL;
    if (u <= 0) return;
    const r = this.rect;
    // `front` = how many pixels of the title have been "signed" so far; it grows left to right like a moving brush.
    const front = (r.w + EDGE * 2) * easeOut(u, 2) - EDGE; // px of the name signed so far
    const settle = easeOut((t - REVEAL_AT - REVEAL * 0.6) / SETTLE, 2);
    // wet juice underneath, leading the brush a little, then drying back to a thin red edge
    const off = [6 - 4 * settle, 8 - 5 * settle];
    this.blitFront(L, this.shadow, [r.left - 6 + 3, r.top - 6 + 6], front + 10, 200 / 255);
    this.blitFront(L, this.wet, [r.left - 6 + off[0], r.top - 6 + off[1]], front + 22, (255 - 120 * settle) / 255);
    this.blitFront(L, this.ink, [r.left, r.top], front, 1);
    if (u < 1.15) { // the brush tip glows as it travels
      const k = Math.max(0.0, 1 - Math.max(0.0, u - 1) / 0.15);
      add.globalAlpha = k;
      add.drawImage(this.streak, r.left + front - this.streak.width / 2, r.centery - this.streak.height / 2);
      add.globalAlpha = 1;
    }
    const s = (t - SWASH_AT) / SWASH;
    if (s > 0) {
      const ww = Math.trunc(this.swash.width * easeOut(s, 2));
      if (ww > 0) L.drawImage(this.swash, 0, 0, ww, this.swash.height, r.left + r.w * 0.06, r.bottom - 34, ww, this.swash.height);
    }
    if (this.done) this.drawSweep(add);
  }

  /** Draw the part of `img` left of the brush front, its last EDGE px feathered. */
  // Copies only the left part of `img` (up to `front` pixels) and fades its last EDGE pixels, so the front edge looks soft.
  blitFront(L, img, pos, front, alpha) {
    const wdt = Math.trunc(Math.min(img.width, front));
    if (wdt <= 0) return;
    const piece = makeCanvas(wdt, img.height), pg = getCtx(piece);
    pg.drawImage(img, 0, 0, wdt, img.height, 0, 0, wdt, img.height);
    if (wdt < img.width) {
      // "destination-in" keeps the existing pixels only where the new gradient is opaque: that is how the soft edge is cut.
      pg.globalCompositeOperation = "destination-in";
      const gr = pg.createLinearGradient(Math.max(0, wdt - EDGE), 0, wdt, 0);
      for (let i = 0; i <= 8; i++) gr.addColorStop(i / 8, `rgba(255,255,255,${(1 - i / 8) ** 1.4})`);
      pg.fillStyle = gr;
      pg.fillRect(0, 0, wdt, img.height);
    }
    L.globalAlpha = alpha;
    L.drawImage(piece, pos[0], pos[1]);
    L.globalAlpha = 1;
  }

  /** The blade's streak: a lens of light drawn across in the first third, then burning out. */
  // u is progress 0..1. The shape is a thin diamond (a lens) made from three polygons of different widths and colours.
  drawSlash(add, u) {
    const [ax, ay, bx, by] = TitleIntro.slashLine();
    // In the first 30% the streak grows across; after that it only fades.
    const grow = easeOut(u / 0.3, 2);
    const fade = u < 0.3 ? 1.0 : (1 - (u - 0.3) / 0.7) ** 1.5;
    const ex = ax + (bx - ax) * grow, ey = ay + (by - ay) * grow;
    const dx = ex - ax, dy = ey - ay;
    const L = Math.hypot(dx, dy) || 1;
    const nx = -dy / L, ny = dx / L;
    const mx = (ax + ex) / 2, my = (ay + ey) / 2;
    const op = add.globalCompositeOperation;
    add.globalCompositeOperation = "source-over";
    [16, 7, 2.5].forEach((wdt, i) => {
      polygon(add, [[ax, ay], [mx + nx * wdt, my + ny * wdt], [ex, ey], [mx - nx * wdt, my - ny * wdt]], shade(this.blade[i], fade));
    });
    add.globalCompositeOperation = op;
  }

  /** Idle: a slow katana light crosses the name every SWEEP_EVERY s. */
  // `p % SWEEP_EVERY` repeats the effect forever: p counts up and wraps every SWEEP_EVERY seconds.
  drawSweep(add) {
    const p = this.t - DONE - SWEEP_FIRST;
    if (p < 0) return;
    const u = (p % SWEEP_EVERY) / SWEEP;
    if (u > 1) return;
    const r = this.rect;
    const k = Math.sin(Math.PI * u); // fades in and out at the ends
    const sx = r.left - 40 + (r.w + 80) * u;
    add.globalAlpha = 0.55 * k;
    add.drawImage(this.streak, sx - this.streak.width / 2, r.centery - this.streak.height / 2);
    const bw = 120;
    const x0 = Math.trunc(sx - r.left - bw / 2);
    const cx0 = Math.max(0, x0), cx1 = Math.min(this.glint.width, x0 + bw);
    // Only the letters under the streak are brightened: cut a slice of the bright copy of the title, shade it with a bell-curve gradient, add it.
    if (cx1 > cx0) { // only the letters right at the streak catch light
      const g = makeCanvas(cx1 - cx0, this.glint.height), gg = getCtx(g);
      gg.drawImage(this.glint, cx0, 0, cx1 - cx0, this.glint.height, 0, 0, cx1 - cx0, this.glint.height);
      gg.globalCompositeOperation = "multiply";
      const gr = gg.createLinearGradient(x0 - cx0, 0, x0 - cx0 + bw, 0);
      for (let i = 0; i <= 12; i++) {
        const v = Math.exp(-((((i / 12) * bw - bw / 2) / (bw / 6)) ** 2));
        gr.addColorStop(i / 12, `rgb(${(v * 255) | 0},${(v * 255) | 0},${(v * 255) | 0})`);
      }
      gg.fillStyle = gr;
      gg.fillRect(0, 0, g.width, g.height);
      add.globalAlpha = 0.7 * k;
      add.drawImage(g, r.left + cx0, r.top);
    }
    add.globalAlpha = 1;
  }

  /** UI part: the subtitle slides in under the name, then the seal is pressed. */
  // The subtitle slides in with two thin gold lines growing on either side of it.
  drawUi(ui) {
    const f = this.app.art.fonts;
    const u = (this.t - SUB_AT) / SUB;
    if (u > 0) {
      const e = easeOut(u);
      const a = Math.min(1.0, u * 1.6);
      const sub = label(ui, f, f.mono17, SUBTITLE, GOLD, [W / 2 + 46 * (1 - e), this.rect.bottom + 6], "center", 8, true, a);
      const lw = Math.max(1, Math.trunc(54 * e));
      ui.fillStyle = rgba(GOLD, a / 2);
      ui.fillRect(sub.left - 18 - lw, sub.centery, lw, 1);
      ui.fillRect(sub.right + 18, sub.centery, lw, 1);
    }
    if (this.t >= SEAL_AT) {
      const age = this.t - SEAL_AT;
      const [x, y] = this.sealPos();
      const k = stampScale(age);
      ui.save();
      ui.translate(x, y);
      // Canvas rotation is clockwise-positive in radians, so a small tilt makes the seal look hand-pressed.
      ui.rotate(rad(8)); // rotozoom(-8): clockwise
      ui.scale(k, k);
      ui.drawImage(this.seal, -this.seal.width / 2, -this.seal.height / 2);
      ui.restore();
    }
  }
}
