# Tone-Builder Anti-Hallucination Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development to implement task-by-task. Each `SKILL.md` edit goes through superpowers:writing-skills; each code task through superpowers:test-driven-development. Ship via the repo's bump + annotated-tag flow (CLAUDE.md).

**Goal:** Make the tone-builder hallucination-resistant by moving every MECHANICAL step (catalog discovery, model-id/param validation, FX/pin policy) out of the agent's prose and into DETERMINISTIC tools — so the agent only makes judgment calls (research, cited) and can never type an unverified model id, param path, or value.

**Architecture:** The agent researches the rig in natural language (cited) and emits a small **research JSON**. Three new deterministic scripts in `skills/openrig-tone-analyzer/scripts/` turn that into a validated base chain: `resolve_gear.py` (research → catalog-backed base-chain skeleton, PINNING exact captures), `validate_chain.py` (every id/param checked against the manifests; hard-fail on anything unknown), `lint_chain.py` (FX/pin/gate policy as code). `build_preset.py` gains validate+lint as a pre-render gate. The `SKILL.md` shrinks to judgment + the tool pipeline, deleting the ~1000 lines of prohibitions the tools now enforce.

**Tech Stack:** Python 3.12 + PyYAML + the existing `_common`/`eq_match` libs and the analyzer venv. Offline; no MCP required. Tests use fixture manifests/catalog (no Rust binary, no real WAVs).

## Global Constraints
- Portable (LAW 1): no machine-tied paths; catalog/plugins root, render-bin, DI, dyld-lib all come from CLI/env. Scripts resolve the venv/sibling scripts relative to `__file__`.
- English only in all committed files. Ship via `git commit` + `git push origin main` + annotated `vX.Y.Z` tag + verify remote; bump `.claude-plugin/plugin.json` by semver in the same commit.
- Tests injected/offline: no `openrig-render`, no large WAVs in unit tests; use fixture manifests.
- Do NOT touch `_common.py`/`analyze.py` fingerprinting (5 pre-existing `test_determinism` failures stay).

## The design decision you must confirm — native-block param validation
`openrig-render` exposes NO offline schema/param dump; native-block params (eq_eight_band_parametric, compressor_*, gate_*, delay_*, reverb_*, native cabs `american_2x12`/`brit_4x12`, native drives `native_ibanez_ts9`…) live only in the OpenRig app's Rust source. NAM/IR PLUGIN params live in the catalog manifests (validatable offline). So:
- **Option A (recommended, ships now):** the validator HARD-fails on (1) any model id not in the catalog (plugin manifests + a committed native-model-id list) and (2) any PLUGIN (NAM/IR) param path/value not in its manifest. Native-block param paths/values are **warn-only** (no offline schema). Catches the worst classes we saw (wrong amp id; the `generic_ir` raw-wav cab — now a manifest-validated `type: cab` plugin). Residual: an invented native knob (e.g. a comp threshold) is flagged, not blocked.
- **Option B (most correct, follow-up):** add a `--dump-schema` JSON to `openrig-render` (OpenRig APP repo, Rust) → commit the dump into this plugin → the validator HARD-fails on native params too. Touches a different repo; larger.
This plan implements **Option A**; Task 6 notes Option B as a follow-up. **Confirm A, or ask for B up front.**

---

## File structure
- `skills/openrig-tone-analyzer/scripts/catalog.py` — shared catalog index (read manifests under a plugins root → `{model_id: {type, brand, display_name, params, captures}}` + native-model-id set). One responsibility: turn the on-disk catalog into a queryable index.
- `skills/openrig-tone-analyzer/scripts/resolve_gear.py` — research JSON → base-chain skeleton (pin exact captures, candidate stand-ins, FIXED-FX placeholders).
- `skills/openrig-tone-analyzer/scripts/validate_chain.py` — base chain → hard-fail on unknown id / unknown plugin param / out-of-range value; warn on native params.
- `skills/openrig-tone-analyzer/scripts/lint_chain.py` — base chain → policy findings (zero time-FX, ungated high-gain NAM, amp-not-pinned-when-exact-exists, limiter/volume present).
- `skills/openrig-tone-analyzer/scripts/build_preset.py` — MODIFY: run validate+lint as a pre-render gate (hard-fail blocks render; lint warnings surface in the report).
- `skills/openrig-tone-analyzer/scripts/native_models.yaml` — committed list of native (non-plugin) model ids + their type, so the validator knows them offline.
- `skills/openrig-tone-builder/SKILL.md` — MODIFY: shrink to research(judgment) → resolve_gear → fill FX params → validate/lint → build_preset → relay; cut the prohibitions the tools now enforce.
- Tests: `tests/test_catalog.py`, `tests/test_resolve_gear.py`, `tests/test_validate_chain.py`, `tests/test_lint_chain.py`, plus build_preset gate tests; fixtures under `tests/fixtures/catalog/`.

