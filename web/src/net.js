// Loading files over a phone connection: a few at a time, and a dropped request is tried again instead of ending the game.

/** Run `task` with at most `n` running at once across all callers sharing this pool. */
export function pool(n) {
  let running = 0;
  const waiting = [];
  const next = () => {
    while (running < n && waiting.length) {
      const { task, resolve, reject } = waiting.shift();
      running++;
      task().then(resolve, reject).finally(() => { running--; next(); });
    }
  };
  return (task) => new Promise((resolve, reject) => { waiting.push({ task, resolve, reject }); next(); });
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Call `fn(attempt)` until it works, up to `tries` times, waiting a little longer after each failure. */
export async function retry(fn, tries = 4) {
  let err;
  for (let i = 0; i < tries; i++) {
    try { return await fn(i); } catch (e) { err = e; await sleep(400 * (i + 1)); }
  }
  throw err;
}

export const netPool = pool(6);
