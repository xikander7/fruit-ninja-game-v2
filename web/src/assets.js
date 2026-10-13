// Loading and building the art: photoreal sprites, fonts, kanji stencils, hanko seals, juice splashes, the
// dojo wall (ninja/art.py). Everything is built once at start-up or on first use and cached.
// Most visuals are built here once and then reused ("cached") because creating canvases is slow.
// Some art comes from files (fruit photos, fonts, kanji stencil images); the rest is drawn in code
// (seals, ink blots, brush strokes, the vignette). The Art class at the bottom is the one object
// the game passes around as `art`. A "canvas" is a pixel image you can draw on.
import { FRUITS, W, H, HANKO, GOLD } from "./config.js";
import { gfx, makeCanvas, getCtx, makeShadow, tinted, blurCanvas, polygon, circle } from "./gfx.js";
import { seeded, rgb, TAU, clamp } from "./util.js";
import { netPool, retry } from "./net.js";

// Unicode code points (in hex) of the kanji stencil images in glyphs/. The seal stamps cut these out of red ink.
export const GLYPH_HEX = ["500d", "518d", "51cd", "5d50", "5f71", "5fcd", "623b", "6587", "65ac", "6642", "6975", "6b62", "708e", "71b1",
  "767d", "7985", "7d42", "8a0e", "9006", "901f", "9023", "9053", "9b3c"];
const GLYPH_SIZE = 120; // the stencils are rendered at 120 px
// Photo splash overlays: file name, and the direction (degrees) the liquid is flung; null = a radial "crown".
const SPLASHES = [["burst1", null], ["burst2", 0], ["drops1", 90], ["drops2", 8]]; // file, direction the liquid is flung (deg)
const SPLASH_SCALE = 0.62;
// Every sprite image to load: each fruit by name plus the bomb, ice bomb, shuriken and the two bosses.
const SPRITE_NAMES = [...Object.keys(FRUITS), "bomb", "icebomb", "shuriken", "durian", "pineapple"];

// ---------------- fonts and text ----------------

// family -> [file, weight, fallback fonts used if the file fails to load].
const FONT_FILES = {
  CormorantSC: ["CormorantSC-Bold.ttf", "700", "Georgia, 'Times New Roman', serif"],
  BarlowCondensed: ["BarlowCondensed-SemiBold.ttf", "600", "'Arial Narrow', 'Segoe UI', sans-serif"],
  PlexMono: ["IBMPlexMono-Regular.ttf", "400", "Consolas, 'Courier New', monospace"],
};

// Describes one font at one size: family + size gives a unique id used as a cache key.
function fontSpec(family, size) {
  const [, weight, fallback] = FONT_FILES[family];
  return { id: `${family}${size}`, family, size, weight, fallback };
}

// All named fonts the game uses (title, score, timer...), plus cached text images so text is not re-rendered every frame.
export class Fonts {
  constructor() {
    const D = "CormorantSC", N = "BarlowCondensed", M = "PlexMono";
    this.title = fontSpec(D, 120); this.pause = fontSpec(D, 72); this.mode = fontSpec(D, 40);
    this.caption = fontSpec(D, 36); this.boss = fontSpec(D, 22);
    this.final = fontSpec(N, 140); this.score = fontSpec(N, 72); this.timer = fontSpec(N, 64);
    this.bonus = fontSpec(N, 40); this.pop = fontSpec(N, 30); this.best = fontSpec(N, 26);
    this.mono15 = fontSpec(M, 15); this.mono13 = fontSpec(M, 13); this.mono12 = fontSpec(M, 12); this.mono17 = fontSpec(M, 17);
    this.display150 = fontSpec(D, 150);
    this._cache = new Map();
    this._metrics = new Map();
  }

  // Builds a CSS font string (like "700 72px Barlow"); S is the render scale for sharp text on big screens.
  css(font, S = gfx.RS) {
    return `${font.weight} ${font.size * S}px "${font.family}", ${font.fallback}`;
  }

