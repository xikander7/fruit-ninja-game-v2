// The app: the window, the layers, input -> slices, the frame loop, scene changes (App in ninja/game.py).
//
// Layers, all drawn in stage coordinates (1280x720, with the extra wall the window's shape shows around it):
//   L   the lit world            add  glow only (black = none), added over L and bloomed
//   ui  HUD, stamps, text        blade  the player's blade trail, drawn last
// compose() lays them over each other with the camera (zoom, shake) and colour grade applied to the world only.
import { W, H, VIEW, SLICE_SPEED, MAX_JUMP, BLADES, MODES, INK } from "./config.js";
import { uniform, rgb } from "./util.js";
import { gfx, makeCanvas, getCtx, glowImg } from "./gfx.js";
import { Trail, bladeToolModel, drawBladeTool } from "./fx.js";
import { loadSave, writeSave } from "./rules/save.js";
import { LeaderboardClient } from "./rules/leaderboard.js";
import { Menu } from "./menu.js";
import { Play } from "./play.js";
import { GameOver } from "./gameover.js";
import { Wipe } from "./wipe.js";
import { bladeColors } from "./hazards.js";

const MAX_RS = 2;

export function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

export async function enterFullscreen() {
  const el = document.documentElement;
  try {
    if (el.requestFullscreen) await el.requestFullscreen({ navigationUI: "hide" });
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
  } catch (e) { /* refused (iPhone Safari has no fullscreen): the page still fills the screen */ }
  try { await screen.orientation.lock("landscape"); } catch (e) { /* desktop, or not supported */ }
}

export async function toggleFullscreen() {
  if (fullscreenElement()) {
    try { await (document.exitFullscreen || document.webkitExitFullscreen).call(document); } catch (e) { /* ignore */ }
  } else await enterFullscreen();
}

/** Begin the game synchronously while a best-effort fullscreen/orientation request continues in the background. */
export function startImmediately(fullscreenAttempt, begin) {
  Promise.resolve(fullscreenAttempt).catch(() => {});
  return begin();
}

export class App {
  constructor({ canvas, art, audio, storage, touch, leaderboard = new LeaderboardClient() }) {
    this.canvas = canvas;
    this.S = getCtx(canvas);
    this.art = art; this.audio = audio; this.storage = storage; this.touch = touch;
    this.save = loadSave(storage);
    this.leaderboard = leaderboard;
    this.globalBest = null;
    if (this.save.muted) audio.muted = true;
    this.trail = new Trail();
    this.now = 0; this.speed = 0;
    this.mouse = [W / 2, H / 2];
    this.segments = [];
    this.lastSwoosh = 0;
    this.pointerActive = !touch; // a mouse is always there; a finger only while it touches
    this.events = [];
    this.wipe = null;
    this.quality = 2; // 2 full bloom, 1 light bloom, 0 none: stepped down if frames run long
    this.avgDt = 1 / 60; this.slowFrames = 0;
    this.bloomOn = true;
    this.resize();
    this.scene = new Menu(this);
    this.audio.startMusic();
    void this.refreshGlobalScores();
  }

  persist() { writeSave(this.storage, this.save); }
  makePlay(mode) { return new Play(this, mode); }
  makeMenu() { return new Menu(this); }
  makeGameOver(play, snap) { return new GameOver(this, play, snap); }

  async refreshGlobalScores() {
    try {
      const scores = await this.leaderboard.loadScores();
      if (!scores) return null;
      this.globalBest = scores;
      if (this.scene && typeof this.scene.refreshScores === "function") this.scene.refreshScores();
      return scores;
    } catch (_error) {
      return null;
    }
  }

  async submitGlobalRun(play) {
    try {
      const run = await play.remoteRunPromise;
      if (!run) return null;
      const result = await this.leaderboard.finishRun(run, {
        mode: play.mode,
        score: play.score,
        elapsed: Math.max(1, Math.round(play.elapsed)),
        stats: { ...play.stats },
      });
      if (!result) return null;
      if (!this.globalBest) this.globalBest = Object.fromEntries(Object.keys(MODES).map((mode) => [mode, 0]));
      this.globalBest[result.mode] = Math.max(this.globalBest[result.mode], result.globalBest);
      if (this.scene && typeof this.scene.refreshScores === "function") this.scene.refreshScores();
      return result;
    } catch (_error) {
      return null;
    }
  }

