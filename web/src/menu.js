// menu.js - the main menu and the fruit you slice to choose a game mode.
// There are no buttons: each mode is a floating fruit, and cutting it starts that mode.
// Also defines Scene, the tiny base class every screen (menu, play, results) builds on.
// The menu, and the fruit you cut to choose (SliceButton, Menu in ninja/game.py). Menus in this dojo have no buttons.
import { W, H, GOLD, WASHI, MUTED, BLADES, MODES } from "./config.js";
import { uniform, rgb } from "./util.js";
import { label, blit, inRect } from "./ui.js";
import { chevron, hairlineRing } from "./assets.js";
import { segHitsCircle } from "./rules/collide.js";

import { World } from "./world.js";
import { TitleIntro } from "./title.js";

export function scoreLabel(personal, globalBest, mode) {
  const global = globalBest && Number.isSafeInteger(globalBest[mode]) ? globalBest[mode] : "—";
  return `Personal ${personal} · Global ${global}`;
}
import { drawIcons, hitIcon } from "./hud.js";

// A "scene" is one screen of the game. The App calls these methods every frame on whichever scene is active.
// The base versions do nothing; each real screen overrides the ones it needs.
//   handle(e)      react to one input event (see input.js)
//   update(dt)     move things forward by dt seconds
//   draw()         paint the screen
//   focusLost()    the player switched away (pause, etc.)
export class Scene {
  handle() {}
  update() {}
  draw() {}
  focusLost() {}
  fxParams() { return this.w.fxParams(); }
  drawScreenFx() {} // over the finished picture, under the UI: colour grades, glows
}

// Constructor arguments: world = the World it lives in, kind = which fruit, x/y = position on the stage,
// glyph/title/sub/sub2 = the seal symbol and the text lines drawn under it, ring = click/hover radius in pixels.
/** A fruit you cut to choose. */
export class SliceButton {
  constructor(world, kind, x, y, glyph, title, sub = "", sub2 = "", ring = 80) {
    this.world = world; this.kind = kind;
    this.x = x; this.y = y;
    this.glyph = glyph; this.title = title; this.sub = sub; this.sub2 = sub2;
    this.ring = ring;
    // The fruit itself is a real World body, flagged static so gravity leaves it floating.
    this.body = world.throw(kind, x, y, 0, 0, true);
    // Random start time, so the four fruits bob up and down out of step with each other.
    this.t = uniform(0, 6);
    this.cutAt = null;
    this.hover = 0;
  }

  /** Is (x, y) on the fruit? A tap or click chooses it too, for anyone who doesn't swipe. */
  hit(x, y) {
    return this.body.alive && Math.hypot(x - this.x, y - this.y) < this.ring;
  }

  // segments are the blade's recent line pieces [ax, ay, bx, by]; mouse is the pointer position (or null).
  // Returns true on the frame the fruit gets cut.
  update(dt, segments, mouse = null) {
    this.t += dt;
    // The hover glow fades in quickly (6/s) and out a bit slower (4/s).
    const near = mouse !== null && Math.hypot(mouse[0] - this.x, mouse[1] - this.y) < this.ring + 20;
    this.hover = near ? Math.min(1, this.hover + dt * 6) : Math.max(0, this.hover - dt * 4);
    if (this.body.alive) {
      // A gentle 4-pixel bob so the fruit feels alive.
      this.body.y = this.y + Math.sin(this.t * 1.8) * 4;
      for (const seg of segments) {
        // Hit test: does the blade piece cross the fruit? The circle is 25% bigger than the fruit to be forgiving.
        if (segHitsCircle(...seg, this.body.x, this.body.y, this.body.r * 1.25)) {
          this.cut(...seg);
          return true;
        }
      }
    }
    return false;
  }

  /** The fruit is cut; with no segment (a key press) the cut is a diagonal stroke. */
  cut(ax, ay, bx, by) {
    if (!this.body.alive) return;
    if (ax === undefined) [ax, ay, bx, by] = [this.x - 80, this.y - 60, this.x + 80, this.y + 60];
    this.world.cut(this.body, ax, ay, bx, by);
    this.cutAt = this.t;
  }

