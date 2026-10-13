// play.js - one round of the game (a "run"): throwing fruit, scoring, combos, strikes, the clock and pause.
// The four modes (classic, arcade, zen, path) all use this one class; MODE_FEATURES in config.js turns extras
// (powers, fever, boss, hazards) on or off per mode. The pure rules live in rules/ and the extras in powers.js,
// fever.js, boss.js and hazards.js.
// A run: spawning, scoring, combos, strikes, the clock, pause (Play in ninja/game.py).
import {
  W, H, GRAVITY, WASHI, GOLD, HANKO, MUTED, FRUITS, REGULAR, WEIGHTS, SPECIALS, MODES, MODE_FEATURES, viewLeft, viewRight,
} from "./config.js";
import { uniform, randint, choice, weighted } from "./util.js";
import { label, blit, inRect } from "./ui.js";
import { brushX } from "./assets.js";
import { frosted } from "./gfx.js";
import { segHitsCircle, rotateVec } from "./rules/collide.js";
import { KiMeter, KI_PER_COMBO } from "./rules/ki.js";
import { Fever } from "./rules/fever.js";
import { Hazards, rollHazard } from "./rules/hazards.js";
import { World } from "./world.js";
import { Scene } from "./menu.js";
import { drawPlayHud, drawGrades, drawKiGlow, powerButtons, iconButtons, drawIcons, hitIcon } from "./hud.js";
import { KEYS as POWER_KEYS, usePower, tickPower, onCut } from "./powers.js";
import { feverCut, tickFever, feverFx } from "./fever.js";
import { makeBossDirector, sliceBoss, tickBoss } from "./boss.js";
import { launchHazard, onHit as hazardHit, sliceHazards, tickHazards, drawHazards } from "./hazards.js";

// The "Quit to menu" button on the pause screen, in stage pixels (x, y = top-left corner).
const QUIT_RECT = { x: W / 2 - 110, y: H / 2 + 78, w: 220, h: 48 };

export function beginRemoteRun(client, mode) {
  if (!client || typeof client.startRun !== "function") return Promise.resolve(null);
  return Promise.resolve().then(() => client.startRun(mode)).catch(() => null);
}

export function saveFinishedRun(play) {
  const save = play.app.save;
  save.best[play.mode] = Math.max(save.best[play.mode], play.score);
  save.total_sliced += play.stats.sliced;
  play.app.persist();
  void play.app.submitGlobalRun(play);
}

// A Scene (see menu.js). `mode` is "classic", "arcade", "zen" or "path".
// state moves through: ready -> play -> (dying | ending) -> over.
export class Play extends Scene {
  // Set up all the counters for a fresh run.
  constructor(app, mode) {
    super();
    this.app = app; this.mode = mode;
    this.features = MODE_FEATURES[mode];
    this.ki = this.features.includes("powers") ? new KiMeter() : null;
    this.power = null; this.lastPower = "timestop";
    this.fever = this.features.includes("fever") ? new Fever() : null;
    this.boss = this.features.includes("boss") ? makeBossDirector() : null;
    this.hz = new Hazards();
    // Seconds left on an ice bomb's frozen blade (can't slice while > 0).
    this.bladeFrozen = 0; // s left of an ice bomb's frozen blade
    this.w = new World(app);
    this.score = 0;
    this.bestPrev = app.save.best[mode];
    this.strikes = 0;
    // Little pop animation timers for the three strike marks.
    this.strikePop = [0, 0, 0];
    this.misses = []; // red X where a fruit dropped
    // Time left in seconds; null means the mode has no clock (classic and path end on strikes instead).
    this.time = { classic: null, arcade: 60.0, zen: 90.0, path: null }[mode];
    this.elapsed = 0;
    // Countdown until the next wave of fruit; the first wave comes after 1.3 seconds.
    this.spawnT = 1.3;
    // Fruit waiting to be launched: [seconds until launch, kind, x].
    this.queue = [];
    this.combo = 0; this.comboT = 0; this.comboPos = [0, 0];
    // Seconds left of the Freeze / Frenzy / Double-score power-fruit effects (0 = off).
    this.freeze = this.frenzy = this.double = 0;
    this.frenzySpawn = 0;
    // Cooldown so power fruit don't appear too often (arcade only).
    this.specialCd = 7.0;
    // Classic gives back a lost strike every 100 points; path gives a life every 150.
    this.lifeEvery = mode === "path" ? 150 : 100; // classic: a strike back per 100; path: a life per 150
    this.nextLife = this.lifeEvery;
    // Numbers shown on the game-over screen.
    this.stats = { sliced: 0, best_combo: 0, bombs: 0, missed: 0 };
    this.state = "ready"; this.stateT = 0;
    this.paused = false;
    // While paused we show a blurred still of the game; it is made once and kept.
    this.frozen = null; // blurred snapshot, made on the first paused frame
    this.wantSnapshot = false;
    // The score on screen counts up smoothly toward the real score.
    this.shown = 0; // the score as displayed: rolls toward this.score
    this.lastTick = null;
    this.remoteRunPromise = beginRemoteRun(app.leaderboard, mode);
    const m = MODES[mode];
    this.w.stamp(m.glyph, "Ready", W / 2, H / 2 - 20, 150);
    app.audio.play("gong");
  }

