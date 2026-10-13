import test from "node:test";
import assert from "node:assert/strict";
import worker, { handleRequest } from "../src/index.js";

const ORIGIN = "https://xikander7.github.io";
const SECRET = "test-only-secret-with-at-least-32-characters";
const SALT = "test-only-rate-salt-with-at-least-32-chars";
const NOW = 1_800_000_000_000;

class FakeDB {
  constructor() {
    this.scores = { classic: 0, arcade: 0, zen: 0, path: 0 };
    this.nonces = new Set();
    this.limits = new Map();
    this.calls = [];
  }

  prepare(sql) {
    const normalized = sql.replace(/\s+/gu, " ").trim();
    const db = this;
    return {
      bind(...values) {
        db.calls.push({ sql: normalized, values });
        return {
          async all() {
            if (normalized.startsWith("SELECT mode, score FROM global_scores")) {
              return { results: Object.entries(db.scores).map(([mode, score]) => ({ mode, score })) };
            }
            throw new Error(`unexpected all: ${normalized}`);
          },
          async first() {
            if (normalized.startsWith("INSERT INTO submission_limits")) {
              const [hash, now, resetBefore] = values;
              const old = db.limits.get(hash);
              const next = !old || old.window_start < resetBefore
                ? { window_start: now, submissions: 1 }
                : { ...old, submissions: old.submissions + 1 };
              db.limits.set(hash, next);
              return { submissions: next.submissions };
            }
            if (normalized.startsWith("SELECT score FROM global_scores")) {
              return { score: db.scores[values[0]] };
            }
            throw new Error(`unexpected first: ${normalized}`);
          },
          async run() {
            if (normalized.startsWith("INSERT OR IGNORE INTO used_nonces")) {
              const [nonce] = values;
              if (db.nonces.has(nonce)) return { meta: { changes: 0 } };
              db.nonces.add(nonce);
              return { meta: { changes: 1 } };
            }
            if (normalized.startsWith("UPDATE global_scores")) {
              const [score, _updatedAt, mode, threshold] = values;
              if (db.scores[mode] < threshold) { db.scores[mode] = score; return { meta: { changes: 1 } }; }
              return { meta: { changes: 0 } };
            }
            if (normalized.startsWith("DELETE FROM used_nonces")) return { meta: { changes: 0 } };
            throw new Error(`unexpected run: ${normalized}`);
          },
        };
      },
    };
  }
}

