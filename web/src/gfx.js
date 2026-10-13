// Canvas drawing helpers: the JavaScript counterparts of pygame's blit / rotozoom / draw.* and the cached
// glow images the effects add onto the emissive layer.
// These small functions wrap the browser's 2D canvas API (ctx = a canvas drawing context).
// Colours are [r, g, b] arrays (0-255) or CSS strings like "#fff". Angles for sprites are in degrees.
// The "glow" helpers make additive images: a bright colour on black that is drawn with "lighter"
// blending, which adds light instead of covering what is underneath. Results are cached in Maps
// (key -> canvas) because building a gradient every frame would be slow.
import { rgb, shade, TAU } from "./util.js";

// Shared drawing settings other files read.
export const gfx = {
  RS: 1, // render scale of text and UI (crisp on big or HiDPI screens); the world layers stay at 1
};

// Creates an off-screen canvas (an invisible drawing surface); size is at least 1x1 pixel.
export function makeCanvas(w, h) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

// Shortcut: the 2D drawing context of a canvas.
export const getCtx = (c) => c.getContext("2d");

/** Draw `img` centred at (x, y), turned `angDeg` counter-clockwise (pygame's rotozoom) and scaled by s. */
export function drawSprite(ctx, img, x, y, angDeg, s = 1, alpha = 1) {
  ctx.save();
  ctx.translate(x, y);
  if (angDeg) ctx.rotate((-angDeg * Math.PI) / 180);
  if (s !== 1) ctx.scale(s, s);
  if (alpha !== 1) ctx.globalAlpha *= alpha;
  ctx.drawImage(img, -img.width / 2, -img.height / 2);
  ctx.restore();
}

// Draws a circle: filled by default, or just an outline when lineW > 0 (px).
export function circle(ctx, x, y, r, color, lineW = 0) {
  if (r <= 0) return;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  if (lineW > 0) { ctx.strokeStyle = typeof color === "string" ? color : rgb(color); ctx.lineWidth = lineW; ctx.stroke(); }
  else { ctx.fillStyle = typeof color === "string" ? color : rgb(color); ctx.fill(); }
}

// Draws a straight line from (x0, y0) to (x1, y1), w px wide.
export function line(ctx, x0, y0, x1, y1, color, w = 1) {
  ctx.strokeStyle = typeof color === "string" ? color : rgb(color);
  ctx.lineWidth = w;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
}

// Draws connected lines through a list of [x, y] points; closed = also join the last point back to the first.
export function polyline(ctx, pts, color, w = 1, closed = false) {
  ctx.strokeStyle = typeof color === "string" ? color : rgb(color);
  ctx.lineWidth = w;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  if (closed) ctx.closePath();
  ctx.stroke();
}

// Fills a closed shape made from a list of [x, y] points.
export function polygon(ctx, pts, color) {
  ctx.fillStyle = typeof color === "string" ? color : rgb(color);
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  ctx.fill();
}

/** A copy of `src` softened by about `r` px: the browser's blur filter where there is one, else a down-and-up scale. */
export function blurCanvas(src, r) {
  const out = makeCanvas(src.width, src.height);
  const g = getCtx(out);
  if ("filter" in g) {
    g.filter = `blur(${r}px)`;
    g.drawImage(src, 0, 0);
    g.filter = "none";
    return out;
  }
  const k = Math.max(2, Math.round(r));
  const small = makeCanvas(src.width / k, src.height / k);
  getCtx(small).drawImage(src, 0, 0, small.width, small.height);
  g.imageSmoothingQuality = "high";
  g.drawImage(small, 0, 0, out.width, out.height);
  return out;
}