  // --- spawning ---
  // Throw one fruit (or bomb) up from below the screen. `x` is the start position (random if omitted).
  // The maths: pick how high it should peak (apex), then work out the launch speed that reaches exactly that height
  // under gravity, and the sideways speed so it arcs back toward the middle of the screen.
  launch(kind, x = null) {
    if (launchHazard(this, kind)) return; // a shuriken flies on its own
    const r = kind === "bomb" || kind === "icebomb" ? 38 : FRUITS[kind].r;
    const x0 = x !== null ? x : uniform(W * 0.12, W * 0.88);
    const y0 = H + r + 10;
    // apex = the y position of the highest point. Smaller y is higher up on the screen.
    const apex = uniform(H * 0.07, H * 0.42);
    // From physics: v^2 = 2 * g * distance, so the upward launch speed is sqrt(2 * g * climb). It is negative because up is -y.
    const vy = -Math.sqrt(2 * GRAVITY * (y0 - apex));
    // t = seconds to reach the top (speed / gravity).
    const t = -vy / GRAVITY;
    // Where it should be sideways at the top, kept away from the screen edges.
    const xa = Math.min(Math.max(x0 + uniform(-W * 0.25, W * 0.25), W * 0.18), W * 0.82);
    const flipped = this.w.gflip < 0;
    this.w.throw(kind, x0, flipped ? H - y0 : y0, (xa - x0) / t, flipped ? -vy : vy); // flipped: from the top
    this.app.audio.play("throw", 0.5);
  }

  // One "wave" is a handful of fruit thrown together. The longer you play, the more per wave and the more bombs.
  wave() {
    const e = this.elapsed;
    // The most fruit one wave can have grows with time, up to 6.
    const hi = Math.min(6, 1 + Math.trunc(e / 12) + (this.mode !== "classic" ? 1 : 0));
    const n = randint(1, hi);
    // Chance each fruit is a bomb: none in zen, rising over time in classic, a fixed 15% in other modes.
    const bombP = this.mode === "zen" ? 0.0 : this.mode === "classic" ? Math.min(0.3, 0.06 + e * 0.0025) : 0.15;
    const kinds = Array.from({ length: n }, () => weighted(REGULAR, WEIGHTS));
    for (let i = 0; i < n; i++) {
      if (Math.random() < bombP && (i > 0 || (n === 1 && e > 15))) kinds[i] = "bomb";
    }
    // Never make a wave of only bombs.
    if (kinds.every((k) => k === "bomb")) kinds[0] = weighted(REGULAR, WEIGHTS);
    if (this.features.includes("hazards")) kinds.forEach((k, i) => { kinds[i] = rollHazard(Math.random, e) || k; });
    if (this.mode === "arcade" && this.specialCd <= 0 && Math.random() < 0.45) {
      kinds[0] = choice(SPECIALS);
      this.specialCd = 8.0;
    }
    // "burst" throws all at once, "stagger" one after another, "line" quickly in a row (stagger is listed twice so it is more likely).
    const pattern = choice(["burst", "stagger", "stagger", "line"]);
    // Random launch positions, sorted left to right (and sometimes reversed) so staggered fruit sweep across.
    const xs = kinds.map(() => uniform(W * 0.12, W * 0.88)).sort((a, b) => a - b);
    if (Math.random() < 0.5) xs.reverse();
    kinds.forEach((k, i) => {
      const delay = { burst: 0.0, stagger: i * uniform(0.18, 0.32), line: i * 0.11 }[pattern];
      this.queue.push([delay, k, xs[i]]);
    });
  }

