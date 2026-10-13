// Ninja Path hazards: the hooks Play calls and everything they draw (ninja/hazards.py). The rules are in rules/hazards.js.
// Hazards are the extra dangers and tricks in Ninja Path: shurikens to parry, ice bombs that freeze
// your blade, gravity-flip "chaos" fruit and a golden fruit that takes five hits.
// This file holds the hooks Play calls (launch, hit, slice, tick) and the drawing code; counting
// and timing live in rules/hazards.js.
import { W, H, GOLD, STEEL, VIEW, viewLeft, viewRight } from "./config.js";
import { uniform, choice, shade, rgb, rgba, TAU } from "./util.js";
import { circle, line, drawSprite, addGlow } from "./gfx.js";
import { drawShadow } from "./entities.js";
import { segHitsCircle } from "./rules/collide.js";
import {
  Shuriken, FREEZE_TIME, FLIP_TIME, GOLD_HITS, GOLD_GAP, GOLD_HIT_POINTS, GOLD_BONUS, ICE, VIOLET, ICE_BLADE,
  PARRY_SPEED, PARRY_POINTS, SHURIKEN_R,
} from "./rules/hazards.js";

// Creates one shuriken (a throwing star) aimed from (x, y) at the target (tx, ty).
export function throwShuriken(play, x, y, tx, ty) {
  const s = new Shuriken(x, y, tx, ty);
  play.hz.shurikens.push(s);
  play.app.audio.play("shuriken", 0.8);
  return s;
}

/** Launch a shuriken from a random screen edge at the cursor; true when `kind` was one (Play.launch does the rest). */
export function launchHazard(play, kind) {
  if (kind !== "shuriken") return false;
  const edge = choice(["left", "right", "top", "bottom"]);
  let x0, y0;
  if (edge === "left" || edge === "right") {
    x0 = edge === "left" ? viewLeft() - 40 : viewRight() + 40;
    y0 = uniform(H * 0.15, H * 0.85);
  } else {
    x0 = uniform(W * 0.1, W * 0.9);
    y0 = edge === "top" ? -40 : H + 40;
  }
  throwShuriken(play, x0, y0, ...play.app.mouse);
  return true;
}

// Sprays n gold beads in random directions at up to `speed` px/s.
function coins(w, x, y, n, speed) { // gold beads with a bright glint: the coin sparks of a golden hit
  for (let i = 0; i < n; i++) {
    const a = uniform(0, TAU), sp = uniform(0.3, 1.0) * speed;
    w.particles.drop(x, y, Math.cos(a) * sp, Math.sin(a) * sp - 180, uniform(0.5, 0.9), uniform(2.2, 3.4), GOLD);
  }
}

// Turns upside-down gravity on or off (w.gflip = -1 means things fall upward) with a punchy effect.
export function flip(play, on) {
  const w = play.w, hz = play.hz;
  if (on) hz.flipT = FLIP_TIME;
  w.gflip = on ? -1.0 : 1.0;
  hz.punch = 1.0;
  w.zoomPunch(1.02);
  w.shake.kick(0.3);
  if (on) w.stamp("逆", "Gravity flipped", W / 2, H * 0.58, 110); // between Fever's stamp (0.44) and the powers' (0.72)
  play.app.audio.play("gong", 0.5);
}