/** The silhouette of img, black and softened, at `alpha`/255: the soft contact shadow under every sprite. */
export function makeShadow(img, alpha = 90) {
  const w = img.width, h = img.height;
  const sil = makeCanvas(w, h);
  const g = getCtx(sil);
  g.drawImage(img, 0, 0);
  g.globalCompositeOperation = "source-in";
  g.fillStyle = "#000";
  g.fillRect(0, 0, w, h);
  // Shrinking to 1/4 size (w >> 2 is a fast integer divide by 4) and stretching back is a cheap blur.
  const small = makeCanvas(Math.max(1, w >> 2), Math.max(1, h >> 2));
  getCtx(small).drawImage(sil, 0, 0, small.width, small.height);
  const out = makeCanvas(w, h);
  const o = getCtx(out);
  o.imageSmoothingQuality = "high";
  o.drawImage(small, 0, 0, w, h);
  o.globalCompositeOperation = "destination-in"; // baked in: alpha multiplied once, here
  o.fillStyle = `rgba(0,0,0,${alpha / 255})`;
  o.fillRect(0, 0, w, h);
  return out;
}

/** A copy of img scaled by k and multiplied by a colour (alpha kept). */
export function tinted(img, k, color) {
  const out = makeCanvas(img.width * k, img.height * k);
  const g = getCtx(out);
  g.drawImage(img, 0, 0, out.width, out.height);
  g.globalCompositeOperation = "multiply";
  g.fillStyle = rgb(color);
  g.fillRect(0, 0, out.width, out.height);
  g.globalCompositeOperation = "destination-in";
  g.drawImage(img, 0, 0, out.width, out.height);
  return out;
}

// ---- cached additive images: opaque colour on black, drawn with 'lighter' ----

// Cache for glowImg, keyed by radius|colour|brightness.
const GLOWS = new Map();

/** A soft additive glow at brightness k. Radius and k are quantised so the cache stays small. */
export function glowImg(radius, color, k) {
  // Rounding radius (to steps of 3) and brightness (to 1/16) means a few cached images get reused instead of thousands of near-duplicates.
  radius = Math.max(2, Math.trunc(radius / 3) * 3);
  k = Math.round(Math.max(0, Math.min(1, k)) * 16) / 16;
  const key = `${radius}|${color[0]},${color[1]},${color[2]}|${k}`;
  let c = GLOWS.get(key);
  if (!c) {
    const d = radius * 2 + 2;
    c = makeCanvas(d, d);
    const g = getCtx(c);
    g.fillStyle = "#000";
    g.fillRect(0, 0, d, d);
    const gr = g.createRadialGradient(d / 2, d / 2, 0, d / 2, d / 2, radius);
    // A radial gradient is a colour that changes with distance from the centre. We add 14 stops, with
    // brightness falling off as t*t (smoother than a straight line) so the glow has no hard edge.
    const steps = 14;
    for (let i = 0; i <= steps; i++) {
      const rho = i / steps; // distance from the centre, 0..1
      const t = Math.min(1, Math.max(0, (1 - rho) / 0.95));
      gr.addColorStop(rho, rgb(shade(color, k * t * t)));
    }
    g.fillStyle = gr;
    g.beginPath();
    g.arc(d / 2, d / 2, radius, 0, TAU);
    g.fill();
    // Safety valve: if the cache grows too big, empty it so memory stays bounded.
    if (GLOWS.size > 400) GLOWS.clear();
    GLOWS.set(key, c);
  }
  return c;
}

/** Draw the glow centred at (x, y) onto an emissive layer. */
export function addGlow(add, radius, color, k, x, y) {
  const g = glowImg(radius, color, k);
  add.drawImage(g, x - g.width / 2, y - g.height / 2);
}

// Cache for rayBurst.
const RAYS = new Map();