  /** Fit the view to the window: the stage plus extra wall for the window's shape, so the picture always fills it. */
  resize() {
    const vv = window.visualViewport;
    let cw = Math.max(200, Math.floor(vv ? vv.width : window.innerWidth));
    let ch = Math.max(200, Math.floor(vv ? vv.height : window.innerHeight));
    // a phone held upright: draw the game turned a quarter, filling the long side, so no one has to rotate (or unlock) the phone
    this.turned = this.touch && ch > cw;
    if (this.turned) [cw, ch] = [ch, cw];
    const aspect = cw / ch;
    let vw = W, vh = H;
    if (aspect >= W / H) vw = Math.min(Math.round(H * aspect), Math.round(H * 2.4)); // wider than 16:9: more wall at the sides
    else vh = Math.min(Math.round(W / aspect), Math.round(W / 1.6)); // taller: more wall above and below
    vw += vw % 2; vh += vh % 2;
    const scale = Math.min(cw / vw, ch / vh);
    const dw = Math.floor(vw * scale), dh = Math.floor(vh * scale);
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const RS = Math.max(1, Math.min(this.touch ? 1.5 : MAX_RS, Math.round(((dw * dpr) / vw) * 4) / 4));
    VIEW.w = vw; VIEW.h = vh; VIEW.ox = (vw - W) / 2; VIEW.oy = (vh - H) / 2;
    gfx.RS = RS;
    this.RS = RS;
    const px = Math.round(vw * RS), py = Math.round(vh * RS);
    this.canvas.width = px; this.canvas.height = py;
    this.canvas.style.width = `${dw}px`; this.canvas.style.height = `${dh}px`;
    this.canvas.classList.toggle("turned", this.turned);
    this.disp = [dw, dh];
    const layer = (w, h) => { const c = makeCanvas(w, h); return [c, getCtx(c)]; };
    [this.Lc, this.L] = layer(vw, vh);
    [this.addc, this.add] = layer(vw, vh);
    [this.uic, this.ui] = layer(px, py);
    [this.bladec, this.blade] = layer(px, py);
    this.bloomc = [2, 4, 8, 16].map((k) => layer(Math.ceil(vw / k), Math.ceil(vh / k)));
    this.L.setTransform(1, 0, 0, 1, VIEW.ox, VIEW.oy);
    this.add.setTransform(1, 0, 0, 1, VIEW.ox, VIEW.oy);
    this.ui.setTransform(RS, 0, 0, RS, RS * VIEW.ox, RS * VIEW.oy);
    this.blade.setTransform(RS, 0, 0, RS, RS * VIEW.ox, RS * VIEW.oy);
    this.S.imageSmoothingEnabled = true;
    this.S.imageSmoothingQuality = "high";
  }

  /** A copy of the last picture shown (wipes and the results backdrop start from it). */
  snapshot() {
    const c = makeCanvas(this.canvas.width, this.canvas.height);
    getCtx(c).drawImage(this.canvas, 0, 0);
    return c;
  }

  go(makeScene) {
    const snap = this.snapshot();
    this.scene = makeScene();
    this.wipe = new Wipe(snap);
    this.audio.play("swoosh", 0.9);
  }

  pressIcon(name) {
    if (name === "mute") {
      this.audio.toggleMute();
      this.save.muted = this.audio.muted;
      this.persist();
    } else if (name === "full") toggleFullscreen();
  }

  // ---------------- one frame ----------------

  /** One frame: input, update, draw, present. `realDt` is the time since the last frame, in seconds. */
  frameStep(realDt) {
    const dt = Math.min(realDt, 1 / 20);
    this.adapt(realDt);
    this.step(dt, this.events.splice(0));
    this.compose();
  }

  /** If frames keep running long, step the glow down a level: a steady frame rate beats a prettier slideshow. */
  adapt(realDt) {
    this.avgDt += (Math.min(realDt, 0.1) - this.avgDt) * 0.05;
    this.slowFrames = this.avgDt > 0.026 ? this.slowFrames + 1 : 0;
    if (this.slowFrames > 90 && this.quality > 0) {
      this.quality -= 1; this.slowFrames = 0; this.avgDt = 1 / 60;
      const w = this.scene && this.scene.w;
      if (w) w.particles.CAP = Math.min(w.particles.CAP, this.quality ? 700 : 350);
    }
  }

