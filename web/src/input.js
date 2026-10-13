// input.js - the doorway for everything the player does.
// The browser tells us about mouse, touch and keyboard actions; this file turns them into a simple list of
// events ("move", "down", "up", "key"...) that the game reads once per frame. It does no game logic itself.
//
// Input: mouse, touch and keyboard turned into the events the App understands. Positions are in stage coordinates.
// Moving the pointer is the blade: a mouse slices as it hovers, a finger as it drags.
import { VIEW } from "./config.js";

// The keys the game uses. We stop the browser from reacting to them (no page scrolling on Space, etc.).
const GAME_KEYS = new Set([" ", "arrowleft", "arrowright", "arrowup", "arrowdown", "escape"]);

// Hooks all the browser listeners up to the canvas. `app` is the App from app.js (we push into app.events);
// `canvas` is the <canvas> element the game is drawn on.
export function attachInput(app, canvas) {
  // Converts a browser pointer position (screen pixels) into game "stage" coordinates.
  // The stage is the game's own fixed-size world; the canvas is scaled to fit any screen, so we have to undo that.
  const toStage = (e) => {
    const [dw, dh] = app.disp;
    let lx, ly; // the point in the canvas's own (unturned) pixels, from its centre
    // On phones held upright the whole canvas is rotated sideways with CSS, so the screen's x and y swap roles.
    if (app.turned) { // the canvas is turned 90 degrees clockwise: undo it
      lx = e.clientY - window.innerHeight / 2;
      ly = -(e.clientX - window.innerWidth / 2);
    } else {
      const r = canvas.getBoundingClientRect();
      lx = e.clientX - (r.left + r.width / 2);
      ly = e.clientY - (r.top + r.height / 2);
    }
    return [((lx + dw / 2) / dw) * VIEW.w - VIEW.ox, ((ly + dh / 2) / dh) * VIEW.h - VIEW.oy];
  };
  // Queue an event for the next frame. The cap of 400 stops a runaway pile-up if the game is paused or lagging.
  const push = (ev) => { if (app.events.length < 400) app.events.push(ev); };
  // "pen" (stylus) behaves like a finger here: it only slices while pressed down.
  const isTouch = (e) => e.pointerType === "touch" || e.pointerType === "pen";

  // Pointer events cover mouse, touch and pen in one API. Pressing down starts a touch-slice and registers a click/tap.
  canvas.addEventListener("pointerdown", (e) => {
    if (!e.isPrimary) return; // one finger is the blade
    e.preventDefault();
    // Browsers keep sound locked until the player does something. The first touch or click unlocks it.
    app.audio.unlock();
    const [x, y] = toStage(e);
    if (isTouch(e)) {
      app.pointerActive = true;
      // Pointer capture keeps move events coming even if the finger slides off the canvas.
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      push({ type: "move", x, y, reset: true }); // a new touch never cuts across the screen from the last one
    }
    push({ type: "down", x, y, button: e.button });
  });

  // Moving the pointer is the blade. A mouse slices while hovering; touch only while the finger is down.
  canvas.addEventListener("pointermove", (e) => {
    if (!e.isPrimary) return;
    if (isTouch(e) && !app.pointerActive) return;
    // Browsers merge several tiny moves into one event to save work. "Coalesced" events give them back so a fast
    // swipe leaves a smooth, unbroken trail instead of straight jumps.
    const list = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const c of list.length ? list : [e]) {
      const [x, y] = toStage(c);
      push({ type: "move", x, y });
    }
    if (!isTouch(e)) app.pointerActive = true;
  });

  // Finger lifted (or the system cancelled the touch, e.g. a call came in): the blade stops.
  const lift = (e) => {
    if (!e.isPrimary) return;
    if (isTouch(e)) app.pointerActive = false;
    push({ type: "up" });
  };
  canvas.addEventListener("pointerup", lift);
  canvas.addEventListener("pointercancel", lift);
  canvas.addEventListener("contextmenu", (e) => e.preventDefault()); // right click uses the last power
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); push({ type: "wheel", dy: e.deltaY }); }, { passive: false });

  // Keyboard. Ctrl/Cmd/Alt combos are left to the browser (copy, reload, etc.).
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (GAME_KEYS.has(key)) e.preventDefault();
    // Holding a key makes the browser repeat it; we only want the first press.
    if (e.repeat) return;
    app.audio.unlock();
    push({ type: "key", key });
  });

  // Losing focus or hiding the tab sends "blur" so the game can pause instead of running unseen.
  window.addEventListener("blur", () => push({ type: "blur" }));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) push({ type: "blur" });
    app.audio.pauseContext(document.hidden);
  });
}