---

## Task 1: `catalog.py` — queryable catalog index
**Files:** Create `scripts/catalog.py`; Test `tests/test_catalog.py`; fixtures `tests/fixtures/catalog/<plugin>/manifest.yaml` (≥1 NAM amp incl. an artist-signature one, 1 IR cab, 1 gain pedal) + `scripts/native_models.yaml`.
**Produces:** `load_catalog(plugins_root, native_models_path) -> Catalog`; `Catalog.find(query) -> [Match]` where a Match has `model_id, type, brand, display_name, score`; `Catalog.params(model_id) -> dict|None` (manifest params for plugins, None for native); `Catalog.is_known(model_id) -> bool`.
**Tests (write first):** index reads manifest `id/type/brand/display_name/parameters/captures`; `find("dumble john mayer")` ranks the artist-signature capture #1; `find` is case/accent-insensitive; native ids from `native_models.yaml` are `is_known` but have `params=None`; an unknown id is not `is_known`.

## Task 2: `resolve_gear.py` — research JSON → base-chain skeleton (PIN exact, SEARCH stand-ins)
**Files:** Create `scripts/resolve_gear.py`; Test `tests/test_resolve_gear.py`.
**Consumes:** `catalog.py`. **Produces:** `resolve(research: dict, catalog) -> dict` returning a base-chain YAML dict (flat `blocks:` in signal order) + a `provenance`/`unresolved` report.
**Research JSON shape (the agent's judgment, cited):** `{song, artist, role, amp:{name,brand,signature?,sources[]}, drives:[{name,brand,sources[]}], cab:{name?}, fx:[{type,model_or_name,params,provenance,sources[]}]}`.
**Logic:** for the amp — `catalog.find(amp.name + brand + signature)`; if an EXACT/signature match exists → **PIN** it (`{type: amp, model: <id>}`, optionally gain-axis candidate variants of that ONE model); else emit `candidates:` of the top documented stand-ins. Same for cab (→ `type: cab` plugin, never `generic_ir`) and each drive. The EQ TUNE slot is added flat. Each `fx` becomes a FIXED block with its researched params + `provenance`. Anything the catalog can't resolve goes to `unresolved` (the agent must fix research, not guess an id).
**Tests:** an artist-signature amp in `research` → PINNED (single fixed model, no alternative models); a non-captured amp → `candidates:` stand-ins; a cab → `type: cab` plugin id (never `generic_ir`); an unresolved amp → listed in `unresolved`, NOT a guessed id; FIXED fx preserved with provenance; signal order preserved.

## Task 3: `validate_chain.py` — hard-fail on unknown id / param (Option A)
**Files:** Create `scripts/validate_chain.py`; Test `tests/test_validate_chain.py`.
**Consumes:** `catalog.py`. **Produces:** `validate(chain: dict, catalog) -> {ok: bool, errors: [...], warnings: [...]}`; CLI exits non-zero on any error.
**Logic:** every block `model` must be `catalog.is_known` (else ERROR). For a PLUGIN block, every `params` key must be a manifest param name and each value within the manifest's declared axis values (else ERROR). For a NATIVE block, params are WARN-only (no offline schema). `limiter_brickwall`/`volume` present → ERROR (engine strips them; authoring is a bug).
**Tests:** unknown model id → error; a NAM/IR plugin param not in the manifest → error (this is the `air=26`-class on a plugin); a value outside the axis → error; a native-block unknown param → warning, not error; a `limiter_brickwall` → error; a clean chain → ok.

## Task 4: `lint_chain.py` — FX/pin policy as code
**Files:** Create `scripts/lint_chain.py`; Test `tests/test_lint_chain.py`.
**Produces:** `lint(chain, catalog) -> [Finding]` (`level: block|warn`, `code`, `message`).
**Checks:** zero reverb AND zero delay → `warn` (research-miss unless cited dry); a high-gain NAM amp/drive present AND no `dynamics` gate → `warn`; an amp authored as multi-MODEL `candidates:` when the catalog HAS an exact/signature capture for the researched name → `block` (must pin); `limiter_brickwall`/`volume` → `block`.
**Tests:** chain with no reverb/delay → the zero-time-FX warn; high-gain NAM + no gate → the gate warn; multi-model amp candidates while an exact capture exists → block; pinned amp + gate + a delay → no findings.

## Task 5: wire validate + lint into `build_preset.py` as a pre-render gate
**Files:** Modify `scripts/build_preset.py`; extend `tests/test_build_preset.py`.
**Logic:** before the gear search, run `validate_chain` on the resolved chain — any ERROR aborts with a clear message (no render). Run `lint_chain` — `block` findings abort; `warn` findings flow into the report (`report["lint"]`). Keep all existing behavior (pin core, `--cab-model`, ±6 EQ, no limiter/volume, provenance, `assert_no_dropped_blocks`).
**Tests:** a chain with an unknown id aborts before render; a `block` lint finding aborts; a `warn` appears in the report; a clean chain renders as today (all current tests green).

## Task 6: shrink + rewrite `SKILL.md` to the tool pipeline
**Files:** Modify `skills/openrig-tone-builder/SKILL.md` (via superpowers:writing-skills).
**Logic:** the FORM becomes: fingerprint → **research the rig in natural language, cited** (judgment) → emit the research JSON → `resolve_gear.py` (it finds the catalog ids; you NEVER type one) → fill FIXED-FX params from research → `validate_chain.py` + `lint_chain.py` (fix every error/`block`; you NEVER ship an invented id/param) → `build_preset.py` → relay the report → persist. Keep the judgment-only content: the no-suppositions HARD RULES, guitar-vs-guitar, degraded-ref honesty, self_floor ceiling, no-ears/user's-ear, Rule A (pin) framed as "resolve_gear pins it", Rule B (FX params sourced/unverified), the eval dir, new-slot-never-overwrite, ONE tone. DELETE the prohibitions the tools now enforce (manual id/param hand-authoring rules, most of the Red-flags/Rationalizations about guessing ids/params/cabs — the validator blocks them). Target: well under 700 lines.
**Tests (writing-skills):** a fresh subagent on the Gravity case follows resolve_gear → validate → build_preset and does NOT type a model id from memory; baseline (no skill) hallucinates an amp id.

## Task 7: verify + ship
- Run the full analyzer suite green (except the 5 pre-existing determinism pins); paste output.
- Independent coherence re-audit of the shrunk SKILL (pin/regulate/tool-pipeline/no-contradiction).
- Baseline-test: a fresh subagent builds Gravity via the new pipeline; confirm it PINS `nam_dumble_ods_john_mayer_a2` (not a Fender) and authors no invented param.
- Bump `.claude-plugin/plugin.json` (minor), commit, push, annotated tag, verify remote.
- (Follow-up, not this ship) Option B: `openrig-render --dump-schema` → hard native-param validation.

## Self-review notes
- Spec coverage: every hallucination class we observed maps to a task — wrong amp id → Task 2 (pin) + Task 3 (id validation); invented cab/native params → Task 3 (plugin params hard, native warn) + the `--cab-model` plugin cab already shipped; missing FX/gate → Task 4; agent typing ids from memory → Task 2 (resolve_gear) + Task 6 (skill never types ids).
- Open risk: native-param invention (comp/delay knobs) is WARN-only under Option A — flagged for the user; Option B closes it.
