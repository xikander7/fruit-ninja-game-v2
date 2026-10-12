// Sound, on the Web Audio API (ninja/audio.py). Why this replaces the pygame mixer in the browser: Web Audio mixes
// on its own audio thread, so a slow frame can never starve it (that was the crackle), and everything passes
// through one limiter, so a storm of splats, a bomb and the Fever drums add up without clipping.
import { uniform, choice } from "./util.js";

// Per-name level. Files are peak-normalised to about -1 dBFS, so these bring them into balance; music sits under the effects.
const LEVEL = {
  swoosh: 0.9, splat: 0.9, throw: 0.35, explode: 0.8, fuse: 0.45, miss: 0.75, combo: 0.7, power: 0.7, stamp: 0.6, life: 0.55,
  gong: 0.75, music: 0.4, timestop: 0.7, clones: 0.7, dragonfire: 0.7, boss_hit: 0.8, boss_roar: 0.8, fever: 0.45, shuriken: 0.7, tick: 0.6,
};
const ALIASES = { stamp: "combo", life: "power" }; // names that reuse another group's files
const VOICES = { splat: 5, swoosh: 3, throw: 3, tick: 1, boss_hit: 3, shuriken: 3 }; // simultaneous copies of one sound (default 6)
const MAX_VOICES = 16;
const MUSIC_GAIN = 0.55; // the music channel's volume in the Python game
const FEVER_DUCK = 0.7; // the music steps back while the Fever drums are on, so the two layers don't muddy each other

