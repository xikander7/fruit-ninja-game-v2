// Small helpers: random numbers (Python's random module, in JS), colours as [r, g, b] arrays.
export const uniform = (a, b) => a + Math.random() * (b - a);
export const randint = (a, b) => a + Math.floor(Math.random() * (b - a + 1)); // inclusive, like Python
export const choice = (arr) => arr[Math.floor(Math.random() * arr.length)];
export const sign = () => (Math.random() < 0.5 ? -1 : 1);
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const dist = (ax, ay, bx, by) => Math.hypot(bx - ax, by - ay);
export const TAU = Math.PI * 2;
export const rad = (deg) => (deg * Math.PI) / 180;
export const deg = (r) => (r * 180) / Math.PI;

/** One item from `items`, picked with the given weights (random.choices(items, weights)[0]). */
export function weighted(items, weights, rnd = Math.random) {
  let total = 0;
  for (const w of weights) total += w;
  let r = rnd() * total;
  for (let i = 0; i < items.length; i++) {
    r -= weights[i];
    if (r < 0) return items[i];
  }
  return items[items.length - 1];
}

/** Normal distribution, mean 0 (Box-Muller). */
export function gauss(sigma = 1) {
  const u = 1 - Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * Math.random()) * sigma;
}

/** A small seeded generator, so procedural art (seals, cracks) is the same every run. */
export function seeded(seed) {
  let h = 2166136261;
  for (const ch of String(seed)) h = Math.imul(h ^ ch.codePointAt(0), 16777619);
  let a = h >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const r = { next, uniform: (lo, hi) => lo + next() * (hi - lo), randint: (lo, hi) => lo + Math.floor(next() * (hi - lo + 1)) };
  r.choice = (arr) => arr[Math.floor(next() * arr.length)];
  return r;
}

// ---- colours ----
export const shade = (c, k) => [0, 1, 2].map((i) => Math.max(0, Math.min(255, Math.trunc(c[i] * k))));
export const tint = (c, k) => [0, 1, 2].map((i) => Math.trunc(c[i] + (255 - c[i]) * k));
export const lerpRgb = (a, b, t) => [0, 1, 2].map((i) => Math.trunc(a[i] + (b[i] - a[i]) * t));
export const rgb = (c) => `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
export const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
export const easeOut = (u, p = 3) => 1 - (1 - Math.min(1, Math.max(0, u))) ** p;
