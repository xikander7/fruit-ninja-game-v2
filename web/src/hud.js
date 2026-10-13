// Heads-up display: the Play HUD, the grades over the world, the on-screen buttons (ninja/hud.py).
// The HUD (heads-up display) is everything drawn on top of the game: score, strikes or timer,
// power-up timers, the Ki bar, the boss health bar and the pause/mute buttons.
// "ui" is the canvas context for the top layer. Most coordinates are on the 1280x720 stage.
// Functions here only draw from Play's current state; they never change the game rules.
import { W, H, VIEW, WASHI, GOLD, HANKO, MUTED, FRUITS } from "./config.js";
import { rgb, rgba, lerpRgb, TAU } from "./util.js";
import { label, thinBar, blit, rectAt } from "./ui.js";
import { brushX, hiCanvas } from "./assets.js";
import { gfx, glowImg } from "./gfx.js";
import { HP as BOSS_HP, CRACK_AT, TALLY_HOLD, TALLY_FADE } from "./rules/boss.js";
import { GRADE as FEVER_GRADE } from "./rules/fever.js";
import { FREEZE_TIME, FLIP_TIME, ICE, VIOLET } from "./rules/hazards.js";
import { KI_MAX } from "./rules/ki.js";
import { drawHazardGrades } from "./hazards.js";

// Width (px) of the Ki bar. Ki is a meter that fills with cuts and unlocks the three superpowers.
export const KI_W = 180;
// Width (px) of the boss health bar.
const BOSS_W = 360;

// Draws the whole in-game HUD once per frame. The layout flows downward on the right: strikes or timer first,
// then one chip per active power-up, so "y" tracks where the next item goes.
export function drawPlayHud(play, ui) {
  const f = play.app.art.fonts;
  // score: left, gold, the number rolls toward the real value
  label(ui, f, f.mono12, "SCORE", MUTED, [42, 34], "midleft", 4);
  const sr = label(ui, f, f.score, String(Math.round(play.shown)), GOLD, [38, 44], "topleft");
  const best = Math.max(play.bestPrev, play.score);
  label(ui, f, f.mono13, `Best ${best}`, MUTED, [42, sr.bottom + 6], "midleft");
  let y;
  if (play.mode === "classic" || play.mode === "path") { // strikes (path: lives lost): three brush marks, empty until missed
    for (let i = 0; i < 3; i++) {
      const cx = W - 66 - (2 - i) * 52;
      if (i < play.strikes) {
        const img = brushX(40, HANKO);
        const p = play.strikePop[i];
        const k = p > 0 ? 1 + p * 1.6 : 1; // lands big and settles, like the brush hitting paper
        blit(ui, img, cx - (img.lw * k) / 2, 62 - (img.lh * k) / 2, 1, k);
      } else {
        const img = brushX(40, WASHI, true);
        blit(ui, img, cx - img.lw / 2, 62 - img.lh / 2, 0.25);
      }
    }
    y = 112;
  } else {
    label(ui, f, f.mono12, "TIME", MUTED, [W - 42, 34], "midright", 4);
    const t = Math.max(0, play.time);
    const col = t <= 5 ? HANKO : t <= 10 ? GOLD : WASHI;
    const s = t > 0 || play.state !== "play" ? `${Math.trunc(t / 60)}:${String(Math.trunc(t) % 60).padStart(2, "0")}` : "0:00";
    const img = f.text(f.timer, s, col), sh = f.shadow(f.timer, s);
    let r = rectAt(img.lw, img.lh, "topright", [W - 38, 44]);
    let k = 1;
    if (t <= 5 && play.state === "play") { // each second lands with a pulse
      const p = t > 0 ? (Math.ceil(t) - t) ** 3 : 0;
      k = 1 + 0.14 * p;
      r = rectAt(img.lw * k, img.lh * k, "midright", [r.right, r.centery]);
    }
    blit(ui, sh, r.centerx - (sh.lw * k) / 2, r.centery + 3 - (sh.lh * k) / 2, 230 / 255, k);
    blit(ui, img, r.x, r.y, 1, k);
    y = r.bottom + 18;
  }
  // power-up chips: what's active and how long it has left
  // Each chip is [time left, total time, label, colour]; the bar under the label shows left / total.
  const chips = [[play.freeze, 6.0, "FREEZE", FRUITS.freeze.juice], [play.frenzy, 4.5, "FRENZY", FRUITS.frenzy.juice],
    [play.double, 8.0, "DOUBLE ×2", FRUITS.double.juice], [play.bladeFrozen, FREEZE_TIME, "BLADE FROZEN", ICE],
    [play.hz.flipT, FLIP_TIME, "GRAVITY FLIPPED", VIOLET]];
  for (const [val, total, name, col] of chips) {
    if (val > 0) {
      label(ui, f, f.mono12, name, col, [W - 42, y], "midright", 3);
      thinBar(ui, W - 42 - 140, y + 14, 140, val / total, col, 2, true);
      y += 38;
    }
  }
  drawMult(play, ui, sr);
  const pw = play.power;
  if (pw) { // the running superpower and its time, under the score
    const py = sr.bottom + 40;
    label(ui, f, f.mono12, pw.title, pw.color, [42, py], "midleft", 3);
    thinBar(ui, 42, py + 14, 140, pw.left(), pw.color);
  }
  drawKi(play, ui);
  drawBossBar(play, ui);
}