export class Audio {
  constructor() {
    this.ok = false;
    this.muted = false;
    this.ctx = null;
    this.buffers = {}; // name -> [AudioBuffer]
    this.voices = new Map(); // name -> number playing now
    this.total = 0;
    this.music = null; // {src, gain}
    this.fuseV = null;
    this.layer = null; this.layerName = null; // the held layer (the Fever drums)
    this.manifest = null;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC({ latencyHint: "interactive" });
      this.build();
      this.ok = true;
    } catch (e) {
      this.ok = false; // no audio: the game still runs silently
    }
  }

  build() {
    const c = this.ctx;
    this.master = c.createGain();
    this.master.gain.value = 0.85;
    this.limiter = c.createDynamicsCompressor(); // a gentle limiter: the sum of many sounds never reaches clipping
    this.limiter.threshold.value = -9;
    this.limiter.knee.value = 8;
    this.limiter.ratio.value = 10;
    this.limiter.attack.value = 0.004;
    this.limiter.release.value = 0.18;
    this.master.connect(this.limiter);
    this.softClip = c.createWaveShaper(); // the last guard: clean below 0.8, a smooth shoulder above, never past 1.0
    const curve = new Float32Array(4097);
    for (let i = 0; i < curve.length; i++) {
      const x = (i / 2048) - 1, a = Math.abs(x);
      curve[i] = a < 0.8 ? x : Math.sign(x) * (0.8 + 0.2 * Math.tanh((a - 0.8) / 0.2));
    }
    this.softClip.curve = curve;
    this.limiter.connect(this.softClip);
    this.softClip.connect(c.destination);
    this.sfxBus = c.createGain();
    this.musicBus = c.createGain();
    this.sfxBus.connect(this.master);
    this.musicBus.connect(this.master);
  }

  /** Must run inside a user gesture (a tap or key press): browsers keep audio suspended until then. */
  unlock() {
    if (!this.ok) return;
    if (this.ctx.state !== "running") {
      this.ctx.resume().then(() => { if (this.wantMusic) this.startMusic(); }).catch(() => {});
    }
    if (!this.unlocked) { // iOS wants a sound started inside the gesture
      this.unlocked = true;
      const s = this.ctx.createBufferSource();
      s.buffer = this.ctx.createBuffer(1, 1, 22050);
      s.connect(this.ctx.destination);
      s.start(0);
    }
  }

  pauseContext(hidden) {
    if (!this.ok) return;
    if (hidden) this.ctx.suspend().catch(() => {});
    else if (this.unlocked) this.ctx.resume().catch(() => {});
  }

  async fetchBuffer(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return this.ctx.decodeAudioData(await res.arrayBuffer());
  }

  /** Load the sound effects (small), then the long loops. `onProgress(done, total)` drives the loading bar. */
  async load(base, onProgress = () => {}) {
    if (!this.ok) return;
    try {
      const man = await (await fetch(`${base}audio/manifest.json`)).json();
      this.manifest = man;
      const groups = Object.entries(man.groups);
      const jobs = [];
      let done = 0;
      const total = groups.reduce((n, [, files]) => n + files.length, 0);
      for (const [name, files] of groups) {
        if (name === "music" || name === "fever" || name === "fuse") continue; // long loops: after the menu is up
        for (const f of files) {
          jobs.push(this.fetchBuffer(`${base}audio/${f}`).then((b) => { (this.buffers[name] ??= []).push(b); })
            .catch(() => {}).finally(() => onProgress(++done, total)));
        }
      }
      await Promise.all(jobs);
      for (const [alias, src] of Object.entries(ALIASES)) if (this.buffers[src]) this.buffers[alias] = this.buffers[src];
      this.buffers.tick = [this.makeTick()];
      this.base = base;
    } catch (e) {
      this.ok = false;
    }
  }

  /** The long loops (music, Fever drums, bomb fuse), loaded in the background once the menu is showing. */
  async loadLoops() {
    if (!this.ok || !this.manifest) return;
    for (const name of ["music", "fever", "fuse"]) {
      for (const f of this.manifest.groups[name] || []) {
        try {
          (this.buffers[name] ??= []).push(await this.fetchBuffer(`${this.base}audio/${f}`));
        } catch (e) { /* that loop stays silent */ }
      }
      if (name === "music" && this.wantMusic) this.startMusic();
    }
  }

  /** The countdown tick, made in code (there is no recording of it). */
  makeTick() {
    const sr = this.ctx.sampleRate, n = Math.trunc(0.08 * sr);
    const b = this.ctx.createBuffer(1, n, sr);
    const d = b.getChannelData(0);
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      d[i] = (Math.sin(2 * Math.PI * 1150 * t) + 0.5 * Math.sin(2 * Math.PI * 1730 * t)) * Math.exp(-i / (0.012 * sr)) * 0.5;
    }
    return b;
  }

  /** Play one random take of `name` once, at LEVEL x vol. Skipped when too many copies are already sounding. */
  play(name, vol = 1.0) {
    if (!this.ok || this.muted) return;
    const bufs = this.buffers[name];
    if (!bufs || !bufs.length || this.ctx.state !== "running") return;
    const n = this.voices.get(name) || 0;
    if (n >= (VOICES[name] ?? 6) || this.total >= MAX_VOICES) return;
    const src = this.ctx.createBufferSource();
    src.buffer = choice(bufs);
    const g = this.ctx.createGain();
    g.gain.value = Math.min(1, (LEVEL[name] ?? 0.7) * vol * uniform(0.94, 1.06));
    src.connect(g);
    g.connect(this.sfxBus);
    this.voices.set(name, n + 1);
    this.total += 1;
    src.onended = () => {
      this.voices.set(name, Math.max(0, (this.voices.get(name) || 1) - 1));
      this.total = Math.max(0, this.total - 1);
      g.disconnect();
    };
    src.start();
  }

  /** A looping voice with a fade in; returns {src, gain}. */
  startLoop(name, level, fadeIn, bus) {
    const bufs = this.buffers[name];
    if (!bufs || !bufs.length) return null;
    const src = this.ctx.createBufferSource();
    src.buffer = choice(bufs);
    src.loop = true;
    const gain = this.ctx.createGain();
    const t = this.ctx.currentTime;
    gain.gain.setValueAtTime(fadeIn > 0 ? 0 : level, t);
    if (fadeIn > 0) gain.gain.linearRampToValueAtTime(level, t + fadeIn);
    src.connect(gain);
    gain.connect(bus);
    src.start();
    return { src, gain, level };
  }

  stopLoop(v, fadeOut) {
    if (!v) return;
    const t = this.ctx.currentTime;
    try {
      v.gain.gain.cancelScheduledValues(t);
      v.gain.gain.setValueAtTime(v.gain.gain.value, t);
      v.gain.gain.linearRampToValueAtTime(0, t + fadeOut);
      v.src.stop(t + fadeOut + 0.02);
    } catch (e) { /* already stopped */ }
    v.src.onended = () => v.gain.disconnect();
  }

  fuse(on) {
    if (!this.ok) return;
    if (on && !this.muted && !this.fuseV && this.ctx.state === "running") {
      this.fuseV = this.startLoop("fuse", LEVEL.fuse * 0.35, 0.03, this.sfxBus);
    } else if (!on && this.fuseV) {
      this.stopLoop(this.fuseV, 0.05);
      this.fuseV = null;
    }
  }

  /** Hold the Fever drums on their own voice while `on`, and let the music step back under them. */
  loop(name, on) {
    if (!this.ok) return;
    if (on && !this.muted && this.layerName !== name && this.ctx.state === "running") {
      this.layerName = name;
      this.layer = this.startLoop(name, LEVEL[name], 0.25, this.sfxBus);
      this.duckMusic(FEVER_DUCK);
    } else if (!on && this.layerName === name) {
      this.layerName = null;
      this.stopLoop(this.layer, 0.4);
      this.layer = null;
      this.duckMusic(1.0);
    }
  }

  duckMusic(k) {
    if (!this.music) return;
    const g = this.music.gain.gain, t = this.ctx.currentTime;
    g.cancelScheduledValues(t);
    g.setValueAtTime(g.value, t);
    g.linearRampToValueAtTime(this.music.level * k, t + 0.4);
  }

  /** Stop the held layers (fuse and the Fever drums): pause, game over, leaving a run. */
  quiet() {
    this.fuse(false);
    if (this.ok && this.layerName) this.loop(this.layerName, false);
  }

  /** Exactly one music voice, ever: asking again while it plays does nothing. */
  startMusic() {
    this.wantMusic = true;
    if (!this.ok || this.muted || this.music || this.ctx.state !== "running") return;
    this.music = this.startLoop("music", LEVEL.music * MUSIC_GAIN, 1.5, this.musicBus);
  }

  stopAll() {
    this.stopLoop(this.music, 0.1); this.music = null;
    this.stopLoop(this.fuseV, 0.05); this.fuseV = null;
    this.stopLoop(this.layer, 0.1); this.layer = null; this.layerName = null;
  }

  toggleMute() {
    this.muted = !this.muted;
    if (!this.ok) return;
    if (this.muted) this.stopAll();
    else this.startMusic();
  }

  /** What is sounding right now (used by the audio check). */
  stats() {
    return { state: this.ctx ? this.ctx.state : "none", voices: this.total, music: Boolean(this.music), fever: Boolean(this.layer), fuse: Boolean(this.fuseV) };
  }
}
