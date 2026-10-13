import test from "node:test";
import assert from "node:assert/strict";
import * as leaderboard from "../src/rules/leaderboard.js";

const SCORES = { classic: 12, arcade: 34, zen: 56, path: 78 };
const response = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

test("loads and validates all four global scores", async () => {
  const calls = [];
  const client = new leaderboard.LeaderboardClient({
    baseUrl: "https://scores.example", fetchFn: async (...args) => { calls.push(args); return response({ scores: SCORES }); },
  });
  assert.deepEqual(await client.loadScores(), SCORES);
  assert.equal(calls[0][0], "https://scores.example/v1/scores");
  assert.equal(calls[0][1].credentials, "omit");
});

test("starts and finishes a run without sending browser credentials", async () => {
  const calls = [];
  const fetchFn = async (url, options) => {
    calls.push([url, options]);
    return url.endsWith("/start")
      ? response({ token: "signed.token", expiresIn: 900 }, 201)
      : response({ mode: "zen", globalBest: 91, newRecord: true });
  };
  const client = new leaderboard.LeaderboardClient({ baseUrl: "https://scores.example/", fetchFn });
  const run = await client.startRun("zen");
  assert.deepEqual(run, { token: "signed.token" });
  const result = await client.finishRun(run, {
    mode: "zen", score: 91, elapsed: 90,
    stats: { sliced: 20, best_combo: 4, bombs: 0, missed: 1 },
  });
  assert.deepEqual(result, { mode: "zen", globalBest: 91, newRecord: true });
  assert.ok(calls.every(([, options]) => options.credentials === "omit"));
  assert.equal(JSON.parse(calls[1][1].body).token, "signed.token");
});

test("disabled, offline, HTTP error, bad JSON and malformed score data return null", async () => {
  assert.equal(await new leaderboard.LeaderboardClient({ baseUrl: "", fetchFn: () => assert.fail() }).loadScores(), null);
  assert.equal(await new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => { throw new Error("offline"); } }).loadScores(), null);
  assert.equal(await new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => response({}, 503) }).loadScores(), null);
  assert.equal(await new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => new Response("nope") }).loadScores(), null);
  for (const scores of [
    { classic: 1 },
    { ...SCORES, arcade: -1 },
    { ...SCORES, zen: 1.5 },
    { ...SCORES, path: Number.MAX_SAFE_INTEGER },
    { ...SCORES, bonus: 99 },
  ]) {
    const client = new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => response({ scores }) });
    assert.equal(await client.loadScores(), null);
  }
});

test("a timed-out request aborts and resolves to null", async () => {
  let aborted = false;
  const fetchFn = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => { aborted = true; reject(new DOMException("aborted", "AbortError")); });
  });
  const client = new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn, timeoutMs: 5 });
  assert.equal(await client.loadScores(), null);
  assert.equal(aborted, true);
});

test("malformed run and finish responses return null", async () => {
  const badStart = new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => response({ token: "" }, 201) });
  assert.equal(await badStart.startRun("classic"), null);
  assert.equal(await badStart.startRun("admin"), null);
  const badFinish = new leaderboard.LeaderboardClient({ baseUrl: "x", fetchFn: async () => response({ mode: "classic", globalBest: -1, newRecord: "yes" }) });
  assert.equal(await badFinish.finishRun({ token: "x.y" }, {
    mode: "classic", score: 1, elapsed: 5,
    stats: { sliced: 1, best_combo: 1, bombs: 0, missed: 0 },
  }), null);
});