  /** Line height of a font in logical px (what pygame calls get_height). */
  lineMetrics(font) {
    let m = this._metrics.get(font.id);
    if (!m) {
      const g = getCtx(makeCanvas(4, 4));
      g.font = this.css(font, 1);
      const t = g.measureText("Mg");
      // ascent = pixels above the text baseline, descent = below it; together they are the line height.
      const asc = t.fontBoundingBoxAscent ?? font.size * 0.95;
      const desc = t.fontBoundingBoxDescent ?? font.size * 0.27;
      m = { asc, h: asc + desc };
      this._metrics.set(font.id, m);
    }
    return m;
  }

  /** Rendered text: a canvas at gfx.RS with logical size lw x lh. `tracking` adds px between letters. */
  text(font, s, color, tracking = 0) {
    const key = `${font.id}|${s}|${color[0]},${color[1]},${color[2]}|${tracking}|${gfx.RS}`;
    let img = this._cache.get(key);
    if (!img) {
      if (this._cache.size > 600) this._cache.clear(); // a rolling score makes many strings; never let the cache grow
      const S = gfx.RS, lm = this.lineMetrics(font);
      const probe = getCtx(makeCanvas(4, 4));
      probe.font = this.css(font);
      // Tracking (letter spacing) is done by drawing letter by letter, so we measure each character.
      const chars = tracking && s.length > 1 ? [...s] : [s];
      const widths = chars.map((c) => probe.measureText(c).width / S);
      const lw = Math.max(1, widths.reduce((a, b) => a + b, 0) + (chars.length > 1 ? tracking * (chars.length - 1) : 0));
      img = makeCanvas(Math.ceil(lw * S), Math.ceil(lm.h * S));
      img.lw = img.width / S; img.lh = img.height / S;
      const g = getCtx(img);
      g.font = this.css(font);
      g.fillStyle = rgb(color);
      g.textBaseline = "alphabetic";
      let x = 0;
      chars.forEach((c, i) => { g.fillText(c, x * S, lm.asc * S); x += widths[i] + tracking; });
      this._cache.set(key, img);
    }
    return img;
  }

  /** A soft drop shadow for text over the photoreal wall (blurred, so it reads as depth, not an outline). */
  shadow(font, s, tracking = 0) {
    const key = `sh|${font.id}|${s}|${tracking}|${gfx.RS}`;
    let img = this._cache.get(key);
    if (!img) {
      const src = this.text(font, s, [0, 0, 0], tracking);
      const S = gfx.RS, pad = 6;
      const base = makeCanvas(src.width + pad * 2 * S, src.height + pad * 2 * S);
      getCtx(base).drawImage(src, pad * S, pad * S);
      img = blurCanvas(base, 3 * S);
      img.lw = img.width / S; img.lh = img.height / S;
      this._cache.set(key, img);
    }
    return img;
  }
}

// ---------------- small UI images, cached at the render scale ----------------

/** A canvas lw x lh logical px, backed at gfx.RS, with a context already scaled to logical units. */
export function hiCanvas(lw, lh) {
  const S = gfx.RS;
  const c = makeCanvas(Math.ceil(lw * S), Math.ceil(lh * S));
  c.lw = c.width / S; c.lh = c.height / S;
  const g = getCtx(c);
  g.scale(S, S);
  return [c, g];
}

// Small shared cache: same key + render scale gives back the same canvas instead of building a new one.
const UI_CACHE = new Map();
function cached(key, make) {
  const k = `${key}|${gfx.RS}`;
  let v = UI_CACHE.get(k);
  if (!v) { v = make(); UI_CACHE.set(k, v); }
  return v;
}

/** A thin < or > (step -1 / 1). */
export function chevron(step, color) {
  return cached(`chev${step}${color}`, () => {
    const [c, g] = hiCanvas(12, 18);
    g.strokeStyle = rgb(color); g.lineWidth = 1.5; g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath();
    g.moveTo(6 - 3 * step, 2); g.lineTo(6 + 4 * step, 9); g.lineTo(6 - 3 * step, 16);
    g.stroke();
    return c;
  });
}

/** A 1 px anti-aliased gold circle (one per radius). */
export function hairlineRing(r) {
  return cached(`ring${r}`, () => {
    const [c, g] = hiCanvas(r * 2 + 4, r * 2 + 4);
    circle(g, r + 2, r + 2, r, rgb(GOLD), 1);
    return c;
  });
}