  // Seconds between waves. It shrinks as `elapsed` grows, down to a minimum, so the game speeds up.
  interval() {
    const e = this.elapsed;
    return { classic: Math.max(0.85, 2.2 - e * 0.016), arcade: Math.max(0.6, 1.4 - e * 0.012), zen: Math.max(0.9, 1.7 - e * 0.008),
      path: Math.max(0.75, 2.0 - e * 0.014) }[this.mode];
  }

  // --- scoring ---
  // Add points. In classic and path, crossing each life threshold removes a strike (gives a life back).
  addScore(n) {
    this.score += n;
    if (this.mode === "classic" || this.mode === "path") {
      while (this.score >= this.nextLife) {
        this.nextLife += this.lifeEvery;
        if (this.strikes > 0) {
          this.strikes -= 1;
          this.w.popups.add("+1 life", W - 120, 166, GOLD, true); // rises 54 px: stays clear of the marks
          this.app.audio.play("life");
        }
      }
    }
  }

  // The blade segment `seg` just touched body `b` (a fruit or bomb). Handles bombs, points, crits, combos and power fruit.
  hit(b, seg) {
    const w = this.w;
    if (hazardHit(this, b)) return; // ice bomb, and the golden fruit's first hits
    if (b.bomb) {
      w.explode(b);
      this.stats.bombs += 1;
      if (this.fever) this.fever.reset();
      if (this.mode === "classic") {
        this.state = "dying"; this.stateT = 0;
        this.app.audio.fuse(false);
      } else if (this.mode === "path") {
        this.loseLife(b.x, "bomb");
      } else {
        this.score = Math.max(0, this.score - 10);
        w.popups.add("-10", b.x, b.y - 40, HANKO, true);
      }
      return;
    }
    // Cut the fruit open (visual) then score it.
    w.cut(b, ...seg);
    onCut(this, b); // Ki, and Dragon Fire's ignition
    feverCut(this); // the chain grows before the cut is scored: the cut that starts Fever already pays x5
    // Arcade bonus: 6% of normal fruit are "critical" hits worth +10.
    const crit = this.mode === "arcade" && !b.special && Math.random() < 0.06;
    let pts = b.points * (this.double > 0 ? 2 : 1) + (crit ? 10 : 0);
    if (this.fever) pts = this.fever.points(pts);
    if (crit) {
      w.popups.add(`Critical +${this.fever ? this.fever.points(10) : 10}`, b.x, b.y - 50, GOLD, true);
      w.particles.sparks(b.x, b.y, GOLD, 30, 600);
      w.hitstop = Math.max(w.hitstop, 0.06);
    } else {
      w.popups.add(`+${pts}`, b.x, b.y - 30, pts > b.ft.points ? GOLD : WASHI);
    }
    this.addScore(pts);
    this.stats.sliced += 1;
    this.combo += 1;
    // A combo stays open for 0.28s after each cut; another cut inside that window extends it.
    this.comboT = 0.28;
    if (this.combo === 3) w.zoomPunch(1.015); // the camera answers a combo the moment it happens, not when it's tallied
    else if (this.combo === 4) w.slow();
    this.comboPos = [b.x, b.y];
    if (b.special) {
      // Power fruit: [which timer to start, English seal label, caption, seconds it lasts].
      const [name, glyph, cap, dur] = { freeze: ["freeze", "ICE", "Freeze", 6.0], frenzy: ["frenzy", "RUSH", "Frenzy", 4.5],
        double: ["double", "2X", "Double score", 8.0] }[b.special];
      this[name] = dur;
      w.stamp(glyph, cap, b.x, b.y, 120);
      w.particles.sparks(b.x, b.y, b.ft.juice, 50, 800);
      this.app.audio.play("power");
    }
  }