/** Bottom-left: a quiet hairline that fills with each cut. Full, it is the one thing on screen that glows, and
 * the three powers appear beside it as seals you can tap (or Q W E). */
function drawKi(play, ui) {
  const ki = play.ki;
  if (!ki) return;
  const f = play.app.art.fonts;
  const x = 42, y = H - 40;
  const full = ki.full && !play.power;
  const pulse = 0.5 + 0.5 * Math.sin(play.w.t * 4.5);
  label(ui, f, f.mono12, "KI", full ? GOLD : MUTED, [x, y - 14], "midleft", 4);
  if (full) {
    label(ui, f, f.mono12, "Q  W  E", GOLD, [x + KI_W, y - 14], "midright", 2, true, (150 + 105 * pulse) / 255);
    for (const b of powerButtons()) {
      const seal = play.app.art.seal(b.glyph, 52);
      blit(ui, seal, b.cx - 26, b.cy - 26, 0.7 + 0.3 * pulse);
    }
  }
  thinBar(ui, x, y, KI_W, ki.value / KI_MAX, GOLD, 3);
}

/** The Ki bar's glow, lit for the bloom (drawn additively over the finished picture). */
export function drawKiGlow(play, ctx) {
  const ki = play.ki;
  if (!ki || !ki.full || play.power) return;
  const pulse = 0.5 + 0.5 * Math.sin(play.w.t * 4.5);
  const x = 42, y = H - 40;
  const g = glowImg(48, GOLD, 0.5 + 0.35 * pulse);
  ctx.drawImage(g, x - 30, y - 15, KI_W + 60, 34);
  ctx.fillStyle = rgb(GOLD);
  ctx.fillRect(x, y, KI_W, 3);
}

// Power names with the kanji shown on their seal button, in Q, W, E key order.
export const POWER_ORDER = [["timestop", "止"], ["clones", "影"], ["dragonfire", "炎"]];
/** The three power seals beside a full Ki bar: tap one to use it. */
export function powerButtons() {
  return POWER_ORDER.map(([name, glyph], i) => ({ name, glyph, cx: 280 + i * 64, cy: H - 48 }));
}

/** Small icon buttons, bottom-right: [pause] [mute]. */
export function iconButtons(play) {
  const list = [];
  let cx = W - 44;
  if (play) { list.push({ name: "pause", cx, cy: H - 44 }); cx -= 52; }
  list.push({ name: "mute", cx, cy: H - 44 });
  return list;
}

