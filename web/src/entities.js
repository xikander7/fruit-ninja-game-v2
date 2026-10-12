// Things that fly: a thrown fruit, special banana or bomb, and the halves of a cut fruit (ninja/entities.py).
import { FRUITS, H, GRAVITY } from "./config.js";
import { uniform, choice } from "./util.js";
import { drawSprite } from "./gfx.js";
import { depthScale, flightTime } from "./rules/collide.js";

const BLUR_SPEED = 900; // px/s: faster than this, a sprite leaves motion-blur ghosts
const GHOSTS = [[1.0, 18], [0.5, 40]]; // (fraction of a frame back, alpha): a smear, not a second copy

export function drawShadow(ctx, shadow, x, y, ang, s) {
  // the nearer the sprite (bigger s), the further and fainter its shadow on the wall
  const k = Math.min(1, Math.max(0, (s - 0.9) / 0.14));
  const off = 10 + 16 * k;
  drawSprite(ctx, shadow, x + off * 0.59, y + off * 0.81, ang, 1, 0.9 - 0.3 * k);
}

export function drawBody(ctx, img, x, y, ang, s, vx, vy, dt) {
  if (dt > 0 && vx * vx + vy * vy > BLUR_SPEED * BLUR_SPEED) {
    for (const [k, a] of GHOSTS) drawSprite(ctx, img, x - vx * dt * k, y - vy * dt * k, ang, s, a / 255);
  }
  drawSprite(ctx, img, x, y, ang, s);
}

/** A thrown fruit, special banana or bomb. */
export class Body {
  constructor(art, kind, x, y, vx, vy, isStatic = false) {
    this.rain = false; // Fever's rain: dropping one never costs a strike or a life
    this.kind = kind;
    this.bomb = kind === "bomb";
    this.hazard = kind === "icebomb" ? "ice" : ""; // an ice bomb: no fruit, not a bomb either
    this.ft = this.bomb || this.hazard ? null : FRUITS[kind];
    this.special = this.ft === null ? "" : this.ft.special;
    this.r = this.ft === null ? 38 : this.ft.r;
    this.points = this.ft === null ? 0 : this.ft.points; // what a cut scores (the golden fruit's last: more)
    this.hp = kind === "golden" ? 5 : 1; // hits it takes
    this.hitT = -1; // when it was last hit (world time)
    // a drop costs a strike or a life only for ordinary fruit: never bombs, power-ups or the hazard specials
    this.costly = this.ft !== null && !this.special && kind !== "golden" && kind !== "chaos";
    if (this.bomb) { this.img = art.bomb; this.shadow = art.bombShadow; }
    else if (this.hazard) { this.img = art.icebomb; this.shadow = art.icebombShadow; }
    else { const fa = art.fruits[kind]; this.img = fa.whole; this.shadow = fa.shadow; }
    this.x = x; this.y = y; this.vx = vx; this.vy = vy;
    this.ang = uniform(0, 360);
    this.spin = !isStatic ? uniform(-200, 200) : choice([-25, 25]);
    this.static = isStatic;
    this.alive = true;
    this.entered = false;
    this.age = 0; this.flight = flightTime(vy, isStatic); this.dt = 0;
  }

  update(dt, g = GRAVITY) {
    if (!this.static) {
      this.vy += g * dt;
      this.x += this.vx * dt;
      this.y += this.vy * dt;
      if (this.r < this.y && this.y < H - this.r) this.entered = true; // launched from the bottom, or from the top while gravity is flipped
    }
    this.ang += this.spin * dt;
    this.age += dt;
    this.dt = dt;
  }

  scale() { return depthScale(this.age, this.flight); }

  /** Moving away past either edge: gravity can be flipped, so a fruit can also leave over the top. */
  gone() {
    return !this.static && ((this.vy > 0 && this.y > H + this.r * 2) || (this.vy < 0 && this.y < -this.r * 2));
  }

  drawShadow(ctx) { drawShadow(ctx, this.shadow, this.x, this.y, this.ang, this.scale()); }

  draw(ctx) {
    const [vx, vy] = this.static ? [0, 0] : [this.vx, this.vy];
    drawBody(ctx, this.img, this.x, this.y, this.ang, this.scale(), vx, vy, this.dt);
  }
}

export class Half {
  constructor(fruitArt, x, y, vx, vy, outDeg, parent = null) {
    this.img = fruitArt.half; this.shadow = fruitArt.halfShadow;
    this.x = x; this.y = y; this.vx = vx; this.vy = vy;
    this.ang = outDeg - fruitArt.halfLocal;
    this.spin = uniform(-260, 260);
    // halves carry on along the whole fruit's depth arc, so the cut doesn't pop in size
    this.age = parent ? parent.age : 0;
    this.flight = parent ? parent.flight : null;
    this.dt = 0;
  }

  update(dt, g = GRAVITY) {
    this.vy += g * dt;
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.ang += this.spin * dt;
    this.age += dt;
    this.dt = dt;
  }

  gone() { return (this.vy > 0 && this.y > H + 150) || (this.vy < 0 && this.y < -150); }
  scale() { return depthScale(this.age, this.flight); }
  drawShadow(ctx) { drawShadow(ctx, this.shadow, this.x, this.y, this.ang, this.scale()); }
  draw(ctx) { drawBody(ctx, this.img, this.x, this.y, this.ang, this.scale(), this.vx, this.vy, this.dt); }
}
