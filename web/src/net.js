// net.js - download helpers used by the asset loaders.
// Phones have shaky connections, so we limit how many files download at once and retry the ones that fail.
// Loading files over a phone connection: a few at a time, and a dropped request is tried again instead of ending the game.

// A tiny "queue" so only `n` downloads happen at the same time.
// Call pool(6) once and use the returned function: it takes a function that returns a Promise.
/** Run `task` with at most `n` running at once across all callers sharing this pool. */
export function pool(n) {
  // How many tasks are active right now, and the ones still waiting their turn.
  let running = 0;
  const waiting = [];
  // Starts waiting tasks while there is free room; called again every time a task finishes.
  const next = () => {
    while (running < n && waiting.length) {
      const { task, resolve, reject } = waiting.shift();
      running++;
      task().then(resolve, reject).finally(() => { running--; next(); });
    }
  };
  return (task) => new Promise((resolve, reject) => { waiting.push({ task, resolve, reject }); next(); });
}

// Wait for `ms` milliseconds (use with await).
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Each failure waits a bit longer (400ms, 800ms, ...) so a struggling network gets time to recover.
/** Call `fn(attempt)` until it works, up to `tries` times, waiting a little longer after each failure. */
export async function retry(fn, tries = 4) {
  let err;
  for (let i = 0; i < tries; i++) {
    try { return await fn(i); } catch (e) { err = e; await sleep(400 * (i + 1)); }
  }
  throw err;
}

// The one shared queue every loader uses: at most 6 downloads at once.
export const netPool = pool(6);
