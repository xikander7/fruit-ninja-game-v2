# Global Scores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add resilient global best scores for all four modes without exposing secrets or collecting player identity data.

**Architecture:** A Cloudflare Worker validates signed run tokens and conditionally updates four D1 records. The GitHub Pages client fetches and submits scores asynchronously while continuing to use localStorage for personal scores and remaining fully playable offline.

**Tech Stack:** Cloudflare Workers, D1 SQLite, Wrangler, JavaScript ES modules, Node test runner or Cloudflare's Workers test pool, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-12-global-scores-english-only-design.md`

## Global Constraints

- No private key, token-signing secret, database credential, raw IP address, or personal identifier is committed or shipped to the browser.
- One global record exists for each internal mode: `classic`, `arcade`, `zen`, and `path`.
- Local score persistence runs before remote submission and never depends on the network.
- The game loads and completes normally if the API is slow, malformed, unavailable, or rate limited.
- Production CORS allows only `https://xikander7.github.io`; development allows explicit localhost origins.
- Requests and responses are size-bounded and schema-validated.

## Review Focus

- A forged, expired, wrong-mode, or replayed run token must not write a score; Task 1 tests every case.
- `NaN`, infinity, decimals, negatives, huge integers, unknown fields, and oversized bodies must be rejected; Task 1 tests every class.
- Simultaneous lower and higher submissions must never lower the record; Task 2 tests conditional D1 updates.
- API timeout, bad JSON, partial score objects, and HTTP errors must not block startup or erase local scores; Task 3 tests each condition.
- Repeated submissions from one source must receive a controlled 429 without storing a raw address; Task 2 tests rate limits and stored hashes.

---

### Task 1: Pure Worker protocol and validation

**Files:**
- Create: `worker/package.json`
- Create: `worker/src/protocol.js`
- Create: `worker/test/protocol.test.mjs`

**Interfaces:**
- Consumes: Web `Request`, Web Crypto, and injected current time/secret.
- Produces: `createRunToken({ mode, issuedAt, nonce }, secret)`, `verifyRunToken(token, secret, now)`, `validateFinishBody(body, claims)`, and `corsHeaders(origin)`.

- [ ] **Step 1: Add failing protocol and threat-model tests**

Cover valid round trips; altered signatures; expired, future, replay-ready, and wrong-mode claims; all numeric edge cases; unknown modes and fields; permitted and denied origins; and maximum JSON size.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `node --test worker/test/protocol.test.mjs`

Expected: FAIL because the protocol module does not exist.

- [ ] **Step 3: Implement the pure protocol functions**

Use HMAC-SHA-256 through Web Crypto, base64url encoding, constant-time-equivalent verification via digest comparison, a 15-minute maximum token lifetime, strict property allowlists, and integer bounds tailored to each mode.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2.

Expected: all protocol tests pass.

- [ ] **Step 5: Commit**

Commit message: `Add secure score submission protocol`

### Task 2: D1-backed Worker API

**Files:**
- Create: `worker/src/index.js`
- Create: `worker/migrations/0001_global_scores.sql`
- Create: `worker/wrangler.jsonc`
- Create: `worker/test/api.test.mjs`
- Modify: `worker/package.json`

**Interfaces:**
- Consumes: Task 1 protocol functions and Worker bindings `DB`, `RUN_TOKEN_SECRET`, and `RATE_LIMIT_SALT`.
- Produces: `fetch(request, env, ctx)` routes for `GET /v1/scores`, `POST /v1/runs/start`, `POST /v1/runs/finish`, and `OPTIONS`.

- [ ] **Step 1: Add failing Worker API tests**

Assert exact JSON schemas and statuses; origin enforcement; content type and body size checks; prepared/parameterized D1 access; atomic max-only updates; one-time nonce consumption; hashed-source rate limits; and no secret or stack leakage in errors.

- [ ] **Step 2: Run Worker tests and verify RED**

Run: the `worker/package.json` test script using Cloudflare's Workers test pool.

Expected: FAIL because the Worker and migration do not exist.

- [ ] **Step 3: Implement schema and Worker routes**

Seed all four modes at zero, store consumed nonces until expiry, store only salted source hashes, use prepared statements, and return stable public error codes.

- [ ] **Step 4: Run Worker tests and verify GREEN**

Run the Worker test script.

Expected: all Worker API tests pass.

- [ ] **Step 5: Commit**

Commit message: `Add D1 global score service`

