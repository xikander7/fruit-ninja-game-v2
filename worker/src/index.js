import {
  MAX_BODY_BYTES, MODES, TOKEN_LIFETIME_MS, corsHeaders, createRunToken,
  validateFinishBody, verifyRunToken,
} from "./protocol.js";

const RATE_WINDOW_MS = 10 * 60_000;
const RATE_LIMIT = 12;
const encoder = new TextEncoder();

function json(body, status, cors, cache = "no-store") {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": cache, ...(cors || {}) },
  });
}

function error(code, status, cors) { return json({ error: code }, status, cors); }

async function readJson(request) {
  if (!(request.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json")) {
    throw Object.assign(new Error("unsupported_media_type"), { status: 415 });
  }
  const announced = Number(request.headers.get("Content-Length") || 0);
  if (announced > MAX_BODY_BYTES) throw Object.assign(new Error("body_too_large"), { status: 413 });
  const text = await request.text();
  if (encoder.encode(text).byteLength > MAX_BODY_BYTES) throw Object.assign(new Error("body_too_large"), { status: 413 });
  try { return JSON.parse(text); }
  catch (_error) { throw Object.assign(new Error("invalid_json"), { status: 400 }); }
}

function exactObject(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).every((key) => keys.includes(key))
    && keys.every((key) => Object.hasOwn(value, key));
}

function nonce() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sourceHash(request, salt) {
  if (typeof salt !== "string" || salt.length < 32) throw new Error("configuration_error");
  const source = request.headers.get("CF-Connecting-IP") || "local-or-unknown";
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(`${salt}:${source}`)));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function scores(db) {
  const result = await db.prepare("SELECT mode, score FROM global_scores ORDER BY mode").bind().all();
  const output = Object.fromEntries(MODES.map((mode) => [mode, 0]));
  for (const row of result.results || []) {
    if (MODES.includes(row.mode) && Number.isSafeInteger(row.score) && row.score >= 0) output[row.mode] = row.score;
  }
  return output;
}

async function takeRateSlot(db, hash, now) {
  const row = await db.prepare(`
    INSERT INTO submission_limits (source_hash, window_start, submissions) VALUES (?1, ?2, 1)
    ON CONFLICT(source_hash) DO UPDATE SET
      window_start = CASE WHEN window_start < ?3 THEN ?2 ELSE window_start END,
      submissions = CASE WHEN window_start < ?3 THEN 1 ELSE submissions + 1 END
    RETURNING submissions
  `).bind(hash, now, now - RATE_WINDOW_MS).first();
  return row && row.submissions <= RATE_LIMIT;
}

async function consumeNonce(db, value, expiresAt, now) {
  await db.prepare("DELETE FROM used_nonces WHERE expires_at < ?1").bind(now).run();
  const result = await db.prepare("INSERT OR IGNORE INTO used_nonces (nonce, expires_at) VALUES (?1, ?2)")
    .bind(value, expiresAt).run();
  return result.meta && result.meta.changes === 1;
}

async function finishRun(request, env, cors, now) {
  const body = await readJson(request);
  const token = body && body.token;
  const claims = await verifyRunToken(token, env.RUN_TOKEN_SECRET, now);
  if (!claims) return error("invalid_token", 401, cors);
  let run;
  try { run = validateFinishBody(body, claims); }
  catch (validation) {
    const status = validation.message === "body_too_large" ? 413 : 400;
    return error(validation.message, status, cors);
  }
  const hash = await sourceHash(request, env.RATE_LIMIT_SALT);
  if (!await takeRateSlot(env.DB, hash, now)) return error("rate_limited", 429, cors);
  if (!await consumeNonce(env.DB, claims.nonce, claims.issuedAt + TOKEN_LIFETIME_MS, now)) {
    return error("run_already_submitted", 409, cors);
  }
  const update = await env.DB.prepare(`
    UPDATE global_scores SET score = ?1, updated_at = ?2 WHERE mode = ?3 AND score < ?4
  `).bind(run.score, now, run.mode, run.score).run();
  const row = await env.DB.prepare("SELECT score FROM global_scores WHERE mode = ?1").bind(run.mode).first();
  return json({ mode: run.mode, globalBest: row.score, newRecord: Boolean(update.meta && update.meta.changes) }, 200, cors);
}

export async function handleRequest(request, env, now = Date.now()) {
  const origin = request.headers.get("Origin");
  const cors = corsHeaders(origin);
  if (!cors) return error("origin_not_allowed", 403, null);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  const { pathname } = new URL(request.url);
  try {
    if (request.method === "GET" && pathname === "/v1/scores") {
      return json({ scores: await scores(env.DB) }, 200, cors, "public, max-age=30");
    }
    if (request.method === "POST" && pathname === "/v1/runs/start") {
      const body = await readJson(request);
      if (!exactObject(body, ["mode"]) || !MODES.includes(body.mode)) return error("invalid_mode", 400, cors);
      const claims = { mode: body.mode, issuedAt: now, nonce: nonce() };
      const token = await createRunToken(claims, env.RUN_TOKEN_SECRET);
      return json({ token, expiresIn: TOKEN_LIFETIME_MS / 1000 }, 201, cors);
    }
    if (request.method === "POST" && pathname === "/v1/runs/finish") return finishRun(request, env, cors, now);
    return error("not_found", 404, cors);
  } catch (caught) {
    if (caught && Number.isInteger(caught.status)) return error(caught.message, caught.status, cors);
    return error("internal_error", 500, cors);
  }
}

export default { fetch: (request, env) => handleRequest(request, env) };
