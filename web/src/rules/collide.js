// Geometry the rules share (ninja/entities.py).
import { GRAVITY } from "../config.js";

/** Does the segment (ax,ay)-(bx,by) touch the circle at (cx,cy) with radius r? */
export function segHitsCircle(ax, ay, bx, by, cx, cy, r) {
  const dx = bx - ax, dy = by - ay;
  const L2 = dx * dx + dy * dy;
  const t = L2 === 0 ? 0 : Math.max(0, Math.min(1, ((cx - ax) * dx + (cy - ay) * dy) / L2));
  const px = ax + dx * t, py = ay + dy * t;
  return (cx - px) ** 2 + (cy - py) ** 2 <= r * r;
}

/** Rotate an offset the way the sprite turns on screen (counter-clockwise, degrees). */
export function rotateVec(x, y, deg) {
  const a = (deg * Math.PI) / 180;
  return [x * Math.cos(a) + y * Math.sin(a), -x * Math.sin(a) + y * Math.cos(a)];
}

/** Fake depth: a thrown sprite swells toward the camera at the top of its arc. */
export function depthScale(age, flight) {
  if (flight === null || flight === undefined) return 1.0;
  const p = Math.min(1, Math.max(0, age / flight));
  return 0.9 + 0.14 * Math.sin(Math.PI * p);
}

/** Time to fall back to the launch height (either way up); null for a static body. */
export function flightTime(vy, isStatic) {
  if (isStatic) return null;
  return Math.max(0.6, (2 * Math.abs(vy)) / GRAVITY);
}
