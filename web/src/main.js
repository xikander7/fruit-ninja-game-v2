// Boot: load the art and sounds with a progress bar, wait for the first tap (browsers keep audio locked until one),
// then start the game and run the frame loop.
import { Art } from "./assets.js";
import { Audio } from "./audio.js";
import { App, enterFullscreen } from "./app.js";
import { attachInput } from "./input.js";

const BASE = "assets/";
const $ = (id) => document.getElementById(id);
const touch = window.matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0;

function setProgress(f) {
  $("bar").style.width = `${Math.round(Math.min(1, f) * 100)}%`;
}

let linesTimer = 0;
const LINES = ["Sharpening the blade…", "Picking the ripest fruit…", "Squeezing the juice…", "Warming up the dojo…"];

async function boot() {
  const art = new Art();
  const audio = new Audio();
  let line = 0;
  linesTimer = setInterval(() => { $("status").textContent = LINES[++line % LINES.length]; }, 1800);
  let a = 0, b = 0;
  const update = () => setProgress(0.7 * a + 0.3 * b);
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
  const start = async (fullscreen) => {
    $("buttons").hidden = true;
    audio.unlock();
    if (fullscreen || touch) await enterFullscreen();
    const app = new App({ canvas: $("game"), art, audio, storage: window.localStorage, touch });
    attachInput(app, $("game"));
    let pending = 0;
    const refit = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(() => app.resize()); };
    window.addEventListener("resize", refit);
    window.addEventListener("orientationchange", refit);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", refit);
    document.addEventListener("fullscreenchange", refit);
    window.__app = app; // for the tests and the console
    $("boot").classList.add("gone");
    let last = performance.now();
    const frame = (t) => {
      requestAnimationFrame(frame);
      const dt = (t - last) / 1000;
      last = t;
      if (dt > 0) app.frameStep(dt);
    };
    requestAnimationFrame(frame);
    audio.loadLoops(); // the long music loops arrive while the menu is already playable
  };
  $("play").onclick = () => start(false);
  $("fs").onclick = () => start(true);
}

boot().catch((err) => {
  clearInterval(linesTimer);
  $("status").textContent = "Could not load the game (" + err.message + "). Check your connection and try again.";
  $("track").hidden = true;
  $("retry").hidden = false;
  $("retry").onclick = () => location.reload();
  console.error(err);
});
