# Global Scores and English-Only Interface Design

## Goal

Make Honey's Slash & Splash production-ready for repeat visitors by adding shared global best scores to the hosted web game and removing all visible Japanese writing. The static game remains hosted on GitHub Pages. A small Cloudflare Worker backed by D1 stores the global records.

Success means:

- Every visitor sees the same global best score for Classic, Arcade, Zen, and Hero Path.
- A completed run can raise its mode's global best score.
- Personal best scores still persist in the current browser.
- A network or leaderboard outage never prevents the game from loading or finishing.
- All visible labels, badges, stamps, power controls, and status messages use English text and Latin characters.
- The deployed GitHub Pages build and leaderboard API are covered by automated tests and production smoke checks.

## Scope

This release adds one global record per mode. It does not add player accounts, names, profiles, or a top-ten leaderboard. Avoiding identity data keeps the experience instant and the backend small enough for the free tier.

The desktop Python edition receives the same English-only presentation changes, but global scoring is web-only because the production URL serves the browser edition.

## Architecture

### Web game

The browser continues to load and save personal progress with `localStorage`. A new leaderboard client performs two best-effort operations:

1. Fetch the four global records after the menu starts.
2. Submit a completed run after the local save succeeds.

The menu displays both values without delaying startup: `Personal 42 · Global 310`. Until the network request completes, the global value is shown as unavailable rather than as zero. When a submission returns a new record, the in-memory global score is updated immediately.

Requests have short timeouts and failures are swallowed after updating a small connection-status field. Local saving always happens first and never depends on a remote response.

### Score service

A Cloudflare Worker exposes a versioned JSON API:

- `GET /v1/scores` returns all four records.
- `POST /v1/runs/start` returns a short-lived, signed run token containing the mode and start time.
- `POST /v1/runs/finish` accepts the token plus the final score and run statistics, validates them, and atomically raises the relevant record when appropriate.
- `OPTIONS` supports browser CORS preflight.

Only the GitHub Pages origin is allowed by CORS in production. Localhost origins are allowed during development. Responses use explicit JSON content types, no-store caching for mutations, and a short public cache for score reads.

### D1 data

The database contains a `global_scores` table with exactly one row per mode:

- `mode` — primary key restricted to the four known mode identifiers.
- `score` — non-negative integer.
- `updated_at` — server timestamp.

A small `submission_limits` table records hashed client identifiers and recent submission windows for rate limiting. Raw IP addresses are never stored.

Updates use prepared statements and a conditional upsert, so simultaneous submissions cannot lower or corrupt a record.

## Abuse Resistance

A browser game cannot make scores impossible to forge without running the full game simulation on a trusted server. For this casual game, the service uses practical protections without adding accounts:

- A run must begin through the API and finish with an unexpired signed token.
- Mode-specific minimum and maximum run durations are enforced.
- Scores and run statistics must be finite non-negative integers and remain within generous mode-specific limits.
- Score-to-slice ratios are sanity checked while still allowing combos, Fever, bosses, and bonuses.
- Submissions are rate limited by a salted hash derived inside the Worker.
- Request bodies have a small maximum size and unknown fields or modes are rejected.
- Secrets used for token signing and hashing remain Worker secrets and are never shipped to GitHub Pages.

These controls prevent accidental corruption and simple scripted spam while keeping normal play frictionless.

## English-Only Interface

All user-visible Japanese characters are replaced with compact English or Latin-letter seal marks. The distressed red stamp animation remains part of the visual identity.

Key replacements include:

| Existing | Replacement |
| --- | --- |
| Title seal | `H` |
| Classic mode seal | `C` |
| Arcade mode seal | `A` |
| Zen mode seal | `Z` |
| Ninja Path | `Hero Path`, seal `H` |
| Sakura blade | `Petal Fan` |
| Ki meter | `Power` |
| Ready/status seals | Short English labels such as `GO`, `TIME`, `BEST`, `OVER` |
| Retry/Menu seals | `TRY`, `MENU` |
| Power and boss seals | English abbreviations matching their captions |

The seal renderer is extended to cut short Latin text from the red square. Existing Japanese glyph image files may remain as unused assets, but the web loader will no longer load them and no visible runtime string will reference them.

Non-ASCII punctuation such as the curly apostrophe in the game name, multiplication sign, arrows, and typographic separators may remain because they are symbols, not Japanese writing. Tests target CJK character ranges rather than banning all Unicode.

## Compatibility and Migration

The local save key remains unchanged so existing personal scores survive the release. Internal mode identifiers also remain unchanged (`classic`, `arcade`, `zen`, `path`); only display labels change. Existing saves using the blade name `Sakura` are migrated to `Petal Fan` during parsing.

The leaderboard client treats malformed API responses as unavailable and validates every returned mode and score before displaying it.

## Testing

Implementation follows test-driven development.

- Save migration tests prove existing `Sakura` selections become `Petal Fan` without resetting scores.
- UI/config tests scan visible runtime strings for CJK characters and verify the English replacements.
- Leaderboard client tests cover successful fetch, malformed responses, timeouts, offline startup, submissions, and server-record updates.
- Worker tests cover routing, CORS, validation, expired or altered tokens, rate limiting, conditional record updates, and concurrent-safe SQL behavior.
- Existing JavaScript and Python suites must remain green.
- The web production build must succeed.
- Production smoke checks fetch the exact GitHub Pages URL and the deployed API, then confirm a harmless non-record test submission cannot lower a score.

## Deployment

The repository gains a `worker/` project containing Worker source, D1 migrations, tests, and Wrangler configuration. Deployment requires a one-time Cloudflare authorization. The D1 database, signing secret, and Worker are created through Wrangler. The deployed Worker URL is then added to the web configuration, and the verified build is pushed to `main` and `gh-pages` using the repository's established deployment process.

If Cloudflare authorization is unavailable, all code and tests can still be completed, but global scores cannot become live until the account is authorized. No private credentials are committed to Git.