  step(dt, events) {
    this.now += dt;
    let pts = [this.mouse];
    for (const e of events) {
      if (e.type === "move") {
        const p = [e.x, e.y];
        if (e.reset || Math.hypot(pts[pts.length - 1][0] - p[0], pts[pts.length - 1][1] - p[1]) > MAX_JUMP) { // re-entered the window / a new touch: don't cut across the screen
          pts = [p];
          this.trail.cut();
        } else pts.push(p);
        this.mouse = p;
        this.trail.add(p[0], p[1], this.now);
        continue;
      }
      if (e.type === "key" && e.key === "m") this.pressIcon("mute");
      else if (e.type === "key" && e.key === "f") toggleFullscreen();
      else if (e.type === "blur") { this.scene.focusLost(); continue; }
      else if (e.type === "up") continue;
      this.scene.handle(e);
    }
    this.segments = [];
    this.speed = 0;
    if (pts.length >= 2 && dt > 0) {
      let path = 0;
      for (let i = 1; i < pts.length; i++) path += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      this.speed = path / dt;
      if (this.speed > SLICE_SPEED) {
        for (let i = 1; i < pts.length; i++) {
          const [a, b] = [pts[i - 1], pts[i]];
          if (a[0] !== b[0] || a[1] !== b[1]) this.segments.push([a[0], a[1], b[0], b[1]]);
        }
      }
      if (this.speed > 1500 && this.now - this.lastSwoosh > 0.18) {
        this.lastSwoosh = this.now;
        this.audio.play("swoosh", 0.55);
      }
    }
    this.trail.update(this.now);
    const w = this.scene.w;
    if (w && this.speed > 1500 && pts.length >= 2) { // sparks thrown off the blade tip on a fast flick
      const [ax, ay] = pts[pts.length - 2], [bx, by] = pts[pts.length - 1];
      const L = Math.hypot(bx - ax, by - ay) || 1;
      const col = BLADES[this.save.blade][2];
      for (let i = 0; i < 2; i++) {
        const sp = uniform(120, 420), j = uniform(-0.6, 0.6);
        const vx = -(bx - ax) / L, vy = -(by - ay) / L;
        w.particles.add(bx, by, (vx - vy * j) * sp, (vy + vx * j) * sp, uniform(0.15, 0.28), uniform(1, 1.8), col, "spark", 0.6);
      }
    }
    this.scene.update(dt);
    this.resetLayers();
    this.scene.draw();
    if (this.wipe && !this.wipe.update(dt)) this.wipe = null;
  }

  resetLayers() {
    const { L, add, ui } = this;
    for (const g of [L, add, ui]) { g.globalAlpha = 1; g.globalCompositeOperation = "source-over"; }
    add.fillStyle = "#000";
    add.fillRect(-VIEW.ox, -VIEW.oy, VIEW.w, VIEW.h);
    add.globalCompositeOperation = "lighter";
    ui.save();
    ui.setTransform(1, 0, 0, 1, 0, 0);
    ui.clearRect(0, 0, this.uic.width, this.uic.height);
    ui.restore();
  }

  /** Lay the layers over each other onto the visible canvas. */
  compose() {
    const S = this.S, RS = this.RS, sc = this.scene;
    const { w: vw, h: vh, ox, oy } = VIEW;
    const p = sc.fxParams();
    S.setTransform(1, 0, 0, 1, 0, 0);
    S.globalCompositeOperation = "source-over";
    S.globalAlpha = 1;
    S.fillStyle = rgb(INK);
    S.fillRect(0, 0, this.canvas.width, this.canvas.height);
    if (sc.paused && sc.frozen) { // a held, blurred frame behind the pause card
      S.drawImage(sc.frozen, 0, 0, this.canvas.width, this.canvas.height);
    } else {
      S.save();
      S.scale(RS, RS);
      S.translate(vw / 2, vh / 2);
      S.scale(p.zoom, p.zoom); // the camera: a combo punches in, a bomb shakes
      S.translate(-vw / 2 + p.shake[0], -vh / 2 + p.shake[1]);
      S.drawImage(this.Lc, 0, 0);
      S.globalCompositeOperation = "lighter";
      S.drawImage(this.addc, 0, 0);
      if (this.quality > 0) this.drawBloom(S, vw, vh);
      S.restore();
      if (p.saturation < 0.995) { // drain the colour: a grey laid over with the 'saturation' blend
        S.globalCompositeOperation = "saturation";
        S.fillStyle = `rgba(128,128,128,${1 - p.saturation})`;
        S.fillRect(0, 0, this.canvas.width, this.canvas.height);
        S.globalCompositeOperation = "source-over";
      }
      S.setTransform(RS, 0, 0, RS, RS * ox, RS * oy);
      sc.drawScreenFx(S);
      if (p.flash > 0) {
        S.globalCompositeOperation = "lighter";
        S.fillStyle = `rgba(255,255,255,${Math.min(1, p.flash)})`;
        S.fillRect(-ox, -oy, vw, vh);
        S.globalCompositeOperation = "source-over";
      }
    }
    S.setTransform(1, 0, 0, 1, 0, 0);
    S.globalAlpha = 1;
    S.drawImage(this.uic, 0, 0);
    if (sc.wantSnapshot) sc.onSnapshot(this.snapshot());
    S.setTransform(RS, 0, 0, RS, RS * ox, RS * oy);
    if (this.wipe) this.wipe.draw(S);
    S.setTransform(1, 0, 0, 1, 0, 0);
    this.drawBlade();
  }