// Draws the round pause and mute buttons with simple vector shapes (no image files needed).
export function drawIcons(ui, buttons, muted, paused = false) {
  ui.save();
  ui.lineCap = "round"; ui.lineJoin = "round";
  for (const b of buttons) {
    ui.strokeStyle = rgba(WASHI, 0.55); ui.fillStyle = rgba(WASHI, 0.55); ui.lineWidth = 1.5;
    ui.beginPath(); ui.arc(b.cx, b.cy, 18, 0, TAU); ui.strokeStyle = rgba(WASHI, 0.3); ui.stroke();
    ui.strokeStyle = rgba(WASHI, 0.7);
    if (b.name === "pause") {
      if (paused) { ui.beginPath(); ui.moveTo(b.cx - 4, b.cy - 7); ui.lineTo(b.cx + 7, b.cy); ui.lineTo(b.cx - 4, b.cy + 7); ui.closePath(); ui.fill(); }
      else { ui.fillRect(b.cx - 6, b.cy - 7, 4, 14); ui.fillRect(b.cx + 2, b.cy - 7, 4, 14); }
    } else if (b.name === "mute") {
      ui.beginPath(); ui.moveTo(b.cx - 8, b.cy - 3); ui.lineTo(b.cx - 4, b.cy - 3); ui.lineTo(b.cx + 1, b.cy - 8);
      ui.lineTo(b.cx + 1, b.cy + 8); ui.lineTo(b.cx - 4, b.cy + 3); ui.lineTo(b.cx - 8, b.cy + 3); ui.closePath(); ui.fill();
      if (muted) { ui.beginPath(); ui.moveTo(b.cx + 5, b.cy - 5); ui.lineTo(b.cx + 12, b.cy + 5); ui.moveTo(b.cx + 12, b.cy - 5); ui.lineTo(b.cx + 5, b.cy + 5); ui.stroke(); }
      else { ui.beginPath(); ui.arc(b.cx + 2, b.cy, 6, -0.9, 0.9); ui.stroke(); }
    } else if (b.name === "full") {
      for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
        ui.beginPath(); ui.moveTo(b.cx + sx * 8, b.cy + sy * 3); ui.lineTo(b.cx + sx * 8, b.cy + sy * 8); ui.lineTo(b.cx + sx * 3, b.cy + sy * 8); ui.stroke();
      }
    }
  }
  ui.restore();
}

// Returns the button under the pointer (x, y) if it is within 28 px of its centre, else undefined.
export function hitIcon(buttons, x, y) {
  return buttons.find((b) => Math.hypot(x - b.cx, y - b.cy) <= 28);
}

/** The multiplier beside the score: x2..x5 in gold, landing with a small pop each step. During Fever a red seal
 * reads FEVER above it, and a hairline under both runs down with the time left. */
function drawMult(play, ui, sr) {
  const fv = play.fever;
  if (!fv || fv.mult < 2) return;
  const f = play.app.art.fonts;
  const x = sr.right + 16;
  const s = `×${fv.mult}`;
  const img = f.text(f.bonus, s, GOLD), sh = f.shadow(f.bonus, s);
  const k = fv.pop > 0 ? 1 + 0.35 * fv.pop ** 2 : 1;
  const r = rectAt(img.lw * k, img.lh * k, "bottomleft", [x, sr.bottom - 6]);
  blit(ui, sh, r.centerx - (sh.lw * k) / 2, r.centery + 3 - (sh.lh * k) / 2, 230 / 255, k);
  blit(ui, img, r.x, r.y, 1, k);
  if (!fv.active) return;
  const seal = feverSeal(f);
  const sr2 = rectAt(seal.lw, seal.lh, "bottomleft", [x + 2, r.top + 4]);
  blit(ui, seal, sr2.x, sr2.y, Math.min(1, fv.grade() * 1.5));
  thinBar(ui, x + 2, r.bottom + 4, Math.max(sr2.w, r.w), fv.left(), GOLD);
}

// The FEVER seal image is built once and reused; it is rebuilt only if the render scale changes.
let SEAL = null, SEAL_RS = 0;
/** FEVER in washi on a hanko-red seal: square-cornered, a touch uneven, like ink pressed onto paper. */
function feverSeal(f) {
  const RS = gfx.RS;
  if (!SEAL || SEAL_RS !== RS) {
    const t = f.text(f.mono12, "FEVER", WASHI, 3);
    const [c, g] = hiCanvas(t.lw + 14, t.lh + 6);
    g.fillStyle = rgba(HANKO, 235 / 255);
    g.beginPath(); g.roundRect(0, 0, c.lw, c.lh, 2); g.fill();
    g.drawImage(t, c.lw / 2 + 1 - t.lw / 2, c.lh / 2 - t.lh / 2, t.lw, t.lh);
    SEAL = c; SEAL_RS = RS;
  }
  return SEAL;
}