/** Six soft light rays on black (for additive blending), fading out from the centre. */
export function rayBurst(radius, color) {
  const key = `${radius}|${color}`;
  let c = RAYS.get(key);
  if (!c) {
    const d = radius * 2 + 2;
    c = makeCanvas(d, d);
    const g = getCtx(c);
    g.fillStyle = "#000";
    g.fillRect(0, 0, d, d);
    const m = d / 2;
    for (let k = 0; k < 6; k++) {
      const a = (k * TAU) / 6;
      // 8 wedges per ray, from wide-and-dim to thin-and-bright, stack into a ray that glows along its core.
      for (let i = 0; i < 8; i++) { // stacked wedges: dim and wide outside, bright and thin in the middle
        const t = i / 7;
        const h = 0.16 * (1 - t) + 0.025;
        polygon(g, [[m, m], [m + Math.cos(a - h) * radius, m + Math.sin(a - h) * radius],
          [m + Math.cos(a + h) * radius, m + Math.sin(a + h) * radius]], shade(color, 0.15 + 0.85 * t * t)); // opaque: the brighter, thinner wedge overwrites
      }
    }
    g.globalCompositeOperation = "multiply"; // radial falloff; dim at the very centre so rays don't stripe the fruit
    // Multiply by a radial gradient (white = keep, black = remove) so rays fade away toward the rim and the centre.
    const gr = g.createRadialGradient(m, m, 0, m, m, radius);
    for (let i = 0; i <= 12; i++) {
      const rho = i / 12;
      const t = 1 - rho;
      const v = Math.max(0, Math.min(1, t ** 1.6 * Math.min(1, (1 - t) / 0.28 + 0.15)));
      gr.addColorStop(rho, `rgb(${(v * 255) | 0},${(v * 255) | 0},${(v * 255) | 0})`);
    }
    g.fillStyle = gr;
    g.fillRect(0, 0, d, d);
    if (RAYS.size > 60) RAYS.clear();
    RAYS.set(key, c);
  }
  return c;
}

// Cache for softImg.
const SOFT = new Map();

/** A soft round puff, tinted, translucent (smoke). */
export function softImg(radius, color) {
  radius = Math.max(2, Math.trunc(radius / 3) * 3);
  const key = `${radius}|${color[0]},${color[1]},${color[2]}`;
  let c = SOFT.get(key);
  if (!c) {
    const d = radius * 2 + 2;
    c = makeCanvas(d, d);
    const g = getCtx(c);
    const gr = g.createRadialGradient(d / 2, d / 2, 0, d / 2, d / 2, radius);
    gr.addColorStop(0, `rgba(${color[0]},${color[1]},${color[2]},0.62)`);
    gr.addColorStop(0.5, `rgba(${color[0]},${color[1]},${color[2]},0.3)`);
    gr.addColorStop(1, `rgba(${color[0]},${color[1]},${color[2]},0)`);
    g.fillStyle = gr;
    g.fillRect(0, 0, d, d);
    if (SOFT.size > 200) SOFT.clear();
    SOFT.set(key, c);
  }
  return c;
}

/** Uniform Catmull-Rom through every control point, `sub` samples per segment. Points are arrays of any length. */
export function catmullRom(pts, sub = 4) {
  const n = pts.length;
  if (n < 2) return pts.slice();
  const out = [];
  const dims = pts[0].length;
  for (let i = 0; i < n - 1; i++) {
    // p1 and p2 are the segment's ends; p0 and p3 are their neighbours, which set the curve's direction there.
    // The long formula below is the standard cubic blend of them, evaluated at u (0..1) between p1 and p2.
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(n - 1, i + 2)];
    for (let s = 0; s < sub; s++) {
      const u = s / sub, u2 = u * u, u3 = u2 * u;
      const q = new Array(dims);
      for (let d = 0; d < dims; d++) {
        q[d] = 0.5 * (2 * p1[d] + (p2[d] - p0[d]) * u + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * u2 +
          (3 * p1[d] - p0[d] - 3 * p2[d] + p3[d]) * u3);
      }
      out.push(q);
    }
  }
  out.push(pts[n - 1].slice());
  return out;
}

/** A frosted backdrop of `src`: scaled down 8x and back (a blur), then multiplied by a dark tint so type sits on it. */
export function frosted(src, tintColor) {
  const w = src.width, h = src.height;
  const small = makeCanvas(w / 8, h / 8);
  const sg = getCtx(small);
  sg.imageSmoothingQuality = "high";
  sg.drawImage(src, 0, 0, small.width, small.height);
  const soft = blurCanvas(small, 1.5);
  const out = makeCanvas(w, h);
  const g = getCtx(out);
  g.imageSmoothingQuality = "high";
  g.drawImage(soft, 0, 0, w, h);
  g.globalCompositeOperation = "multiply";
  g.fillStyle = rgb(tintColor);
  g.fillRect(0, 0, w, h);
  return out;
}
