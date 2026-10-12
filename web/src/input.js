// Input: mouse, touch and keyboard turned into the events the App understands. Positions are in stage coordinates.
// Moving the pointer is the blade: a mouse slices as it hovers, a finger as it drags.
import { VIEW } from "./config.js";

const GAME_KEYS = new Set([" ", "arrowleft", "arrowright", "arrowup", "arrowdown", "escape"]);

export function attachInput(app, canvas) {
  const toStage = (e) => {
    const r = canvas.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * VIEW.w - VIEW.ox, ((e.clientY - r.top) / r.height) * VIEW.h - VIEW.oy];
  };
  const push = (ev) => { if (app.events.length < 400) app.events.push(ev); };
  const isTouch = (e) => e.pointerType === "touch" || e.pointerType === "pen";

  canvas.addEventListener("pointerdown", (e) => {
    if (!e.isPrimary) return; // one finger is the blade
    e.preventDefault();
    app.audio.unlock();
    const [x, y] = toStage(e);
    if (isTouch(e)) {
      app.pointerActive = true;
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      push({ type: "move", x, y, reset: true }); // a new touch never cuts across the screen from the last one
    }
    push({ type: "down", x, y, button: e.button });
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!e.isPrimary) return;
    if (isTouch(e) && !app.pointerActive) return;
    const list = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const c of list.length ? list : [e]) {
      const [x, y] = toStage(c);
      push({ type: "move", x, y });
    }
    if (!isTouch(e)) app.pointerActive = true;
  });

  const lift = (e) => {
    if (!e.isPrimary) return;
    if (isTouch(e)) app.pointerActive = false;
    push({ type: "up" });
  };
  canvas.addEventListener("pointerup", lift);
  canvas.addEventListener("pointercancel", lift);
  canvas.addEventListener("contextmenu", (e) => e.preventDefault()); // right click uses the last power
  canvas.addEventListener("wheel", (e) => { e.preventDefault(); push({ type: "wheel", dy: e.deltaY }); }, { passive: false });

  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (GAME_KEYS.has(key)) e.preventDefault();
    if (e.repeat) return;
    app.audio.unlock();
    push({ type: "key", key });
  });

  window.addEventListener("blur", () => push({ type: "blur" }));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) push({ type: "blur" });
    app.audio.pauseContext(document.hidden);
  });
}