const env = (db = new FakeDB()) => ({ DB: db, RUN_TOKEN_SECRET: SECRET, RATE_LIMIT_SALT: SALT });
const req = (path, options = {}) => new Request(`https://scores.example${path}`, {
  ...options,
  headers: { Origin: ORIGIN, ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
});
const json = (path, body, headers) => req(path, { method: "POST", body: JSON.stringify(body), headers });

test("GET scores returns the four records with production CORS and cache headers", async () => {
  const db = new FakeDB(); db.scores.arcade = 99;
  const response = await handleRequest(req("/v1/scores"), env(db));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  assert.match(response.headers.get("Cache-Control"), /max-age=30/);
  assert.deepEqual(await response.json(), { scores: { classic: 0, arcade: 99, zen: 0, path: 0 } });
  assert.ok(db.calls[0].sql.includes("?0") === false);
});

test("a started run can raise but never lower a global score and cannot be replayed", async () => {
  const db = new FakeDB(); const bindings = env(db);
  const start = await handleRequest(json("/v1/runs/start", { mode: "arcade" }), bindings, NOW);
  assert.equal(start.status, 201);
  const { token } = await start.json();
  const result = { token, score: 480, elapsed: 61, stats: { sliced: 18, best_combo: 6, bombs: 1, missed: 2 } };
  const finish = await handleRequest(json("/v1/runs/finish", result, { "CF-Connecting-IP": "203.0.113.7" }), bindings, NOW + 61_000);
  assert.equal(finish.status, 200);
  assert.deepEqual(await finish.json(), { mode: "arcade", globalBest: 480, newRecord: true });
  assert.equal(db.scores.arcade, 480);
  assert.ok(db.calls.every(({ sql }) => !sql.includes("203.0.113.7")));
  assert.ok(db.calls.some(({ values }) => values.includes(480) && !values.some((v) => typeof v === "string" && v.includes("UPDATE"))));

  const replay = await handleRequest(json("/v1/runs/finish", result, { "CF-Connecting-IP": "203.0.113.7" }), bindings, NOW + 62_000);
  assert.equal(replay.status, 409);

  const secondStart = await handleRequest(json("/v1/runs/start", { mode: "arcade" }), bindings, NOW + 63_000);
  const secondToken = (await secondStart.json()).token;
  const lower = await handleRequest(json("/v1/runs/finish", { ...result, token: secondToken, score: 100 }, { "CF-Connecting-IP": "203.0.113.8" }), bindings, NOW + 124_000);
  assert.equal(lower.status, 200);
  assert.deepEqual(await lower.json(), { mode: "arcade", globalBest: 480, newRecord: false });
});

test("denied origins, bad content, oversized bodies and forged tokens return stable errors", async () => {
  const bindings = env();
  const denied = await handleRequest(json("/v1/runs/start", { mode: "zen" }, { Origin: "https://evil.example" }), bindings);
  assert.equal(denied.status, 403);
  assert.equal(denied.headers.get("Access-Control-Allow-Origin"), null);
  const wrongType = await handleRequest(req("/v1/runs/start", { method: "POST", body: "{}", headers: { "Content-Type": "text/plain" } }), bindings);
  assert.equal(wrongType.status, 415);
  const huge = await handleRequest(req("/v1/runs/start", { method: "POST", body: "x".repeat(3_000), headers: { "Content-Type": "application/json" } }), bindings);
  assert.equal(huge.status, 413);
  const forged = await handleRequest(json("/v1/runs/finish", {
    token: "forged.token", score: 1, elapsed: 60,
    stats: { sliced: 1, best_combo: 1, bombs: 0, missed: 0 },
  }, { "CF-Connecting-IP": "203.0.113.9" }), bindings);
  assert.equal(forged.status, 401);
  assert.deepEqual(await forged.json(), { error: "invalid_token" });
});

test("finish parsing errors stay inside the stable HTTP error boundary", async () => {
  const bindings = env();
  const wrongType = await handleRequest(req("/v1/runs/finish", {
    method: "POST", body: "{}", headers: { "Content-Type": "text/plain" },
  }), bindings);
  assert.equal(wrongType.status, 415);
  assert.deepEqual(await wrongType.json(), { error: "unsupported_media_type" });

  const invalidJson = await handleRequest(req("/v1/runs/finish", {
    method: "POST", body: "{", headers: { "Content-Type": "application/json" },
  }), bindings);
  assert.equal(invalidJson.status, 400);
  assert.deepEqual(await invalidJson.json(), { error: "invalid_json" });
});

test("finish rejects a claimed duration that has not actually elapsed", async () => {
  const bindings = env();
  const start = await handleRequest(json("/v1/runs/start", { mode: "arcade" }), bindings, NOW);
  const token = (await start.json()).token;
  const finish = await handleRequest(json("/v1/runs/finish", {
    token, score: 100_000, elapsed: 60,
    stats: { sliced: 1_000, best_combo: 10, bombs: 0, missed: 0 },
  }), bindings, NOW);
  assert.equal(finish.status, 400);
  assert.deepEqual(await finish.json(), { error: "invalid_duration" });
});

test("oversized streamed bodies are cancelled as soon as the byte limit is crossed", async () => {
  let pulls = 0; let cancelled = false;
  const body = new ReadableStream({
    pull(controller) {
      pulls += 1;
      if (pulls <= 100) controller.enqueue(new Uint8Array(1_024));
      else controller.close();
    },
    cancel() { cancelled = true; },
  });
  const request = new Request("https://scores.example/v1/runs/start", {
    method: "POST", body, duplex: "half",
    headers: { Origin: ORIGIN, "Content-Type": "application/json" },
  });
  const response = await handleRequest(request, env());
  assert.equal(response.status, 413);
  assert.equal(cancelled, true);
  assert.ok(pulls < 100);
});

test("submission rate limiting stores a salted hash and returns 429", async () => {
  const db = new FakeDB(); const bindings = env(db);
  let last;
  for (let i = 0; i < 13; i++) {
    const startedAt = NOW + i * 21_000;
    const start = await handleRequest(json("/v1/runs/start", { mode: "classic" }), bindings, startedAt);
    const token = (await start.json()).token;
    last = await handleRequest(json("/v1/runs/finish", {
      token, score: i, elapsed: 20,
      stats: { sliced: 1, best_combo: 1, bombs: 0, missed: 0 },
    }, { "CF-Connecting-IP": "198.51.100.22" }), bindings, startedAt + 20_000);
  }
  assert.equal(last.status, 429);
  assert.equal(db.limits.has("198.51.100.22"), false);
  assert.equal([...db.limits.keys()][0].length, 64);
});

test("OPTIONS, unknown routes and the default export use the same handler", async () => {
  const preflight = await worker.fetch(req("/v1/runs/finish", { method: "OPTIONS" }), env());
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  assert.equal((await handleRequest(req("/nope"), env())).status, 404);
});