  // Check the blade against every fruit. app.segments are the line pieces the pointer drew since the last frame.
  slice() {
    if (sliceHazards(this)) return; // parries shurikens; true while an ice bomb has frozen the blade
    sliceBoss(this); // the boss is never in w.bodies (no power targets it); its own hits, here
    if (this.power && this.power.blocksSlicing) return;
    for (const seg of this.app.segments) {
      for (const b of this.w.bodies) {
        // The hit circle is 5% bigger than the fruit so near-misses still count.
        if (b.alive && segHitsCircle(...seg, b.x, b.y, b.r * 1.05)) {
          this.hit(b, seg);
          if (this.state !== "play") return;
        }
      }
    }
  }

  // The combo window closed: 3 or more cuts in a row earns a bonus, Ki energy and a stamp on the wall.
  finishCombo() {
    if (this.combo >= 3) {
      let bonus = this.combo * (this.double > 0 ? 2 : 1);
      if (this.fever) bonus = this.fever.points(bonus);
      this.addScore(bonus);
      if (this.ki) this.ki.add(KI_PER_COMBO * this.combo);
      this.w.stamp("COMBO", `${this.combo} fruit combo`, ...this.comboPos, 100 + Math.min(60, this.combo * 6), WASHI, `+${bonus}`);
      this.w.hitstop = Math.max(this.w.hitstop, 0.05);
      this.app.audio.play("combo");
    }
    this.stats.best_combo = Math.max(this.stats.best_combo, this.combo);
    this.combo = 0;
  }

  /** Path mode's lives are the classic strike marks counted the other way (null in the other modes). */
  get lives() { return this.mode === "path" ? 3 - this.strikes : null; }

  // A fruit fell off the screen uncut.
  strike(b) {
    this.stats.missed += 1;
    if (this.fever && !this.fever.active) this.fever.reset(); // a drop breaks the chain, but never a running Fever
    if (this.mode === "classic" || this.mode === "path") this.loseLife(b.x, "drop");
  }

  /** A strike (classic) or a lost life (path; `reason` is "drop", "bomb" or "shuriken"): a red brush mark where it happened. */
  loseLife(x, reason) {
    if (this.state !== "play") return;
    if (this.fever && (reason !== "drop" || !this.fever.active)) this.fever.reset();
    this.strikePop[this.strikes] = 0.35;
    this.strikes += 1;
    this.misses.push([Math.min(Math.max(x, 40), W - 40), 0.0]);
    this.w.shake.kick(0.3);
    this.app.audio.play("miss");
    if (this.strikes >= 3) { this.state = "dying"; this.stateT = 0; }
  }

  // Shortcut to the power-activation function in powers.js.
  usePower(name) { return usePower(this, name); }

  // --- loop ---
  // Leave the run and go back to the menu.
  quitToMenu() {
    this.app.audio.quiet();
    this.app.go(() => this.app.makeMenu());
  }

  // Input events: Esc/P pauses, Q quits while paused, power keys fire powers, a right-click repeats the last power.
  handle(e) {
    if (e.type === "key") {
      if (e.key === "escape" || e.key === "p") this.paused = !this.paused;
      else if (this.paused && e.key === "q") this.quitToMenu();
      else if (POWER_KEYS[e.key]) this.usePower(POWER_KEYS[e.key]); // usePower refuses unless playing, unpaused and full
    } else if (e.type === "down") {
      if (e.button === 2) { this.usePower(this.lastPower); return; }
      if (e.button !== 0) return;
      if (this.paused) {
        if (inRect(QUIT_RECT, e.x, e.y)) this.quitToMenu();
        else this.paused = false;
        return;
      }
      const ic = hitIcon(iconButtons(this), e.x, e.y);
      if (ic) { if (ic.name === "pause") this.paused = true; else this.app.pressIcon(ic.name); return; }
      if (this.ki && this.ki.full && !this.power) {
        const b = powerButtons().find((p) => Math.hypot(e.x - p.cx, e.y - p.cy) <= 30);
        if (b) this.usePower(b.name);
      }
    }
  }

  // Auto-pause when the player switches tabs or apps.
  focusLost() {
    if (this.state === "play") this.paused = true;
  }

  // Screen effects for this frame (zoom, colour, flash, shake). Powers and fever add their own tweaks.
  fxParams() {
    if (this.paused) return { zoom: 1, saturation: 1, flash: 0, shake: [0, 0] };
    const p = this.w.fxParams();
    if (this.freeze > 0) p.saturation *= 1 - 0.2 * Math.min(1.0, this.freeze / 0.6); // the cold grade also drains a little colour
    if (this.power) this.power.fx(p);
    feverFx(this, p);
    return p;
  }

