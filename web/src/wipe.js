// The transition between scenes: the old picture is cut in two along a diagonal and the halves part to show the
// new scene underneath (Wipe in ninja/game.py).
import { W, H, VIEW } from "./config.js";
import { shade, rgb } from "./util.js";

export class Wipe {
  /** `snap`: a canvas of the old frame (the whole view, at the render scale). */
  constructor(snap) {
    this.DUR = 0.5;
    this.snap = snap;
    const xt = W * 0.62, xb = W * 0.38;
    // the cut line runs (xt, 0) -> (xb, H), extended to the edges of the view; each half covers everything on its side
    const at = (t) => [xt + (xb - xt) * t, H * t];
    const top = at(-VIEW.oy / H), bottom = at((H + VIEW.oy) / H);
    const left = -VIEW.ox, right = W + VIEW.ox, y0 = -VIEW.oy, y1 = H + VIEW.oy;
    this.polys = [[[left, y0], top, bottom, [left, y1]], [top, [right, y0], [right, y1], bottom]];
    const L = Math.hypot(xb - xt, H);
    this.n = [H / L, -(xb - xt) / L]; // normal pointing right
    this.line = [top, bottom];
    this.t = 0;
  }

  update(dt) {
    this.t += dt;
    return this.t < this.DUR;
  }

  /** `g` draws in stage coordinates over the finished new scene. */
  draw(g) {
    const k = Math.min(1.0, this.t / this.DUR);
    const e = 1 - (1 - k) ** 3;
    const d = e * W * 0.8;
    const [nx, ny] = this.n;
    const offs = [[Math.trunc(-nx * d), Math.trunc(-ny * d - e * 40)], [Math.trunc(nx * d), Math.trunc(ny * d + e * 40)]];
    this.polys.forEach((poly, i) => {
      const [ox, oy] = offs[i];
      g.save();
      g.beginPath();
      poly.forEach(([x, y], j) => (j ? g.lineTo(x + ox, y + oy) : g.moveTo(x + ox, y + oy)));
      g.closePath();
      g.clip();
      g.drawImage(this.snap, -VIEW.ox + ox, -VIEW.oy + oy, VIEW.w, VIEW.h);
      g.restore();
    });
    // the cut's edge glows and travels with each half, burning out as they part
    const c = (1 - k) ** 1.5;
    if (c <= 0.02) return;
    const [[ax, ay], [bx, by]] = this.line;
    g.save();
    g.globalCompositeOperation = "lighter";
    for (const [ox, oy] of offs) {
      for (const [col, w] of [[shade([255, 200, 140], 0.35 * c), 9], [shade([255, 244, 225], c), 2]]) {
        g.strokeStyle = rgb(col);
        g.lineWidth = w;
        g.beginPath();
        g.moveTo(ax + ox, ay + oy);
        g.lineTo(bx + ox, by + oy);
        g.stroke();
      }
    }
    g.restore();
  }
}
