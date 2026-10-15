// ui.js - little drawing helpers shared by the HUD, menus and effects.
// They wrap common canvas chores (placing text, drawing images with fading, thin bars).
// Small UI drawing helpers shared by the HUD, the menus and the effects (ninja/hud.py).
import { WASHI } from "./config.js?v=229f44b64d";
import { rgb, rgba } from "./util.js?v=229f44b64d";

// anchor says which point of the rectangle `pos` refers to, e.g. "center", "topleft", "midbottom".
// This mirrors the Python/pygame version so the two games line up.
/** A rectangle from a size and an anchor point, like pygame's img.get_rect(midleft=(x, y)). */
export function rectAt(w, h, anchor, pos) {
  const [px, py] = pos;
  let x = px, y = py;
  if (anchor.includes("right")) x = px - w;
  else if (anchor === "center" || anchor === "midtop" || anchor === "midbottom") x = px - w / 2;
  if (anchor.startsWith("bottom") || anchor === "midbottom") y = py - h;
  else if (anchor === "center" || anchor === "midleft" || anchor === "midright") y = py - h / 2;
  return { x, y, w, h, left: x, top: y, right: x + w, bottom: y + h, centerx: x + w / 2, centery: y + h / 2 };
}

// alpha is opacity (0 invisible .. 1 solid); scale resizes it. lw/lh are the "logical" size: text images are
// rendered extra sharp (bigger than shown), so we draw them at their smaller logical size.
/** Draw a text/UI canvas (made by Fonts.text / hiCanvas) at its logical size. */
export function blit(ctx, img, x, y, alpha = 1, scale = 1) {
  const w = (img.lw ?? img.width) * scale, h = (img.lh ?? img.height) * scale;
  if (alpha <= 0) return;
  const a = ctx.globalAlpha;
  ctx.globalAlpha = a * alpha;
  ctx.drawImage(img, x, y, w, h);
  ctx.globalAlpha = a;
}

// font/s/color pick the look, `tracking` is extra letter spacing.
/** Cached text with a soft shadow, so it reads over the photoreal wall without a hard outline. Returns its rect. */
export function label(ctx, fonts, font, s, color, pos, anchor = "center", tracking = 0, shadow = true, alpha = 1) {
  const img = fonts.text(font, s, color, tracking);
  const r = rectAt(img.lw, img.lh, anchor, pos);
  if (shadow) {
    const sh = fonts.shadow(font, s, tracking);
    blit(ctx, sh, r.centerx - sh.lw / 2, r.centery + 3 - sh.lh / 2, alpha * 0.9);
  }
  blit(ctx, img, r.x, r.y, alpha);
  return r;
}

// frac is how full the bar is, 0..1. right=true fills from the right edge instead of the left.
/** A hairline track with a solid fill (power timers, the Ki meter). */
export function thinBar(ctx, x, y, w, frac, color, h = 2, right = false) {
  ctx.fillStyle = rgba(WASHI, 40 / 255);
  ctx.fillRect(x, y, w, h);
  const fill = Math.trunc(w * Math.max(0, Math.min(1, frac)));
  if (fill > 0) {
    ctx.fillStyle = rgb(color);
    ctx.fillRect(right ? x + w - fill : x, y, fill, h);
  }
}

/** Is (px, py) inside the rect {x, y, w, h}? */
// Handy for hit-testing: did a tap land inside this button?
export const inRect = (r, px, py) => px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h;