/** A strike mark painted as two brush strokes, blunt where the brush lands and tapering as it lifts. */
export function brushX(size, color, outline = false) {
  return cached(`bx${size}${color}${outline}`, () => {
    const d = size, p = d * 0.1;
    // Each stroke: [start x, y, end x, y, bow (how much it curves), max width]. Two strokes make the X.
    const strokes = [[p, p * 1.3, d - p, d - p * 0.8, 0.05, 0.17], [d - p * 1.2, p, p * 1.1, d - p * 1.1, -0.04, 0.14]];
    const shapes = strokes.map(([x0, y0, x1, y1, bow, wmax]) => {
      const L = Math.hypot(x1 - x0, y1 - y0), ux = (x1 - x0) / L, uy = (y1 - y0) / L, nx = -uy, ny = ux;
      const left = [], right = [];
      for (let i = 0; i <= 20; i++) {
        const t = i / 20;
        // Width along the stroke: blunt where the brush lands, then tapering to a point as it lifts (t goes 0 -> 1).
        const w = (d * wmax * (0.65 + 0.35 * Math.min(1, t / 0.18)) * Math.max(0.03, 1 - t ** 1.8)) / 2;
        const cx = x0 + ux * L * t + nx * bow * L * Math.sin(Math.PI * t);
        const cy = y0 + uy * L * t + ny * bow * L * Math.sin(Math.PI * t);
        left.push([cx + nx * w, cy + ny * w]);
        right.push([cx - nx * w, cy - ny * w]);
      }
      return left.concat(right.reverse());
    });
    const [c, g] = hiCanvas(size, size);
    if (!outline) {
      for (const s of shapes) polygon(g, s, color);
      return c;
    }
    // outline of the union of both strokes: each outline loses the part that lies inside the other stroke
    const lines = shapes.map((s, i) => {
      const [lc, lg] = hiCanvas(size, size);
      lg.strokeStyle = rgb(color); lg.lineWidth = 1.3; lg.lineJoin = "round";
      lg.beginPath(); s.forEach(([x, y], k) => (k ? lg.lineTo(x, y) : lg.moveTo(x, y))); lg.closePath(); lg.stroke();
      lg.globalCompositeOperation = "destination-out";
      polygon(lg, shapes[1 - i], "#000");
      return lc;
    });
    for (const l of lines) g.drawImage(l, 0, 0, size, size);
    return c;
  });
}

// ---------------- hanko seals, ink blots ----------------

// Draws a hanko (a Japanese stamp seal): a red square with a slightly wobbly edge, the kanji cut out,
// then noise and wear so it looks pressed in ink. A seeded random generator (rng) makes the same glyph look the same each time.
export function makeSeal(art, glyph, size) {
  const rng = seeded(glyph);
  const s = makeCanvas(size, size), g = getCtx(s);
  const m = size * 0.06;
  const pts = []; // the stone's edge: square, slightly irregular
  const corners = [[m, m], [size - m, m], [size - m, size - m], [m, size - m]];
  for (let side = 0; side < 4; side++) {
    const a = corners[side], b = corners[(side + 1) % 4];
    for (let k = 0; k < 8; k++) {
      const t = k / 8, j = size * 0.012;
      pts.push([a[0] + (b[0] - a[0]) * t + rng.uniform(-j, j), a[1] + (b[1] - a[1]) * t + rng.uniform(-j, j)]);
    }
  }
  polygon(g, pts, HANKO);
  const gl = art.glyphs[glyph[0].codePointAt(0).toString(16)];
  if (gl) { // the glyph is left uncut (白文): subtracting its alpha cuts it out of the ink
    const px = Math.trunc(size * 0.6);
    g.globalCompositeOperation = "destination-out";
    g.drawImage(gl, size / 2 - px / 2, size / 2 + size * 0.02 - px / 2, px, px);
  }
  g.globalCompositeOperation = "destination-in"; // uneven ink: a coarse noise field multiplied into alpha
  const n = Math.max(4, size >> 3);
  const noise = makeCanvas(n, n), ng = getCtx(noise);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) { ng.fillStyle = `rgba(255,255,255,${rng.randint(205, 255) / 255})`; ng.fillRect(x, y, 1, 1); }
  g.imageSmoothingQuality = "high";
  g.drawImage(noise, 0, 0, size, size);
  const wear = makeCanvas(size, size), wg = getCtx(wear); // worn spots where the paper didn't take the ink
  wg.fillStyle = "#fff"; wg.fillRect(0, 0, size, size);
  wg.globalCompositeOperation = "destination-out";
  for (let i = 0; i < Math.trunc(size * 0.35); i++) {
    wg.fillStyle = `rgba(0,0,0,${1 - rng.randint(0, 190) / 255})`;
    wg.beginPath(); wg.arc(rng.uniform(0, size), rng.uniform(0, size), rng.uniform(0.4, Math.max(0.8, size * 0.018)), 0, TAU); wg.fill();
  }
  wg.fillStyle = "#000"; // chipped edges
  for (let i = 0; i < Math.trunc(size * 0.12); i++) {
    const t = rng.uniform(m, size - m);
    const [x, y] = [[t, m], [size - m, t], [t, size - m], [m, t]][rng.randint(0, 3)];
    wg.beginPath(); wg.arc(x, y, rng.uniform(0.6, Math.max(1.0, size * 0.025)), 0, TAU); wg.fill();
  }
  g.drawImage(wear, 0, 0);
  return s;
}