  // Draws the ring and the labels. `ui` is the 2D canvas context for the interface layer.
  draw(ui) {
    const f = this.world.art.fonts, R = this.ring;
    const ring = hairlineRing(R);
    if (this.cutAt === null) {
      blit(ui, ring, this.x - ring.lw / 2, this.y - ring.lh / 2, (110 + 145 * this.hover) / 255);
    } else { // the ring opens out and is gone, like a ripple from the cut
      const u = Math.min(1.0, (this.t - this.cutAt) / 0.35);
      if (u < 1) { const k = 1 + 0.25 * u; blit(ui, ring, this.x - (ring.lw * k) / 2, this.y - (ring.lh * k) / 2, 1 - u, k); }
    }
    const y = this.y + R + 34;
    label(ui, f, f.mode, this.title, WASHI, [this.x, y], "center", 1);
    if (this.sub) label(ui, f, f.mono15, this.sub, MUTED, [this.x, y + 34]);
    if (this.sub2) label(ui, f, f.best, this.sub2, GOLD, [this.x, y + 64]);
  }
}

// The main menu scene: four mode fruits, a blade picker and some hint text.
export class Menu extends Scene {
  constructor(app) {
    super();
    this.SETTLE = 1.2; // s for the background to drift from 1.04x to rest
    this.app = app;
    this.w = new World(app);
    const best = app.save.best;
    this.buttons = [];
    // Which fruit goes with which mode. The x positions (17%, 39%, 61%, 83% of the width) space them evenly.
    const spec = [["classic", "watermelon"], ["arcade", "dragonfruit"], ["zen", "peach"], ["path", "golden"]];
    spec.forEach(([mode, kind], i) => {
      const m = MODES[mode];
      const b = new SliceButton(this.w, kind, W * [0.17, 0.39, 0.61, 0.83][i], 388, m.glyph, m.title, m.hint,
        scoreLabel(best[mode], app.globalBest, mode));
      b.mode = mode;
      this.buttons.push(b);
    });
    this.chosen = null; this.chosenT = 0;
    this.t = 0;
    this.arrowRects = [];
    this.bgBase = 1.03; // the wall is held slightly oversize so it can drift with the pointer without showing an edge
    this.par = [0.0, 0.0];
    this.setBg();
    this.intro = new TitleIntro(app, this.w);
  }

  refreshScores() {
    for (const button of this.buttons) {
      button.sub2 = scoreLabel(this.app.save.best[button.mode], this.app.globalBest, button.mode);
    }
  }

  // True once the opening title animation (title.js) has finished.
  get introDone() { return this.intro.done; }

  /** Entry drift (1.04x -> 1.0x of rest scale, eased) then a gentle parallax against the pointer. */
  setBg() {
    const u = Math.min(1.0, this.t / this.SETTLE);
    const k = u < 1.0 ? 1 + 0.04 * (1 - u) ** 3 : 1;
    this.w.bgDraw = { scale: this.bgBase * k, dx: -this.par[0], dy: -this.par[1] };
  }

  // Blades unlock when your best score in any mode reaches the blade's threshold (item 3 of its config).
  unlocked() {
    const top = Math.max(...Object.values(this.app.save.best));
    return Object.entries(BLADES).filter(([, b]) => top >= b[3]).map(([n]) => n);
  }

  // Switch to the next (step 1) or previous (step -1) blade, skipping ones still locked, and save the choice.
  cycleBlade(step) {
    const names = Object.keys(BLADES);
    let i = names.indexOf(this.app.save.blade);
    const open = this.unlocked();
    for (let n = 0; n < names.length; n++) {
      i = (i + step + names.length) % names.length;
      if (open.includes(names[i])) break;
    }
    this.app.save.blade = names[i];
    this.app.persist();
    this.app.audio.play("swoosh", 0.6);
  }

  // Pick a mode: cut its fruit and remember the choice; update() starts the game after a short pause.
  choose(b) {
    b.cut();
    this.chosen = b.mode; this.chosenT = 0;
  }

  // Reads input events: number keys 1-4 start a mode, arrows or A/D change blade, the wheel changes blade, a click or tap picks a fruit.
  handle(e) {
    if (e.type === "key") {
      this.intro.skip(); // any key skips the intro (and still does what it does)
      const k = e.key;
      if (k >= "1" && k <= "4" && !this.chosen) this.choose(this.buttons[+k - 1]);
      else if (k === "arrowleft" || k === "a") this.cycleBlade(-1);
      else if (k === "arrowright" || k === "d") this.cycleBlade(1);
    } else if (e.type === "wheel") {
      this.cycleBlade(e.dy < 0 ? -1 : 1);
    } else if (e.type === "down" && e.button === 0) {
      for (const [step, r] of this.arrowRects) if (inRect(r, e.x, e.y)) this.cycleBlade(step);
      const ic = hitIcon(this.icons(), e.x, e.y);
      if (ic) this.app.pressIcon(ic.name);
      else {
        this.intro.skip();
        const b = this.buttons.find((q) => q.hit(e.x, e.y));
        if (b && !this.chosen) this.choose(b);
      }
    }
  }

