export const MODES = Object.freeze(["classic", "arcade", "zen", "path"]);
export const MAX_BODY_BYTES = 2048;
export const TOKEN_LIFETIME_MS = 15 * 60_000;

const encoder = new TextEncoder();
const MODE_LIMITS = Object.freeze({
  classic: { minSeconds: 1, maxSeconds: 900, maxScore: 1_000_000 },
  arcade: { minSeconds: 45, maxSeconds: 900, maxScore: 100_000 },
  zen: { minSeconds: 75, maxSeconds: 900, maxScore: 100_000 },
  path: { minSeconds: 1, maxSeconds: 900, maxScore: 1_000_000 },
});

const fail = (code) => { throw new Error(code); };
const exactKeys = (value, allowed, code = "unknown_field") => {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(code);
};
const safeInt = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;

function base64url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function unbase64url(text) {
  if (typeof text !== "string" || !/^[A-Za-z0-9_-]+$/u.test(text)) throw new Error("bad_base64");
  const padded = text.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - text.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function hmacKey(secret, usages) {
  if (typeof secret !== "string" || secret.length < 32) fail("invalid_secret");
  return crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, usages);
}

function validClaims(claims) {
  exactKeys(claims, ["mode", "issuedAt", "nonce"], "invalid_claims");
  return MODES.includes(claims.mode)
    && safeInt(claims.issuedAt, 0, Number.MAX_SAFE_INTEGER)
    && typeof claims.nonce === "string"
    && /^[a-f0-9]{32}$/u.test(claims.nonce);
}

export async function createRunToken(claims, secret) {
  if (!validClaims(claims)) fail("invalid_claims");
  const payload = base64url(encoder.encode(JSON.stringify({
    mode: claims.mode, issuedAt: claims.issuedAt, nonce: claims.nonce,
  })));
  const key = await hmacKey(secret, ["sign"]);
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(payload)));
  return `${payload}.${base64url(signature)}`;
}

export async function verifyRunToken(token, secret, now = Date.now()) {
  try {
    if (typeof token !== "string" || token.length > 1024) return null;
    const parts = token.split(".");
    if (parts.length !== 2) return null;
    const [payload, encodedSignature] = parts;
    const key = await hmacKey(secret, ["verify"]);
    const ok = await crypto.subtle.verify("HMAC", key, unbase64url(encodedSignature), encoder.encode(payload));
    if (!ok) return null;
    const claims = JSON.parse(new TextDecoder().decode(unbase64url(payload)));
    if (!validClaims(claims)) return null;
    if (!safeInt(now, 0, Number.MAX_SAFE_INTEGER)) return null;
    const age = now - claims.issuedAt;
    if (age < -30_000 || age > TOKEN_LIFETIME_MS) return null;
    return claims;
  } catch (_error) {
    return null;
  }
}

export function validateFinishBody(body, claims) {
  let encoded;
  try { encoded = JSON.stringify(body); } catch (_error) { fail("body_too_large"); }
  if (encoder.encode(encoded ?? "").byteLength > MAX_BODY_BYTES) fail("body_too_large");
  exactKeys(body, ["token", "score", "elapsed", "stats"]);
  if (!claims || !MODES.includes(claims.mode)) fail("invalid_mode");
  if (typeof body.token !== "string" || !body.token || body.token.length > 1024) fail("invalid_token");
  const limits = MODE_LIMITS[claims.mode];
  if (!safeInt(body.score, 0, limits.maxScore)) fail("invalid_score");
  if (!safeInt(body.elapsed, limits.minSeconds, limits.maxSeconds)) fail("invalid_duration");
  exactKeys(body.stats, ["sliced", "best_combo", "bombs", "missed"], "invalid_stats");
  const statLimits = { sliced: 10_000, best_combo: 1_000, bombs: 1_000, missed: 1_000 };
  for (const [key, max] of Object.entries(statLimits)) {
    if (!safeInt(body.stats[key], 0, max)) fail("invalid_stats");
  }
  if (body.stats.best_combo > body.stats.sliced || body.score > body.stats.sliced * 100 + 5_000) {
    fail("implausible_score");
  }
  return {
    token: body.token,
    mode: claims.mode,
    score: body.score,
    elapsed: body.elapsed,
    stats: { ...body.stats },
  };
}

export function corsHeaders(origin) {
  const allowed = origin === "https://xikander7.github.io"
    || /^http:\/\/(localhost|127\.0\.0\.1)(:\d{1,5})?$/u.test(origin || "");
  if (!allowed) return null;
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}