/** The dark-red bleed a seal leaves behind it: an irregular soft blob with a few flecks thrown off by the impact. */
export function makeBlot(size) {
  const rng = seeded(`blot${size}`);
  const d = Math.trunc(size * 1.9);
  const s = makeCanvas(d, d), g = getCtx(s);
  const c = d / 2, col = "rgb(92,12,10)";
  let x = c, y = c;
  for (let i = 0; i < 40; i++) { // a wandering cluster, pulled back toward the centre so it stays one blot
    x += rng.uniform(-1, 1) * size * 0.16 + (c - x) * 0.2;
    y += rng.uniform(-1, 1) * size * 0.16 + (c - y) * 0.2;
    circle(g, x, y, rng.uniform(size * 0.24, size * 0.5), col);
  }
  for (let i = 0; i < 9; i++) {
    const a = rng.uniform(0, TAU), r = rng.uniform(size * 0.62, size * 0.86);
    circle(g, c + Math.cos(a) * r, c + Math.sin(a) * r, rng.uniform(1.2, Math.max(1.5, size * 0.035)), col);
  }
  return blurCanvas(s, Math.max(1, size / 60));
}

// ---------------- the dojo wall, full-view grades ----------------

/** The photo wall darkened so it sits behind the fruit, with the vignette, covering the whole view. */
export function makeBackground(img, vw, vh) {
  const c = makeCanvas(vw, vh), g = getCtx(c);
  const k = Math.max(vw / W, vh / H); // cover: the wall fills the window whatever its shape
  g.drawImage(img, (vw - W * k) / 2, (vh - H * k) / 2, W * k, H * k);
  g.globalCompositeOperation = "multiply";
  g.fillStyle = "rgb(165,150,140)";
  g.fillRect(0, 0, vw, vh);
  // vignette: a lamplit pool in the middle, dark toward the edges (the same ellipses as the Python game, scaled to the view)
  const vig = makeCanvas(vw, vh), vg = getCtx(vig);
  const sx = vw / W, sy = vh / H;
  vg.fillStyle = "rgb(95,95,95)";
  vg.fillRect(0, 0, vw, vh);
  // Draw 90 nested ellipses, each smaller and brighter than the last, so the centre ends brightest and the steps blend into a smooth fade.
  const N = 90;
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const v = Math.trunc(95 + 160 * t ** 0.6);
    vg.fillStyle = `rgb(${v},${v},${v})`;
    vg.beginPath();
    vg.ellipse(vw / 2, vh / 2 - (H * 0.5 - H * 0.42) * sy, (W * 1.5 * (1 - t * 0.55) * sx) / 2, (H * 1.6 * (1 - t * 0.55) * sy) / 2, 0, 0, TAU);
    vg.fill();
  }
  g.drawImage(vig, 0, 0); // still multiplying
  return c;
}