  // The little fullscreen and mute buttons in the top-right corner.
  icons() {
    return [{ name: "full", cx: W - 44, cy: 40 }, { name: "mute", cx: W - 96, cy: 40 }];
  }

  // Runs every frame: parallax background, intro, fruit cutting, then starting the game once a choice is made.
  update(dt) {
    this.t += dt;
    const [mx, my] = this.app.mouse;
    // Parallax: the wall shifts slightly opposite to the pointer, like a layer far behind the fruit.
    const tx = -(mx / W - 0.5) * 20, ty = -(my / H - 0.5) * 20; // +-10 px, against the pointer like a deeper layer
    // Move only part of the way toward the target each frame, so the motion eases instead of jumping.
    const k = Math.min(1.0, dt * 3);
    this.par[0] += (tx - this.par[0]) * k;
    this.par[1] += (ty - this.par[1]) * k;
    this.setBg();
    if (this.app.speed > 1500) this.intro.skip(); // a fast swipe skips the intro too
    this.w.update(dt, dt);
    this.intro.update(dt);
    for (const b of this.buttons) {
      if (b.update(dt, this.app.segments, this.app.pointerActive ? this.app.mouse : null) && !this.chosen) {
        this.chosen = b.mode; this.chosenT = 0;
      }
    }
    if (this.chosen) {
      this.chosenT += dt;
      // Wait 0.6s so the player sees the fruit burst before the scene changes.
      if (this.chosenT > 0.6) {
        const mode = this.chosen;
        this.chosen = null;
        this.app.go(() => this.app.makePlay(mode));
      }
    }
  }

  // Paints the world first, then the intro, the fruit labels and the blade picker on the UI layer.
  draw() {
    const f = this.app.art.fonts, ui = this.app.ui;
    this.w.draw((L, add) => this.intro.drawWorld(L, add));
    this.intro.drawUi(ui);
    for (const b of this.buttons) b.draw(ui);
    // blade picker: small, bottom-left
    const name = this.app.save.blade;
    const x0 = 48, y = H - 66;
    label(ui, f, f.mono12, "BLADE", MUTED, [x0, y - 30], "midleft", 4);
    this.arrowRects = [];
    const prev = { x: x0 + 4 - 26, y: y - 26, w: 52, h: 52 };
    const nm = label(ui, f, f.best, name, WASHI, [x0 + 24, y], "midleft");
    const nxt = { x: nm.right + 20 - 26, y: y - 26, w: 52, h: 52 };
    for (const [step, rr] of [[-1, prev], [1, nxt]]) {
      this.arrowRects.push([step, rr]);
      const img = chevron(step, MUTED);
      blit(ui, img, rr.x + rr.w / 2 - img.lw / 2, rr.y + rr.h / 2 - img.lh / 2);
    }
    ui.fillStyle = rgb(BLADES[name][1]);
    ui.fillRect(nxt.x + nxt.w / 2 + 4 + 14, y - 1, 22, 2);
    const open = this.unlocked();
    const locked = Object.entries(BLADES).filter(([n]) => !open.includes(n)).map(([n, b]) => [n, b[3]]);
    label(ui, f, f.mono13, locked.length ? `Next: ${locked[0][0]} at best ${locked[0][1]}` : "All blades unlocked", MUTED, [x0, y + 28], "midleft");
    // controls: bottom-right, quiet
    if (this.app.touch) {
      label(ui, f, f.mono13, "Swipe across a fruit to slice it", MUTED, [W - 48, y + 14], "midright");
    } else {
      label(ui, f, f.mono13, "Move the cursor fast to slice a fruit", MUTED, [W - 48, y], "midright");
      label(ui, f, f.mono13, "1–4 quick start  ·  ← → blade  ·  M mute  ·  F fullscreen", MUTED, [W - 48, y + 28], "midright");
    }
    drawIcons(ui, this.icons(), this.app.audio.muted);
    this.w.drawOverlay();
  }
}