/** Power-up and Fever grades over the world, under the HUD. `g` is the finished picture's context. */
export function drawGrades(play, g) {
  const w = play.w, art = play.app.art, view = art.view(VIEW.w, VIEW.h);
  const full = () => g.fillRect(-VIEW.ox, -VIEW.oy, VIEW.w, VIEW.h);
  const multiply = (c) => { g.globalCompositeOperation = "multiply"; g.fillStyle = rgb(c); full(); g.globalCompositeOperation = "source-over"; };
  if (play.freeze > 0) { // a cold grade that fades in and out with the effect
    const k = Math.min(1, play.freeze / 0.6);
    multiply(lerpRgb([255, 255, 255], [190, 214, 240], k));
    g.globalAlpha = k;
    g.drawImage(view.frost, -VIEW.ox, -VIEW.oy);
    g.globalAlpha = 1;
  }
  if (play.frenzy > 0) { // embers at the edges, breathing slowly
    const k = Math.min(1, play.frenzy / 0.5);
    g.globalAlpha = Math.min(1, k * (0.75 + 0.25 * Math.sin(w.t * 5)));
    g.drawImage(view.ember, -VIEW.ox, -VIEW.oy);
    g.globalAlpha = 1;
  }
  drawHazardGrades(play, g, view);
  const k = play.fever ? play.fever.grade() : 0;
  if (k > 0) multiply(lerpRgb([255, 255, 255], FEVER_GRADE, k)); // Fever's warm gold
}

/** Top centre while a boss is up: its name in Cormorant SC over a thin hanko-red bar, with a pale trail where the
 * last hits took the HP and hairline notches where the rind cracks. */
function drawBossBar(play, ui) {
  const b = play.boss ? play.boss.active : null;
  if (!b) return;
  const f = play.app.art.fonts;
  drawBossTally(b, f, ui);
  // Fade the boss bar in while the boss rises, out while it escapes or dies; a is opacity 0-1.
  const a = b.phase === "rise" ? Math.min(1, b.t / 0.4) : b.phase === "escape" ? Math.max(0, 1 - b.t / 0.5)
    : b.phase === "dead" ? Math.max(0, 1 - b.deadT / 0.6) : 1.0;
  if (a <= 0) return;
  const x = W / 2 - BOSS_W / 2, y = 50;
  label(ui, f, f.boss, b.title, WASHI, [W / 2, y - 16], "center", 2, true, a);
  ui.save();
  ui.globalAlpha = a;
  // Three bars stacked: faint track, pale "recent damage" trail (b.shown), then the red real HP (b.hp).
  ui.fillStyle = rgba(WASHI, 40 / 255); ui.fillRect(x, y, BOSS_W, 4);
  ui.fillStyle = rgba(WASHI, 150 / 255); ui.fillRect(x, y, Math.trunc((BOSS_W * b.shown) / BOSS_HP), 4);
  ui.fillStyle = rgb(HANKO); ui.fillRect(x, y, Math.trunc((BOSS_W * b.hp) / BOSS_HP), 4);
  ui.fillStyle = "rgba(0,0,0,0.63)";
  for (const h of CRACK_AT) ui.fillRect(x + Math.trunc((BOSS_W * h) / BOSS_HP), y, 1, 4);
  ui.restore();
}

/** One "+N" off the boss's upper right that counts up the current run of hits: it pops on each hit and fades. */
function drawBossTally(b, f, ui) {
  if (!b.tally) return;
  const a = Math.min(1, (TALLY_HOLD + TALLY_FADE - b.tallyT) / TALLY_FADE);
  if (a <= 0) return;
  const s = `+${b.tally}`;
  const img = f.text(f.bonus, s, GOLD), sh = f.shadow(f.bonus, s);
  // Quick swell right after each hit: pop falls from 1 to 0 in 0.15 s.
  const pop = Math.max(0, 1 - b.tallyT / 0.15);
  const k = pop > 0 ? 1 + 0.3 * pop * pop : 1; // each hit lands with a small swell
  const x = Math.min(Math.max(b.x + b.r * 0.85, 60), W - 60);
  const y = Math.min(Math.max(b.y - b.r * 0.95, 110), H - 60);
  const r = rectAt(img.lw * k, img.lh * k, "midleft", [x, y]);
  blit(ui, sh, r.centerx - (sh.lw * k) / 2, r.centery + 3 - (sh.lh * k) / 2, (230 / 255) * a, k);
  blit(ui, img, r.x, r.y, a, k);
}