### Task 3: Resilient browser leaderboard client

**Files:**
- Create: `web/src/rules/leaderboard.js`
- Create: `web/tests/leaderboard.test.mjs`
- Modify: `web/src/config.js`

**Interfaces:**
- Consumes: `fetch`, `AbortController`, a configured public API base URL, mode identifiers, and completed run data.
- Produces: `LeaderboardClient` with `loadScores()`, `startRun(mode)`, and `finishRun(run, result)` methods returning validated data or `null` without throwing expected network failures.

- [ ] **Step 1: Add failing client tests**

Cover valid scores and tokens; timeout; rejected fetch; non-2xx response; invalid JSON; partial/unknown modes; negative/decimal scores; and a returned record after submission.

- [ ] **Step 2: Run client tests and verify RED**

Run: `node --test web/tests/leaderboard.test.mjs`

Expected: FAIL because the client module does not exist.

- [ ] **Step 3: Implement the minimal client**

Use an injected fetch function, three-second timeout, strict response validation, no credentials, and a disabled state when the API URL is empty.

- [ ] **Step 4: Run client tests and verify GREEN**

Run the command from Step 2.

Expected: all client tests pass.

- [ ] **Step 5: Commit**

Commit message: `Add resilient global score client`

### Task 4: Integrate global scores with game flow

**Files:**
- Modify: `web/src/app.js`
- Modify: `web/src/menu.js`
- Modify: `web/src/play.js`
- Modify: `web/src/gameover.js`
- Test: `web/tests/game-flow.test.mjs`
- Test: `web/tests/rules.test.mjs`

**Interfaces:**
- Consumes: `LeaderboardClient` from Task 3 and existing local `app.save.best` values.
- Produces: `app.globalBest`, non-blocking menu refresh, per-run server token state, and best-effort finished-run submission after `app.persist()`.

- [ ] **Step 1: Add failing integration tests**

Assert that startup does not await global scores, the menu distinguishes Personal and Global values, starting a mode requests but does not require a token, local persistence precedes submission, a remote record updates memory, and every failure path leaves play usable.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `node --test web/tests/game-flow.test.mjs web/tests/rules.test.mjs`

Expected: FAIL because global score state is absent.

- [ ] **Step 3: Integrate the client**

Keep scene transitions synchronous, refresh menu labels after successful fetch, capture elapsed time and existing run statistics, and never retry mutations automatically.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run the command from Step 2.

Expected: all integration tests pass.

- [ ] **Step 5: Commit**

Commit message: `Show and submit global best scores`

### Task 5: Secure deployment and production verification

**Files:**
- Modify: `worker/wrangler.jsonc` with the created D1 database identifier only
- Modify: `web/src/config.js` with the public Worker URL
- Modify: `README.md`
- Modify: `.gitignore` if Wrangler creates local state not already ignored

**Interfaces:**
- Consumes: Verified Worker, D1 migration, browser client, Cloudflare authorization, and the established GitHub Pages deployment process.
- Produces: Live score API and live GitHub Pages game using it.

- [ ] **Step 1: Verify no secrets or personal data are tracked**

Run repository scans for secret variable values, Wrangler state, credentials, raw IP persistence, and accidental environment files; inspect `git diff --cached` before every deployment commit.

- [ ] **Step 2: Authorize Cloudflare and create production resources**

Use Wrangler's browser login, create the D1 database, apply remote migrations, generate high-entropy `RUN_TOKEN_SECRET` and `RATE_LIMIT_SALT` directly into Worker secrets, and deploy the Worker. Never print or save secret values in repository files or chat output.

- [ ] **Step 3: Configure the public URL and run complete verification**

Run all Python tests, all web tests, all Worker tests, the web production build, `git diff --check`, and a secret scan.

Expected: zero test failures, successful build, no tracked secrets, and a clean diff check.

- [ ] **Step 4: Run production smoke checks**

Verify CORS from the GitHub Pages origin, fetch the four records, verify denied origins cannot mutate, verify an invalid token cannot mutate, and confirm the exact GitHub Pages URL contains the English-only release and global-score API URL.

- [ ] **Step 5: Commit, push, and deploy GitHub Pages**

Commit message: `Deploy secure global scores`

- [ ] **Step 6: Re-run live checks after CDN propagation**

Confirm both the plain production URL and a cache-busted URL load the same release, local personal scores survive reload, and global records are visible without blocking startup.

