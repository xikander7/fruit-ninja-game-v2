// main.js - the page's entry point (index.html loads this file).
// It shows the loading screen, then builds the App and starts the frame loop.
// Boot: load the art and sounds with a progress bar, wait for the first tap (browsers keep audio locked until one),
// then start the game and run the frame loop.
import { Art } from "./assets.js";
import { Audio } from "./audio.js";
import { App, enterFullscreen } from "./app.js";
import { attachInput } from "./input.js";

// Folder the images and sounds are fetched from.
const BASE = "assets/";
// Shortcut: $("play") means document.getElementById("play").
const $ = (id) => document.getElementById(id);
// True on phones/tablets: they get a "Tap to play" button and go fullscreen automatically.
const touch = window.matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0;

// Fills the loading bar. `f` goes from 0 (empty) to 1 (full).
function setProgress(f) {
  $("bar").style.width = `${Math.round(Math.min(1, f) * 100)}%`;
}

// Funny status messages rotate while loading, so waiting feels less dull.
let linesTimer = 0;
const LINES = ["Sharpening the blade…", "Picking the ripest fruit…", "Squeezing the juice…", "Warming up the dojo…"];

// Loads everything, waits for the first tap, then starts the game.
async function boot() {
  const art = new Art();
  const audio = new Audio();
  let line = 0;
  linesTimer = setInterval(() => { $("status").textContent = LINES[++line % LINES.length]; }, 1800);
  let a = 0, b = 0;
  const update = () => setProgress(0.7 * a + 0.3 * b);
  // Art and audio download at the same time. Art counts as 70% of the bar, audio as 30%.
  await Promise.all([
    art.load(BASE, (d, t) => { a = d / t; update(); }),
    audio.load(BASE, (d, t) => { b = d / t; update(); }),
  ]);
  clearInterval(linesTimer);
  setProgress(1);
  $("status").textContent = "";
  $("buttons").hidden = false;
  $("fs").hidden = touch; // phones go fullscreen with the first tap; computers choose
  $("play").textContent = touch ? "Tap to play" : "Play";
  // Runs when the player taps Play. Starting from a tap is required: browsers refuse sound and
  // fullscreen unless they come from a real user action.
  const start = async (fullscreen) => {
    $("buttons").hidden = true;
    audio.unlock();
    if (fullscreen || touch) await enterFullscreen();
    const app = new App({ canvas: $("game"), art, audio, storage: window.localStorage, touch });
    attachInput(app, $("game"));
    // The window can fire many resize events in a row; we only refit once per animation frame.
    let pending = 0;
    const refit = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(() => app.resize()); };
    window.addEventListener("resize", refit);
    window.addEventListener("orientationchange", refit);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", refit);
    document.addEventListener("fullscreenchange", refit);
    // Exposed so automated tests and the browser console can poke at the game.
    window.__app = app; // for the tests and the console
    $("boot").classList.add("gone");
    let last = performance.now();
    // The game loop. requestAnimationFrame calls this before every screen refresh (about 60 times a second).
    // `dt` is the time since the last frame in seconds, so movement stays the same speed on fast and slow screens.
    const frame = (t) => {
      requestAnimationFrame(frame);
      const dt = (t - last) / 1000;
      last = t;
      if (dt > 0) app.frameStep(dt);
    };
    requestAnimationFrame(frame);
    // Music loops are big, so they load after the game is already usable.
    audio.loadLoops(); // the long music loops arrive while the menu is already playable
  };
  $("play").onclick = () => start(false);
  $("fs").onclick = () => start(true);
}

// If loading fails (usually a bad connection), show a message and a retry button instead of a blank page.
boot().catch((err) => {
  clearInterval(linesTimer);
  $("status").textContent = "Could not load the game (" + err.message + "). Check your connection and try again.";
  $("track").hidden = true;
  $("retry").hidden = false;
  $("retry").onclick = () => location.reload();
  console.error(err);
});