/** Hazard rules for a hit body; true when the hit is fully handled here (Play.hit does nothing more). */
export function onHit(play, b) {
  const w = play.w;
  // Slicing an ice bomb freezes the blade for a moment instead of scoring.
  if (b.hazard === "ice") {
    b.alive = false;
    play.bladeFrozen = FREEZE_TIME;
    for (let i = 0; i < 26; i++) { // shattered ice: pale glassy beads and cold sparks
      const a = uniform(0, TAU), sp = uniform(150, 650);
      w.particles.drop(b.x, b.y, Math.cos(a) * sp, Math.sin(a) * sp - 120, uniform(0.4, 0.8), uniform(1.6, 3.4), ICE);
    }
    w.particles.sparks(b.x, b.y, [225, 242, 255], 40, 800, 0.5);
    for (let i = 0; i < 8; i++) {
      w.particles.add(b.x, b.y, uniform(-160, 160), uniform(-160, 60), uniform(0.5, 0.9), uniform(30, 60), ICE, "glow", -0.1);
    }
    w.shake.kick(0.35);
    w.flash = Math.max(w.flash, 0.25);
    w.zoomPunch(1.02);
    play.app.audio.play("explode", 0.45);
    return true;
  }
  // The golden fruit takes GOLD_HITS hits; GOLD_GAP stops one swipe counting twice.
  if (b.kind === "golden") {
    const now = w.t;
    if (now - b.hitT < GOLD_GAP) return true; // the same swipe still crossing it
    b.hitT = now;
    b.hp -= 1;
    if (b.hp <= 0) { // the fifth hit cuts it: Play.hit scores it with the bonus
      b.points = GOLD_BONUS;
      coins(w, b.x, b.y, 46, 720);
      w.particles.sparks(b.x, b.y, [255, 236, 170], 50, 950, 0.6);
      w.particles.embers(b.x, b.y, 24, 520);
      w.zoomPunch(1.025);
      w.shake.kick(0.3);
      w.hitstop = Math.max(w.hitstop, 0.06);
      play.app.audio.play("power");
      return false;
    }
    const pts = play.fever ? play.fever.points(GOLD_HIT_POINTS) : GOLD_HIT_POINTS;
    play.addScore(pts);
    w.popups.add(`+${pts}`, b.x + (GOLD_HITS - b.hp - 2.5) * 30, b.y - b.r - 10, GOLD); // side by side, not a heap
    coins(w, b.x, b.y, 12, 420);
    w.particles.sparks(b.x, b.y, GOLD, 14, 520, 0.4);
    if (!b.static) b.vy -= 160 * w.gflip; // each hit juggles it a little higher
    b.spin = -b.spin * 1.4;
    w.shake.kick(0.08);
    play.app.audio.play("splat", 0.5);
    return true;
  }
  // A chaos fruit flips gravity; returning false lets the normal slice scoring continue.
  if (b.kind === "chaos") flip(play, true);
  return false;
}

/** Before the normal slice: a fast blade parries shurikens. True while the blade is frozen (no slicing). */
export function sliceHazards(play) {
  if (play.bladeFrozen > 0) return true;
  const app = play.app, w = play.w;
  if (app.speed <= PARRY_SPEED || (play.power && play.power.blocksSlicing)) return false;
  for (const s of play.hz.shurikens) {
    if (s.parried || s.struck) continue;
    for (const [ax, ay, bx, by] of app.segments) {
      if (segHitsCircle(ax, ay, bx, by, s.x, s.y, SHURIKEN_R)) {
        s.parry(bx - ax, by - ay);
        play.addScore(PARRY_POINTS);
        w.popups.add(`Parry +${PARRY_POINTS}`, s.x, s.y - 40, STEEL, true);
        w.particles.sparks(s.x, s.y, [255, 250, 235], 44, 1100, 0.55);
        w.particles.sparks(s.x, s.y, [255, 196, 110], 26, 700, 0.45);
        w.particles.add(s.x, s.y, 0, 0, 0.18, 46, [230, 240, 255], "glow", 0);
        play.hz.rings.push([s.x, s.y, 0.0]);
        w.hitstop = Math.max(w.hitstop, 0.05);
        w.shake.kick(0.2);
        app.audio.play("shuriken");
        break;
      }
    }
  }
  return false;
}

/** Once a frame (not during hit-stop). Timers run on the game clock, so Time Stop holds them. */
export function tickHazards(play, dt) {
  const hz = play.hz, w = play.w;
  // gdt = "game time": powers like Time Stop scale it to 0 so the hazard timers pause too.
  const gdt = dt * w.powerScale;
  play.bladeFrozen = Math.max(0, play.bladeFrozen - gdt);
  if (hz.flipT > 0) {
    hz.flipT -= gdt;
    if (hz.flipT <= 0) { hz.flipT = 0; flip(play, false); }
  }
  // Effect strengths (punch, red) fade out over time; the numbers are decay speeds per second.
  hz.punch = Math.max(0, hz.punch - dt * 2.2);
  hz.red = Math.max(0, hz.red - dt * 3.0);
  for (const r of hz.rings) r[2] += dt;
  hz.rings = hz.rings.filter((r) => r[2] < 0.3);
  // mdt = "world time": slow-motion slows it, Time Stop holds it at 0.
  const mdt = dt * w.timeScale(); // world time: slow-mo slows it, Time Stop holds it
  const [mx, my] = play.app.mouse;
  for (const s of hz.shurikens) {
    s.update(mdt);
    if (mdt > 0 && !s.parried && !s.struck && s.near(mx, my) && play.app.pointerActive) { // a shuriken held by Time Stop can't strike
      s.struck = true;
      play.loseLife(s.x, "shuriken");
      hz.red = 1.0;
      w.shake.kick(0.7);
      w.particles.sparks(s.x, s.y, [255, 120, 90], 24, 600, 0.4);
      s.vx *= 0.6; s.vy *= 0.6;
    }
  }
  hz.shurikens = hz.shurikens.filter((s) => !s.gone(viewLeft(), viewRight()));
  hz.mistT -= gdt;
  if (hz.mistT <= 0) { // ice bombs breathe a little cold vapour
    hz.mistT = 0.06;
    for (const b of w.bodies) {
      if (b.alive && b.hazard === "ice") {
        w.particles.add(b.x + uniform(-b.r, b.r) * 0.6, b.y + uniform(-b.r, b.r) * 0.6, uniform(-30, 30), uniform(-50, 10),
          uniform(0.4, 0.7), uniform(14, 24), shade(ICE, 0.6), "glow", -0.15);
      }
    }
  }
}

