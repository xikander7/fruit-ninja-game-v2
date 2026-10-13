# English-Only Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all visible Japanese writing from the web and desktop editions while preserving the stamped visual style and existing personal saves.

**Architecture:** Keep internal mode identifiers and the existing seal animation APIs. Replace visible vocabulary at configuration and call sites, teach both seal renderers to cut short Latin labels, and migrate the renamed blade during save parsing.

**Tech Stack:** JavaScript ES modules and Node test runner; Python, pygame-ce, and pytest.

**Spec:** `docs/superpowers/specs/2026-10-12-global-scores-english-only-design.md`

## Global Constraints

- All visible text and symbols use English words or Latin characters.
- Existing local score data and the `slash-and-splash-save` key remain intact.
- Internal mode identifiers remain `classic`, `arcade`, `zen`, and `path`.
- The red distressed stamp animation remains visually recognizable.
- Japanese glyph assets may remain in the repository but must not load or appear at runtime.

## Review Focus

- An old save selecting `Sakura` loads as `Petal Fan` without losing scores; Task 1 tests this in both editions.
- A missing or corrupt save still falls back safely; Task 1 reruns the existing corruption tests.
- Two-to-four-letter seal labels stay legible and centered at small and large sizes; Task 2 tests rendered bounds.
- No CJK literal remains in reachable UI configuration or scene code; Task 3 adds source and runtime scans.
- Renamed power terminology remains consistent in HUD, help text, and documentation; Task 3 asserts the visible vocabulary.

---

### Task 1: English vocabulary and save migration

**Files:**
- Modify: `web/src/config.js`
- Modify: `web/src/rules/save.js`
- Modify: `ninja/settings.py`
- Modify: `ninja/game.py`
- Test: `web/tests/rules.test.mjs`
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: Existing `parseSave(text)` and `load_save()` save-validation flows.
- Produces: `BLADES["Petal Fan"]`, `MODES.path.title === "Hero Path"`, and transparent migration from the old `Sakura` blade name.

- [ ] **Step 1: Add failing migration and vocabulary tests**

Assert that old saves retain all best scores while selecting `Petal Fan`, new saves accept `Petal Fan`, the former blade name is absent from visible config, and `path` displays `Hero Path`.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `node --test web/tests/rules.test.mjs` and `python -m pytest tests/test_modes.py -q`

Expected: FAIL on the old names and missing migration.

- [ ] **Step 3: Implement the configuration renames and migrations**

Update the two configs and both save parsers without changing save keys or internal mode identifiers.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the commands from Step 2.

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

Commit message: `Replace Japanese-derived UI names`

### Task 2: Latin stamp rendering

**Files:**
- Modify: `web/src/assets.js`
- Modify: `ninja/art.py`
- Test: `web/tests/visuals.test.mjs`
- Test: `tests/test_ui.py`

**Interfaces:**
- Consumes: `makeSeal(art, glyph, size)` and `make_seal(fonts, glyph, size, rng=None)`.
- Produces: The same interfaces, accepting one-to-four Latin characters and cutting centered English abbreviations from the ink square.

- [ ] **Step 1: Add failing Latin-label rendering tests**

Assert that `H`, `GO`, and `MENU` produce non-empty cutout pixels within the seal bounds in both renderers and remain deterministic.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `node --test web/tests/visuals.test.mjs` and `python -m pytest tests/test_ui.py -q`

Expected: FAIL because the web renderer only uses bundled CJK images and the desktop renderer is not sized for short words.

- [ ] **Step 3: Add Latin text cutouts**

Use the existing UI font families, bold condensed sizing, and dynamic fit-to-square logic; retain the existing CJK asset fallback only for compatibility with non-visible legacy calls during migration.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the commands from Step 2.

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

Commit message: `Render English labels in game seals`

### Task 3: Replace all visible Japanese runtime strings

**Files:**
- Modify: `web/src/title.js`
- Modify: `web/src/play.js`
- Modify: `web/src/gameover.js`
- Modify: `web/src/fever.js`
- Modify: `web/src/hazards.js`
- Modify: `web/src/hud.js`
- Modify: `web/src/powers.js`
- Modify: `web/src/boss.js`
- Modify: `web/src/rules/boss.js`
- Modify: `ninja/title.py`
- Modify: `ninja/game.py`
- Modify: `ninja/fever.py`
- Modify: `ninja/hazards.py`
- Modify: `ninja/hud.py`
- Modify: `ninja/powers.py`
- Modify: `ninja/boss.py`
- Test: `web/tests/english-ui.test.mjs`
- Test: `tests/test_english_ui.py`

**Interfaces:**
- Consumes: Latin-capable seal renderers from Task 2.
- Produces: English labels for title, modes, Ready, Time, Fever, powers, combo, boss, Retry, Menu, Game Over, and New Best UI paths.

- [ ] **Step 1: Add failing English-only source and config tests**

Scan reachable scene/config modules for the CJK Unicode ranges and assert the exact replacement labels used at each major UI state.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `node --test web/tests/english-ui.test.mjs` and `python -m pytest tests/test_english_ui.py -q`

Expected: FAIL and list the remaining CJK literals.

- [ ] **Step 3: Replace runtime symbols and terminology**

Use `H`, `C`, `A`, `Z`, `GO`, `ICE`, `RUSH`, `2X`, `COMBO`, `TIME`, `OVER`, `BEST`, `TRY`, `MENU`, `FLIP`, `BOSS`, `WIN`, `STOP`, `CLONE`, and `FIRE` as context-appropriate seals; replace visible `Ki` with `Power`.

- [ ] **Step 4: Run the new tests and verify GREEN**

Run the commands from Step 2.

Expected: both scans and vocabulary assertions pass.

- [ ] **Step 5: Commit**

Commit message: `Make the game interface English only`

### Task 4: Documentation and complete verification

**Files:**
- Modify: `README.md`
- Modify: `docs/screenshot.png` if the repository's screenshot workflow produces it

**Interfaces:**
- Consumes: Completed English-only web and desktop UI.
- Produces: Accurate user-facing documentation and screenshot.

- [ ] **Step 1: Update documentation and screenshot references**

Remove claims about kanji UI, document the English stamp style and renamed labels, and refresh the main screenshot if supported by the existing capture tool.

- [ ] **Step 2: Run complete verification**

Run: `python -m pytest -q`, `node --test web/tests/*.test.mjs`, the existing production build command from `README.md`, and `git diff --check`.

Expected: zero failures, successful build, and no whitespace errors.

- [ ] **Step 3: Commit**

Commit message: `Document the English-only interface`