/** A smooth coloured vignette: clear in the middle, rising to `peak` alpha at the frame edge (frost, embers). */
export function makeEdgeGlow(color, peak, reach, vw, vh) {
  const sw = Math.max(2, vw >> 3), sh = Math.max(2, vh >> 3);
  const small = makeCanvas(sw, sh), sg = getCtx(small);
  const data = sg.createImageData(sw, sh);
  for (let y = 0; y < sh; y++) {
    for (let x = 0; x < sw; x++) {
      const u = ((x + 0.5) / sw) * 2 - 1, v = ((y + 0.5) / sh) * 2 - 1;
      const d = (u ** 4 + v ** 4) ** 0.25; // superellipse: hugs the 16:9 frame instead of a circle
      const t = clamp((d - (1 - reach)) / reach, 0, 1);
      const i = (y * sw + x) * 4;
      data.data[i] = color[0]; data.data[i + 1] = color[1]; data.data[i + 2] = color[2];
      data.data[i + 3] = Math.trunc(peak * t * t * (3 - 2 * t));
    }
  }
  sg.putImageData(data, 0, 0);
  const out = makeCanvas(vw, vh), g = getCtx(out);
  g.imageSmoothingQuality = "high";
  g.drawImage(small, 0, 0, vw, vh);
  return out;
}

// ---------------- the Art object ----------------

// Loads one image file as a promise (waits until it is ready); retries on failure through the shared network pool.
function loadImage(url) {
  return netPool(() => retry((attempt) => new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`could not load ${url}`));
    img.src = attempt ? `${url}?retry=${attempt}` : url; // a retry asks for a fresh copy, not the failed one
  })));
}

// Loads the custom font files and registers them with the browser. If one fails, the fallback font is used.
async function loadFonts(base) {
  const faces = Object.entries(FONT_FILES).map(([family, [file, weight]]) => {
    const f = new FontFace(family, `url(${base}fonts/${file})`, { weight });
    return netPool(() => retry(() => f.load())).then((ff) => { document.fonts.add(ff); }).catch(() => { /* the fallback font covers it */ });
  });
  await Promise.all(faces);
}

/** The first row of opaque pixels: where a bomb's fuse comes out (offset from the centre). */
function bombTip(img) {
  const c = makeCanvas(img.width, img.height), g = getCtx(c);
  g.drawImage(img, 0, 0);
  const { data, width, height } = g.getImageData(0, 0, c.width, c.height);
  for (let y = 0; y < height; y++) {
    let sum = 0, n = 0;
    for (let x = 0; x < width; x++) if (data[(y * width + x) * 4 + 3] > 8) { sum += x; n++; }
    if (n) return [sum / n - width / 2, y - height / 2];
  }
  return [0, -height / 2];
}

// The loaded art for the whole game. Create it, `await art.load(base)`, then read art.fruits, art.bomb, art.fonts...
export class Art {
  constructor() {
    this.fonts = new Fonts();
    this._seals = new Map(); this._blots = new Map(); this._splash = new Map(); this._views = new Map();
  }

