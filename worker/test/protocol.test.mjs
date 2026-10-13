import test from "node:test";
import assert from "node:assert/strict";
import * as protocol from "../src/protocol.js";

const SECRET = "test-only-secret-with-at-least-32-characters";
const NOW = 1_800_000_000_000;

test("signed run token round-trips trusted claims", async () => {
  const claims = { mode: "arcade", issuedAt: NOW, nonce: "0123456789abcdef0123456789abcdef" };
  const token = await protocol.createRunToken(claims, SECRET);
  assert.match(token, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
  assert.deepEqual(await protocol.verifyRunToken(token, SECRET, NOW + 60_000), claims);
});

test("altered, malformed, expired, future and unknown-mode tokens are rejected", async () => {
  const base = { mode: "classic", issuedAt: NOW, nonce: "abcdef0123456789abcdef0123456789" };
  const token = await protocol.createRunToken(base, SECRET);
  const changed = `${token.slice(0, -1)}${token.endsWith("A") ? "B" : "A"}`;
  assert.equal(await protocol.verifyRunToken(changed, SECRET, NOW + 1_000), null);
  assert.equal(await protocol.verifyRunToken("not-a-token", SECRET, NOW), null);
  assert.equal(await protocol.verifyRunToken(token, SECRET, NOW + 15 * 60_000 + 1), null);
  assert.equal(await protocol.verifyRunToken(token, SECRET, NOW - 30_001), null);
  await assert.rejects(protocol.createRunToken({ ...base, mode: "admin" }, SECRET), /invalid_claims/);
});

test("finish payload accepts a plausible run and returns normalized values", () => {
  const body = {
    token: "signed-token", score: 480, elapsed: 61,
    stats: { sliced: 18, best_combo: 6, bombs: 1, missed: 2 },
  };
  assert.deepEqual(protocol.validateFinishBody(body, { mode: "arcade" }), {
    token: "signed-token", mode: "arcade", score: 480, elapsed: 61,
    stats: { sliced: 18, best_combo: 6, bombs: 1, missed: 2 },
  });
});

test("finish payload rejects unsafe numbers, implausible scores, fields and durations", () => {
  const claims = { mode: "arcade" };
  const valid = { token: "x", score: 10, elapsed: 60, stats: { sliced: 1, best_combo: 1, bombs: 0, missed: 0 } };
  for (const score of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER]) {
    assert.throws(() => protocol.validateFinishBody({ ...valid, score }, claims), /invalid_score/);
  }
  assert.throws(() => protocol.validateFinishBody({ ...valid, score: 10_001 }, claims), /implausible_score/);
  assert.throws(() => protocol.validateFinishBody({ ...valid, elapsed: 4 }, claims), /invalid_duration/);
  assert.throws(() => protocol.validateFinishBody({ ...valid, admin: true }, claims), /unknown_field/);
  assert.throws(() => protocol.validateFinishBody({ ...valid, stats: { ...valid.stats, sliced: -1 } }, claims), /invalid_stats/);
  assert.throws(() => protocol.validateFinishBody({ ...valid, token: "x".repeat(3_000) }, claims), /body_too_large/);
});

test("CORS permits only production and explicit localhost origins", () => {
  assert.equal(protocol.corsHeaders("https://xikander7.github.io")["Access-Control-Allow-Origin"], "https://xikander7.github.io");
  assert.equal(protocol.corsHeaders("http://localhost:8000")["Access-Control-Allow-Origin"], "http://localhost:8000");
  assert.equal(protocol.corsHeaders("http://127.0.0.1:5173")["Access-Control-Allow-Origin"], "http://127.0.0.1:5173");
  assert.equal(protocol.corsHeaders("https://evil.example"), null);
  assert.equal(protocol.corsHeaders("https://xikander7.github.io.evil.example"), null);
});
