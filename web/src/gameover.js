// The results screen: the score counts up over the blurred wall (GameOver in ninja/game.py).
// It is the last screen of a run: it reads the finished Play (score, stats, mode) and offers Retry or Menu.
// The buttons are fruit you slice, so the whole game is played with the same gesture.
import { W, GOLD, WASHI, MUTED, MODES } from "./config.js";
import { frosted } from "./gfx.js";
import { label, blit, rectAt } from "./ui.js";
import { World } from "./world.js";
import { Scene, SliceButton } from "./menu.js";

//
// The Game Over scene. A scene is one screen with handle(event), update(dt) and draw().
export class GameOver extends Scene {
  constructor(app, play, snap) {
    super();
    // Timeline: COUNT_AT = seconds before counting starts, COUNT = how long the count-up takes.
    this.COUNT_AT = 0.45; this.COUNT = 1.3; // the score counts up once the 終 seal has landed
    this.app = app; this.play = play;
    // A World is the fruit/particle playground; here it sits on a frosted (blurred, dimmed) snapshot of the last frame.
    this.w = new World(app, frosted(snap, [100, 92, 88]));
    this.t = 0;
    this.newBest = play.score > play.bestPrev && play.score > 0;
    this.retry = new SliceButton(this.w, "watermelon", W * 0.38, 548, "再", "Retry", app.touch ? "" : "or press Enter", "", 72);
    this.menu = new SliceButton(this.w, "apple", W * 0.62, 548, "戻", "Menu", app.touch ? "" : "or press Esc", "", 72);
    this.choice = null; this.choiceT = 0;
    // stamped tracks the seal animations: 0 none yet, 1 "Game over" seal shown, 2 "New best" seal shown.
    this.stamped = 0;
    this.shown = 0;
  }

  // Keyboard and mouse input: Enter/R/Space retries, Esc goes back to the menu.
  handle(e) {
    if (e.type === "down" && e.button === 0) this.tap(e.x, e.y);
    else if (e.type === "key" && !this.choice) {
      if (e.key === "enter" || e.key === "r" || e.key === " ") {
        this.retry.cut(); // the same answer a swipe gets: the fruit splits and its seal lands
        this.pick("retry");
      } else if (e.key === "escape") {
        this.menu.cut();
        this.pick("menu");
      }
    }
  }

  // Ignores taps for the first 0.6 s so a leftover swipe from the game can't pick a button by accident.
  tap(x, y) {
    if (this.choice || this.t < 0.6) return;
    if (this.retry.hit(x, y)) { this.retry.cut(); this.pick("retry"); }
    else if (this.menu.hit(x, y)) { this.menu.cut(); this.pick("menu"); }
  }

  // Records the choice; update() waits a moment so the cut animation can play before changing scene.
  pick(c) { this.choice = c; this.choiceT = 0; }

  update(dt) {
    this.t += dt;
    this.w.update(dt, dt);
    const u = Math.min(1.0, Math.max(0.0, (this.t - this.COUNT_AT) / this.COUNT));
    // Ease-out cubic: 1 - (1-u)^3 is fast at first and slows down onto the final number.
    this.shown = this.play.score * (1 - (1 - u) ** 3); // fast at first, easing onto the final number
    if (this.stamped === 0 && this.t > 0.2) {
      this.stamped = 1;
      this.w.stamp("終", this.play.time !== null ? "Time's up" : "Game over", W / 2, 104, 88, WASHI, null, true);
    }
    if (this.stamped === 1 && this.newBest && this.t > this.COUNT_AT + this.COUNT) {
      this.stamped = 2;
      this.w.stamp("極", "New best", W / 2 + 300, 280, 104, WASHI, null, true);
      this.w.particles.sparks(W / 2 + 300, 280, GOLD, 60, 700);
      this.app.audio.play("power");
    }
    if (this.t > 0.6 && !this.choice) {
      const pointer = this.app.pointerActive ? this.app.mouse : null;
      if (this.retry.update(dt, this.app.segments, pointer)) this.pick("retry");
      else if (this.menu.update(dt, this.app.segments, pointer)) this.pick("menu");
    }
    // After the chosen button has been cut for 0.55 s, start a new game or return to the menu.
    if (this.choice) {
      this.choiceT += dt;
      if (this.choiceT > 0.55) {
        const c = this.choice;
        this.choice = null;
        const mode = this.play.mode;
        this.app.go(c === "retry" ? () => this.app.makePlay(mode) : () => this.app.makeMenu());
      }
    }
  }

  draw() {
    const f = this.app.art.fonts, ui = this.app.ui, p = this.play;
    this.w.draw();
    if (this.t > this.COUNT_AT) {
      const sr = label(ui, f, f.final, String(Math.round(this.shown)), GOLD, [W / 2, 290]);
      const best = this.app.save.best[p.mode];
      label(ui, f, f.mono12, `${MODES[p.mode].title.toUpperCase()}  ·  BEST ${best}`, MUTED, [W / 2, sr.bottom + 6], "center", 3);
      // stats row: quiet labels, the numbers in paper white
      const parts = [["Sliced", p.stats.sliced], ["Best combo", p.stats.best_combo], ["Bombs", p.stats.bombs]];
      const imgs = parts.map(([name, val]) => [f.text(f.mono15, `${name} `, MUTED), f.text(f.mono15, String(val), WASHI)]);
      const gap = 40;
      const total = imgs.reduce((n, [a, b]) => n + a.lw + b.lw, 0) + gap * (imgs.length - 1);
      let x = W / 2 - total / 2;
      const y = sr.bottom + 40;
      for (const pair of imgs) {
        for (const im of pair) {
          const r = rectAt(im.lw, im.lh, "midleft", [x, y]);
          blit(ui, im, r.x, r.y);
          x += im.lw;
        }
        x += gap;
      }
    }
    if (this.t > 0.6) {
      this.retry.draw(ui);
      this.menu.draw(ui);
    }
    this.w.drawOverlay();
  }
}