  /** Fetch and build everything. `onProgress(done, total)` drives the loading bar. */
  async load(base, onProgress = () => {}) {
    const jobs = [];
    let done = 0;
    // Counts every file to load so the loading bar can show done / total.
    const total = SPRITE_NAMES.length + 1 + SPLASHES.length + GLYPH_HEX.length + 2;
    const track = (p) => p.then((v) => { onProgress(++done, total); return v; });
    const img = (url) => track(loadImage(`${base}${url}`));
    const sprites = {};
    for (const n of SPRITE_NAMES) jobs.push(img(`sprites/${n}.png`).then((i) => { sprites[n] = i; }));
    const halves = {};
    for (const n of Object.keys(FRUITS)) {
      if (FRUITS[n].special) continue;
      jobs.push(img(`sprites/${n}_half.png`).then((i) => { halves[n] = i; }));
    }
    jobs.push(img("sprites/banana_half.png").then((i) => { halves.banana = i; }));
    this.glyphs = {};
    for (const hex of GLYPH_HEX) jobs.push(img(`glyphs/${hex}.png`).then((i) => { this.glyphs[hex] = i; }));
    const bgJob = img("sprites/background.jpg");
    const splashImgs = [];
    SPLASHES.forEach(([n], i) => jobs.push(img(`sprites/splash_${n}.png`).then((im) => { splashImgs[i] = im; })));
    jobs.push(track(loadFonts(base)));
    await Promise.all(jobs);
    this.bgImage = await bgJob;

    this.fruits = {};
    for (const [name, ft] of Object.entries(FRUITS)) {
      const whole = sprites[name];
      const half = ft.special ? tinted(halves.banana, 1, ft.juice) : halves[name]; // specials reuse the banana half, tinted
      this.fruits[name] = {
        ft, whole, half, halfLocal: 270, // every half has the cut face up and the rind dome down: outward is 270 deg
        shadow: makeShadow(whole), halfShadow: makeShadow(half),
      };
    }
    // bombTip finds where the fuse comes out of the bomb sprite, so the spark can sit there.
    this.bomb = sprites.bomb; this.bombTip = bombTip(sprites.bomb); this.bombShadow = makeShadow(sprites.bomb);
    this.icebomb = sprites.icebomb; this.icebombShadow = makeShadow(sprites.icebomb);
    this.shuriken = sprites.shuriken; this.shurikenShadow = makeShadow(sprites.shuriken);
    this.boss = { durian: sprites.durian, pineapple: sprites.pineapple };
    this.splashes = splashImgs.map((im, i) => ({ img: im, dir: SPLASHES[i][1], glint: null }));
    this.splashDirs = SPLASHES.map(([, d]) => d);
    onProgress(total, total);
  }

  /** Splash sprite i tinted to a juice colour at SPLASH_SCALE of its size, cached; rotation is done when drawn. */
  splash(i, color) {
    const key = `${i}|${color}`;
    let c = this._splash.get(key);
    if (!c) {
      const sp = this.splashes[i];
      const w = sp.img.width, h = sp.img.height;
      const src = makeCanvas(w, h), sg = getCtx(src);
      sg.drawImage(sp.img, 0, 0);
      const px = sg.getImageData(0, 0, w, h), d = px.data;
      for (let j = 0; j < d.length; j += 4) {
        const v = d[j]; // the photo is grey: the brightest few percent are specular glints, added back after tinting
        const glint = Math.min(255, Math.max(0, (v - 222) * 8));
        d[j] = Math.min(255, (v * color[0]) / 255 + glint);
        d[j + 1] = Math.min(255, (d[j + 1] * color[1]) / 255 + glint);
        d[j + 2] = Math.min(255, (d[j + 2] * color[2]) / 255 + glint);
      }
      sg.putImageData(px, 0, 0);
      c = makeCanvas(w * SPLASH_SCALE, h * SPLASH_SCALE);
      const cg = getCtx(c);
      cg.imageSmoothingQuality = "high";
      cg.drawImage(src, 0, 0, c.width, c.height);
      if (this._splash.size >= 48) this._splash.delete(this._splash.keys().next().value);
      this._splash.set(key, c);
    }
    return c;
  }

  // Returns a cached seal image for a kanji glyph at a given pixel size.
  seal(glyph, size = 120) {
    const key = `${glyph}|${size}`;
    if (!this._seals.has(key)) this._seals.set(key, makeSeal(this, glyph, size));
    return this._seals.get(key);
  }

  // Returns a cached ink blot image for the given size.
  blot(size) {
    if (!this._blots.has(size)) this._blots.set(size, makeBlot(size));
    return this._blots.get(size);
  }

  /** View-sized layers: the wall and the frost / ember edge glows follow the window's shape. */
  view(vw, vh) {
    const key = `${vw}x${vh}`;
    let v = this._views.get(key);
    if (!v) {
      this._views.clear();
      v = {
        bg: makeBackground(this.bgImage, vw, vh),
        frost: makeEdgeGlow([190, 222, 255], 42, 0.28, vw, vh), // freeze: cold breath at the edges
        ember: makeEdgeGlow([255, 120, 36], 110, 0.2, vw, vh), // frenzy: warm glow at the edges
      };
      this._views.set(key, v);
    }
    return v;
  }
}