  // Runs every frame; dt is seconds since the last frame. Order matters: powers, fever, world, state machine, spawning,
  // slicing, boss and hazards, then removing fruit that left the screen.
  update(dt) {
    if (this.paused) {
      this.app.audio.quiet();
      return;
    }
    this.frozen = null;
    const w = this.w;
    tickPower(this, dt);
    tickFever(this, dt);
    // game clock: freeze slows (Time Stop stops) the timer, spawning and difficulty ramp; slow-mo only the world
    // "Game dt": the time the game clock sees. Freeze slows it to 40%, and Time Stop sets powerScale to 0.
    const wdt = dt * (this.freeze > 0 ? 0.4 : 1.0) * w.powerScale;
    w.update(wdt * w.timeScale(), dt);
    // rolling counter: ease toward the real score (also downward after a bomb), snapping once close
    // Exponential smoothing: close 12x dt of the remaining gap each frame.
    this.shown += (this.score - this.shown) * Math.min(1.0, dt * 12);
    if (Math.abs(this.score - this.shown) < 0.5) this.shown = this.score;
    this.strikePop = this.strikePop.map((p) => Math.max(0, p - dt));
    for (const m of this.misses) m[1] += dt;
    this.misses = this.misses.filter((m) => m[1] < 1.2);
    this.stateT += dt;
    if (w.hitstop > 0) {
      if (this.state === "play") this.slice(); // hit-stop freezes the picture, never the blade: a swipe through it still cuts
      return;
    }
    // After the "Ready" stamp (1.1s) the round begins.
    if (this.state === "ready" && this.stateT > 1.1) { this.state = "play"; this.stateT = 0; }
    if (this.state === "play") {
      this.elapsed += wdt;
      for (const k of ["freeze", "frenzy", "double"]) this[k] = Math.max(0, this[k] - dt * w.powerScale);
      this.specialCd -= dt * w.powerScale; // real time, but Time Stop holds it
      if (this.time !== null) {
        this.time -= wdt;
        if (this.time > 0 && this.time <= 5 && Math.ceil(this.time) !== this.lastTick) {
          this.lastTick = Math.ceil(this.time);
          this.app.audio.play("tick");
        }
        // Time ran out: show "Time's up" and let the ending state play before the results.
        if (this.time <= 0) {
          this.time = 0;
          this.state = "ending"; this.stateT = 0;
          w.stamp("TIME", "Time's up", W / 2, H / 2 - 20, 150);
          this.app.audio.play("gong");
        }
      }
      // Count down each queued fruit and launch it when its delay hits zero.
      for (const q of this.queue) {
        q[0] -= wdt;
        if (q[0] <= 0) this.launch(q[1], q[2]);
      }
      this.queue = this.queue.filter((q) => q[0] > 0);
      this.spawnT -= wdt;
      if (this.spawnT <= 0 && !this.queue.length && !(this.boss && this.boss.pauseWaves)) {
        this.wave();
        this.spawnT = this.interval();
      }
      // Frenzy power: extra fruit fly in from both sides every 0.09s.
      if (this.frenzy > 0) {
        this.frenzySpawn -= dt * w.powerScale;
        if (this.frenzySpawn <= 0) {
          this.frenzySpawn = 0.09;
          const side = choice([-1, 1]);
          const kind = weighted(REGULAR, WEIGHTS);
          const x0 = side < 0 ? viewLeft() - 40 : viewRight() + 40;
          w.throw(kind, x0, uniform(H * 0.4, H * 0.85), -side * uniform(380, 700), -uniform(450, 850));
        }
      }
      this.slice();
      if (this.combo) {
        this.comboT -= dt;
        if (this.comboT <= 0) this.finishCombo();
      }
    }
    tickBoss(this, wdt * w.timeScale()); // world time: Time Stop and hit-stop hold it
    tickHazards(this, dt);
    // Fruit that fell off the bottom: a costly one (a real fruit you should have cut) is a strike once it had entered the screen.
    for (const b of w.bodies) {
      if (b.alive && b.gone()) {
        b.alive = false;
        if (b.costly && !b.rain && b.entered) this.strike(b);
      }
    }
    w.bodies = w.bodies.filter((b) => b.alive);
    // bomb fuses fizz
    // Burning fuse sparks on every bomb. The tip position is rotated with the bomb's angle.
    const bombs = w.bodies.filter((b) => b.bomb);
    if (w.powerScale) {
      for (const b of bombs) {
        const [tx, ty] = rotateVec(...this.app.art.bombTip, b.ang);
        w.particles.add(b.x + tx, b.y + ty, uniform(-90, 90), uniform(-160, -20), 0.25, 2, [255, 210, 120], "spark", 0.3);
        if (Math.random() < 0.5) w.particles.add(b.x + tx, b.y + ty, 0, 0, 0.12, 9, [255, 140, 40], "glow", 0);
      }
    }
    // The fuse hissing sound plays while any bomb is on screen.
    this.app.audio.fuse(bombs.length > 0 && this.state === "play");
    // Let the death/ending animation play for a moment, then show the results.
    if (this.state === "dying" && this.stateT > 1.7) this.end();
    else if (this.state === "ending" && this.stateT > 2.0) this.end();
  }