  /** Bloom: the glow layer shrunk through a chain of halvings (each is a blur) and added back, soft and wide. */
  drawBloom(S, vw, vh) {
    let src = this.addc;
    for (const [c, g] of this.bloomc) {
      g.globalCompositeOperation = "copy";
      g.drawImage(src, 0, 0, c.width, c.height);
      src = c;
    }
    const strength = [0, 0.5, 0.45, 0.4];
    S.globalCompositeOperation = "lighter";
    const levels = this.quality >= 2 ? [1, 2, 3] : [1];
    for (const i of levels) {
      S.globalAlpha = strength[i];
      S.drawImage(this.bloomc[i][0], 0, 0, vw, vh);
    }
    S.globalAlpha = 1;
  }

  drawBlade() {
    const S = this.S, B = this.blade, RS = this.RS;
    const skin = BLADES[this.save.blade];
    const colors = bladeColors(this.scene) || skin.slice(0, 3);
    const live = this.trail.pts.filter((q) => q);
    if (!this.pointerActive && !live.length) return;
    const xs = live.map((q) => q[0]).concat(this.pointerActive ? [this.mouse[0]] : []);
    const ys = live.map((q) => q[1]).concat(this.pointerActive ? [this.mouse[1]] : []);
    const x0 = Math.max(-VIEW.ox, Math.min(...xs) - 70), x1 = Math.min(W + VIEW.ox, Math.max(...xs) + 70);
    const y0 = Math.max(-VIEW.oy, Math.min(...ys) - 70), y1 = Math.min(H + VIEW.oy, Math.max(...ys) + 70);
    if (x1 <= x0 || y1 <= y0) return;
    B.globalCompositeOperation = "source-over";
    B.fillStyle = "#000";
    B.fillRect(x0, y0, x1 - x0, y1 - y0);
    B.save();
    B.beginPath();
    B.rect(x0, y0, x1 - x0, y1 - y0);
    B.clip();
    this.trail.draw(B, colors, this.now, true);
    if (this.pointerActive) {
      const g = glowImg(this.speed > SLICE_SPEED ? 16 : 11, colors[1], 1.0);
      B.globalCompositeOperation = "lighter";
      B.drawImage(g, this.mouse[0] - g.width / 2, this.mouse[1] - g.height / 2);
      B.globalCompositeOperation = "source-over";
      const a = live.length >= 2 ? live[live.length - 2] : [this.mouse[0] - 1, this.mouse[1]];
      const b = live.length ? live[live.length - 1] : this.mouse;
      const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
      drawBladeTool(B, bladeToolModel(skin[4], this.now, this.speed), this.mouse[0], this.mouse[1], dx / len, dy / len, colors);
    }
    B.restore();
    const sx = Math.floor((x0 + VIEW.ox) * RS), sy = Math.floor((y0 + VIEW.oy) * RS);
    const sw = Math.ceil((x1 - x0) * RS), sh = Math.ceil((y1 - y0) * RS);
    S.globalCompositeOperation = "lighter";
    S.drawImage(this.bladec, sx, sy, sw, sh, sx, sy, sw, sh);
    S.globalCompositeOperation = "source-over";
  }
}
