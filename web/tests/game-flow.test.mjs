import test from "node:test";
import assert from "node:assert/strict";
import { App } from "../src/app.js";
import { scoreLabel } from "../src/menu.js";
import { beginRemoteRun, saveFinishedRun } from "../src/play.js";

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test("global score loading is non-blocking and refreshes the active menu", async () => {
  const pending = deferred(); let refreshes = 0;
  const app = {
    leaderboard: { loadScores: () => pending.promise }, globalBest: null,
    scene: { refreshScores: () => { refreshes += 1; } },
  };
  const loading = App.prototype.refreshGlobalScores.call(app);
  assert.equal(app.globalBest, null);
  assert.equal(refreshes, 0);
  pending.resolve({ classic: 10, arcade: 20, zen: 30, path: 40 });
  await loading;
  assert.deepEqual(app.globalBest, { classic: 10, arcade: 20, zen: 30, path: 40 });
  assert.equal(refreshes, 1);
});

test("menu distinguishes personal and unavailable or loaded global records", () => {
  assert.equal(scoreLabel(12, null, "classic"), "Personal 12 · Global —");
  assert.equal(scoreLabel(12, { classic: 91 }, "classic"), "Personal 12 · Global 91");
});

test("starting a run requests a token without delaying play and tolerates failure", async () => {
  const pending = deferred();
  const tokenPromise = beginRemoteRun({ startRun: () => pending.promise }, "zen");
  assert.ok(tokenPromise instanceof Promise);
  pending.resolve({ token: "signed.token" });
  assert.deepEqual(await tokenPromise, { token: "signed.token" });
  assert.equal(await beginRemoteRun({ startRun: async () => { throw new Error("offline"); } }, "zen"), null);
});

test("finished run saves locally before best-effort remote submission", () => {
  const events = [];
  const app = {
    save: { best: { classic: 2 }, total_sliced: 5 },
    persist: () => events.push("persist"),
    submitGlobalRun: () => { events.push("submit"); return Promise.resolve(null); },
  };
  const play = { app, mode: "classic", score: 9, stats: { sliced: 3 } };
  saveFinishedRun(play);
  assert.deepEqual(events, ["persist", "submit"]);
  assert.equal(app.save.best.classic, 9);
  assert.equal(app.save.total_sliced, 8);
});

test("successful submission updates global memory while every failure remains harmless", async () => {
  const app = {
    leaderboard: { finishRun: async () => ({ mode: "arcade", globalBest: 480, newRecord: true }) },
    globalBest: { classic: 1, arcade: 2, zen: 3, path: 4 },
    scene: { refreshScores() {} },
  };
  const play = {
    remoteRunPromise: Promise.resolve({ token: "signed.token" }), mode: "arcade", score: 480, elapsed: 61,
    stats: { sliced: 18, best_combo: 6, bombs: 1, missed: 2 },
  };
  assert.deepEqual(await App.prototype.submitGlobalRun.call(app, play), { mode: "arcade", globalBest: 480, newRecord: true });
  assert.equal(app.globalBest.arcade, 480);

  app.leaderboard.finishRun = async () => { throw new Error("offline"); };
  await assert.doesNotReject(() => App.prototype.submitGlobalRun.call(app, play));
  assert.equal(app.globalBest.arcade, 480);
  assert.equal(await App.prototype.submitGlobalRun.call(app, { ...play, remoteRunPromise: Promise.resolve(null) }), null);
});