  // Run is over: save the best score and totals, grab a still of the screen for the results backdrop, and change scene.
  end() {
    this.state = "over";
    if (this.combo) this.finishCombo();
    saveFinishedRun(this);
    this.app.audio.quiet();
    const snap = this.app.snapshot();
    this.app.go(() => this.app.makeGameOver(this, snap));
  }

  // Extras drawn inside the world: red miss marks, the boss, hazards and the active power's visuals.
  drawWorldExtra(L, add) {
    for (const [x, age] of this.misses) { // a red brush mark where the fruit fell
      const k = Math.min(1.0, age / 0.12);
      const a = Math.min(1.0, (1.2 - age) / 0.4);
      const img = brushX(44, HANKO);
      const s = k < 1 ? 1.5 - 0.5 * k : 1;
      blit(L, img, x - (img.lw * s) / 2, H - 46 - (img.lh * s) / 2, a, s);
    }
    if (this.boss) for (const b of [this.boss.leaving, this.boss.active]) if (b && !b.done) b.draw(L, add);
    drawHazards(this, L, add);
    if (this.power) this.power.draw(L, add, this.app.ui);
  }

  /** Called once with the finished first paused frame: the world is frozen, so blur it (with its HUD) once. */
  onSnapshot(canvas) {
    this.frozen = frosted(canvas, [120, 114, 110]);
    this.wantSnapshot = false;
  }

  // The pause screen text and the Quit button outline.
  drawPause() {
    const f = this.app.art.fonts, ui = this.app.ui;
    label(ui, f, f.pause, "Paused", WASHI, [W / 2, H / 2 - 28], "center", 2);
    ui.fillStyle = "rgb(226,182,92)";
    ui.fillRect(W / 2 - 32, H / 2 + 24, 64, 1);
    label(ui, f, f.mono15, this.app.touch ? "Tap to resume" : "Click or Esc to resume", MUTED, [W / 2, H / 2 + 58]);
    ui.strokeStyle = "rgba(150,138,120,0.55)";
    ui.lineWidth = 1;
    ui.strokeRect(QUIT_RECT.x + 0.5, QUIT_RECT.y + 0.5, QUIT_RECT.w, QUIT_RECT.h);
    label(ui, f, f.mono15, this.app.touch ? "Quit to menu" : "Quit to menu  (Q)", WASHI, [W / 2, QUIT_RECT.y + QUIT_RECT.h / 2]);
  }

  // Paused: just show the blurred still. Otherwise draw the world, then the HUD, icons and stamps on top.
  draw() {
    if (this.paused && this.frozen) {
      this.drawPause();
      return;
    }
    this.w.draw((L, add) => this.drawWorldExtra(L, add));
    drawPlayHud(this, this.app.ui);
    drawIcons(this.app.ui, iconButtons(this), this.app.audio.muted, this.paused);
    this.w.drawOverlay();
    if (this.paused) this.wantSnapshot = true; // the App hands back this finished frame; it is blurred and held while paused
  }

  // Colour grades and glows laid over the finished picture.
  drawScreenFx(g) {
    drawGrades(this, g);
    drawKiGlow(this, g);
  }
}