/** The blade's colours when something overrides the player's: frozen (pale ice), else the running power's. */
export function bladeColors(scene) {
  if (scene.bladeFrozen > 0) return ICE_BLADE;
  return (scene.power && scene.power.blade) || null;
}

/** World layer: auras on the special bodies and the shurikens with their trails. */
export function drawHazards(play, L, add) {
  const art = play.app.art, t = play.w.t;
  for (const b of play.w.bodies) {
    if (!b.alive) continue;
    if (b.kind === "golden") { // a warm aura and a ring that tightens with every hit
      addGlow(add, b.r * 1.9, GOLD, 0.22 + 0.06 * Math.sin(t * 7), b.x, b.y);
      // The golden ring shrinks as hp drops, hinting that it is nearly broken.
      const rr = b.r * (1.85 - 0.17 * (GOLD_HITS - b.hp));
      circle(add, b.x, b.y, rr, rgb(shade(GOLD, 0.8)), 2);
      circle(add, b.x, b.y, rr + 4, rgb(shade(GOLD, 0.3)), 1);
    } else if (b.kind === "chaos") {
      addGlow(add, b.r * 2.0, VIOLET, 0.4 + 0.15 * Math.sin(t * 5), b.x, b.y);
    } else if (b.hazard === "ice") {
      addGlow(add, b.r * 1.8, ICE, 0.3, b.x, b.y);
    }
  }
  for (const s of play.hz.shurikens) {
    drawShadow(L, art.shurikenShadow, s.x, s.y, s.ang, 1.0);
    const n = s.trail.length;
    s.trail.forEach(([x, y, a], i) => drawSprite(L, art.shuriken, x, y, a, 1, (70 * (i + 1) / (n + 1)) / 255)); // a faint smear of where it just was
    if (n) line(add, s.trail[0][0], s.trail[0][1], s.x, s.y, [40, 52, 66], 3);
    drawSprite(L, art.shuriken, s.x, s.y, s.ang, 1);
    addGlow(add, 30, STEEL, 0.18, s.x, s.y); // a glint off the steel for the bloom
  }
  // Parry ring: k goes 1 -> 0 over 0.3 s; the ring grows and thins as it fades.
  for (const [x, y, age] of play.hz.rings) { // the parry's metallic ring
    const k = 1 - age / 0.3;
    circle(add, x, y, 12 + 90 * (1 - k * k), rgb(shade([150, 170, 190], k)), Math.max(1, Math.trunc(3 * k)));
  }
}

/** Over the world, under the HUD: frost while the blade is frozen, the chaos violet, a shuriken hit's red. */
// "Grading" = tinting the whole screen. multiply darkens toward a colour; lighter adds light.
export function drawHazardGrades(play, g, view) {
  const hz = play.hz;
  const full = () => g.fillRect(-VIEW.ox, -VIEW.oy, VIEW.w, VIEW.h);
  const multiply = (c) => { g.globalCompositeOperation = "multiply"; g.fillStyle = rgb(c); full(); g.globalCompositeOperation = "source-over"; };
  if (play.bladeFrozen > 0) {
    const k = Math.min(1, play.bladeFrozen / 0.4);
    multiply([200, 222, 245].map((c) => Math.trunc(255 - (255 - c) * 0.5 * k)));
    g.globalAlpha = k;
    g.drawImage(view.frost, -VIEW.ox, -VIEW.oy);
    g.globalAlpha = 1;
  }
  // Violet tint: steady while gravity is flipped, plus a brief stronger pulse (punch squared) at each flip.
  const k = (hz.flipT > 0 ? 0.35 : 0.0) + 0.65 * hz.punch ** 2;
  if (k > 0) multiply([225, 205, 255].map((c) => Math.trunc(255 - (255 - c) * Math.min(1, k)))); // violet grade
  if (hz.red > 0) {
    g.globalCompositeOperation = "lighter";
    g.fillStyle = rgba([255, 0, 0], (110 * hz.red ** 2) / 255);
    full();
    g.globalCompositeOperation = "source-over";
    multiply([255, 170, 160].map((c) => Math.trunc(255 - (255 - c) * hz.red)));
  }
}
