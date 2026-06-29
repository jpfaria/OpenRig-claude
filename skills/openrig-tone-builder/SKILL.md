---
name: openrig-tone-builder
description: "Use when the user asks for a tone, timbre, or preset for a specific song or artist (\"timbre da Duality\", \"preset do Slipknot\", \"tom da [música]\", \"recreate the [song] sound\", \"build a [artist] preset\"). Researches the original signal chain, maps it to OpenRig blocks, and saves it as a NAMED PRESET in the chain's bank — adding a NEW slot via `apply_rig_nav Preset(-1)`, never overwriting existing presets. ALWAYS asks the user once up front whether to commit via the live MCP rig or as a YAML file only."
---

# OpenRig Tone Builder

## ⛔ THE PROCESS — deterministic, in THIS exact order. No shortcuts.

The user's standing law for this skill: **fingerprint → research the
artist's REAL gear → author the chain with that SAME gear → let the
ENGINE regulate by the number.** That is the whole job. You do ONLY this:

1. **Fingerprint the stems** the user sent (Step 0). Confirm they are the
   **isolated instrument being built** (the guitar — or acoustic). A
   separated stem can still be the WRONG instrument: a piano-driven song
   (e.g. Clocks) separated badly yields a piano-dominated stem, and matching
   a guitar to it is hopeless. If unsure, ask which instrument the stem is.
2. **Research the artist's actual rig for THIS song** (Step 1) — amp(s),
   pedals, cab(s); for acoustic, which guitar. **`tonedb.co` is source #1 —
   hit it FIRST**, then the rest of the ladder. Cite sources. Never assert
   gear from memory (the gear HARD RULE).
3. **Author the base-chain YAML with the SAME researched gear**, mapped to
   OpenRig models (Steps 2–3). You write the real rig as a flat `blocks:`
   list — SEARCH slots carry research-derived `candidates:`, FIXED FX carry
   researched params, ONE `eq_eight_band_parametric` is the TUNE slot. You
   do **NOT** patch or EQ-tweak a pre-existing preset to chase the number.
4. **Run `build_preset.py`** (Step 4): it renders, searches the gear,
   tunes the EQ, sets headroom, and emits the preset + a report. You relay
   the report and persist the preset (Step 5–6). You do not hand-render,
   hand-tune EQ, or hand-stage level — the engine owns the loop.

**Forbidden shortcuts — each has burned a real build:**
- Skipping `tonedb.co`, jumping to a generic web search or to memory.
- Measuring/patching an existing preset's EQ instead of researching +
  authoring the real gear from scratch.
- **Asking the user to diagnose by ear** ("what sounds wrong / too dark?").
  You have no ears AND you do not outsource the diagnosis. The engine drives
  the number; the user's ear enters only when THEY volunteer "it's bad", and
  even then you act on the specific complaint — you never fish for it.
- Treating a low **self-floor** as a tone failure: a sparse/separated stem
  has a low self-floor, the proximity caps there, and "at the floor" is the
  honest ceiling — **report that plainly** to the user (e.g. "the stem's own
  ceiling is 89%; the preset is at it — a longer/cleaner guitar stem is what
  would move the number"). Do not silently ship a dead-feeling preset, and
  do not chase a number that physically cannot move.

## ⛔ THE FORM — author the base chain, run the engine, relay the report

Build EXACTLY this way, every tone, the same. Improvising is where it breaks.
The deterministic loop (render → gear search → EQ trim → headroom) lives in
**`build_preset.py`** (the `openrig-tone-analyzer` engine). Your job is to feed
it a correct **base-chain YAML** and relay its **report** — never to re-narrate
the loop by hand.

1. **Fingerprint the reference** → the honest `match_target` (analyzer schema ≥3):
   `ltas_norm_db` + `reliable_mask` + `reliable_range_hz` + `top_octave_dead` +
   `self_floor_pct`. **The fingerprint is the validator — not the user's ear.**
   The user's ear only enters when THEY volunteer a complaint; never fish for it.
   (`build_preset` re-measures the reference itself; you fingerprint up front to
   shape the EQ direction and to read the per-song floor BAR.)
2. **Research the gear EXHAUSTIVELY** (cited, `tonedb.co` first, THEN multiple
   sources — interviews, rig rundowns, gear DBs, forums). Make a real effort to
   discover the artist's FULL signal chain for THIS song — guitar + pickups, and
   **EVERY pedal** (boost / OD / distortion / fuzz, compressor, wah, modulation,
   delay, reverb), amp(s), cab(s), mic, and any studio technique. Do NOT stop at
   "the amp" — keep digging and cross-checking sources until the rig is complete,
   and cite them. A shallow "amp + done" search is exactly how pedals get missed
   and the tone comes out wrong. Never from memory. **This research is what FEEDS
   the Step 3 candidate lists (Rule A): every amp/drive you later search must
   trace to a source HERE — a thin candidate list is fixed by digging deeper, not
   by padding Step 3 with unrelated gear.**
   ⛔ **Reproduce the COMPLETE researched rig — omit NO element.** Every block the
   research shows is part of the chain: drive(s), compressor, amp, cab, modulation
   (chorus/phaser/tremolo), delay, reverb. **Dropping ANY of them** — because it
   "feels minor", "wasn't a stomp box", or "the number didn't ask for it" — is the
   error that gets the whole batch thrown away. Two traps that make you omit:
   - **Gain:** "no stomp box on the record" is NOT "amp-only." The saturation was
     often a CRANKED / MODDED amp (e.g. Green Day's Dookie-Mod Plexi), but our NAM
     captures are STOCK / lower-gain → under-gained. Cover the missing gain by
     **cranking the amp capture's own `gain` axis** (a `{model, params:{gain:N}}`
     candidate, Rule A) when the capture exposes one, and/or by adding a
     **drive pedal** candidate (boost/OD/distortion); players stack 2–3 drives.
   - **Time/feel:** chorus, delay, reverb, compression the research lists ARE part
     of the tone — author them as FIXED blocks even though **they barely move the
     LTAS number** (they are heard, not measured). The engine keeps every FIXED
     block verbatim; it never tells you an element is missing.
   Before writing the base chain, re-walk the research **element by element** and
   confirm each is in the `blocks:` list. Omit an element ONLY when research shows
   it genuinely absent.
   ⛔ **Zero reverb AND zero delay in your base chain is a RED FLAG — re-research.**
   Before running the engine, COUNT the FIXED time/feel blocks. A finished chain
   with NO reverb and NO delay is almost always a research miss, not a genuinely dry
   tone — a recorded guitar nearly always carries some ambience (a pedal, or the
   studio's reverb/delay). STOP and either **(a)** re-research the artist's reverb /
   delay / modulation / compression for THIS tone and author them (FIXED, params per
   Rule B), or **(b)** confirm with a **CITED source** that the part is genuinely
   dry. Do NOT ship a bare `drive → amp → cab → EQ` preset by default — "the record
   was dry" is a claim that needs a source, not an assumption. (This is not a blanket
   default: you author the artist's ACTUAL ambience, or you cite its absence.)
   ⛔ **Noise gate is research/noise-driven — and a high-gain NAM capture is noisy.**
   Author an **enabled** `dynamics` noise gate when research cites one OR the chosen
   capture's measured noise floor is high (check the analyzer reading / the
   silent-region level of the amp-only render). Set a sensible threshold tagged
   `provenance: unverified` when research gives none. Do NOT leave a noisy high-gain
   NAM amp/drive ungated; do NOT blanket-gate a genuinely clean part.
   ⛔ **Each FIXED block's params are sourced, derivable, or flagged `unverified`
   (Rule B).** Follow the source: **documented** (rig rundown / interview) → use
   the values, tag `provenance: sourced`; **derivable** (delay time = tempo math
   from the song BPM) → compute them, tag `provenance: derived`; **not documented**
   (e.g. a compressor's exact knobs) → set a sensible default, tag the block
   `provenance: unverified`. An **absent marker is treated as `unverified`**. The
   `build_preset` report surfaces every FIXED block under `param_provenance.blocks`
   plus an explicit `param_provenance.unverified` list — you **relay that list to
   the user** (Step 5), never presenting a default as if it were sourced. Params
   the proximity number cannot validate (comp / mod / delay / reverb feel) are set
   from source/default and are **never** optimized by the number.
   ⛔ **"Regulate" is MULTI-BLOCK, not the EQ alone — every block carries researched
   params.** Regulating the tone toward the reference is NOT the 8-band EQ by itself.
   The number regulates the **timbre-affecting** controls TOGETHER: the **amp's
   gain-axis** (the pinned model, its gain regulated via candidate variants, Rule A),
   the **drive** (its gain-axis / selection), AND the **EQ trim** — all toward the
   reference. A run where only the EQ moved and every other block sat at its default
   is WRONG. And EVERY block carries its params from research (Rule B): the
   **feel/time blocks** (compressor, noise gate, delay, reverb, modulation) are set
   from what the artist dials — **documented** → use + `provenance: sourced`;
   **derivable** (delay = BPM math) → compute + `derived`; **undocumented** → a
   sensible default + `unverified`. They are NEVER left at the engine/plugin DEFAULT,
   and NEVER optimized by the number (they are heard, not measured). The amp/drive
   gain-axis, by contrast, IS timbre — so the number regulates THOSE.
3. **Author the base-chain YAML** yourself (Step 3) — a flat `blocks:` list in
   signal order, e.g. `drive(s) → amp → cab → EQ → time-FX`.
   - **SEARCH slots** (the `gain`/`amp`/`preamp`/`body`/`cab` core) carry a
     `candidates:` list instead of a fixed `model` — the engine renders the
     cartesian product and picks the best by proximity.
   - The **ONE** `eq_eight_band_parametric` filter is the **TUNE** slot (no
     `candidates:`, no params needed — the engine starts it flat and trims it).
   - **every other block** (dynamics/wah/pitch/mod/delay/reverb/other filter,
     acoustic body) is a **FIXED** pass-through carrying its researched params +
     `provenance:` tag — the engine keeps it verbatim, in place.
   ⛔ **Rule A — PIN the artist's gear; the number REGULATES, it never PICKS the
   amp.** Each core slot (`gain`/`amp`/`preamp`/`body`/`cab`) is PINNED or SEARCHED,
   its options derived ONLY from the gear Step 2 named, on this priority ladder:
   - **(1) The EXACT researched capture exists in the catalog → PIN it.** Author it
     as a FIXED amp model (`{type: amp, model: <the exact capture>}`), NOT as one of
     several amp models the number ranks. The proximity number is too weak to tell
     amps apart — on a real John Mayer "Gravity" build it ranked a generic
     `nam_fender_deluxe_reverb` at 67.81% ABOVE the artist's actual
     `nam_dumble_ods_john_mayer` at 66.10% (a 1.7% noise gap), with nothing clearing
     the 85.91 floor. A 1–2% spread between amp models is noise; it must NEVER swap
     the artist's actual amp. You MAY add **gain-axis candidate variants of that ONE
     model** (`candidates: [{model: X, params:{gain:5}}, {model: X, params:{gain:8}}]`)
     so the number REGULATES the gain — but NEVER list a DIFFERENT amp model. (The
     engine honors a pinned fixed-model core.)
   - **(2/3) No exact capture exists → SEARCH among documented stand-ins** (multiple
     amp models in `candidates:`; the number picks the closest — they are all guesses
     anyway). Same brand / family / circuit, justified by research (e.g. "1959SLP not
     captured → other Plexi / Super-Lead captures"). For a cranked / MODDED amp with
     no modded capture: the stock researched capture's **gain-axis** variants
     (`{model, params: {gain: N}}`, one per axis value the capture exposes — e.g. the
     Dookie-Mod's `[2, 5, 8, 10]`), and/or a drive whose CHARACTER matches the mod (a
     Marshall-in-a-box / hot OD for a Marshall Dookie-Mod) — mod-matched, not random
     pedals.
   - **Same PIN logic for a preamp or a cab** when the exact researched capture
     exists: pin the model and regulate around it; only SEARCH stand-ins when the
     exact capture is absent.
   The amp's gain-axis IS timbre, so the number regulating it via candidate variants
   is correct (unlike the FIXED-FX feel params Rule B keeps OFF the number). **The
   engine preferring a different amp than the researched one is NOT permission to
   ship it.** When the exact capture exists you PIN it and regulate; if the pinned
   chain cannot reach the floor, that is a real signal — a degraded reference, the
   wrong drive/EQ, or simply a high floor — which you SURFACE to the user. You do
   NOT swap the artist's amp to chase 1–2% of a noisy number. The candidate forms
   the engine accepts: a **bare model-id string** (default params), the literal
   **`none`** (try the slot empty), a **`{model, params:{axis: val}}`** mapping, or a
   `:full_rig` suffix / `full_rig: true` for a cab-baked-in capture. The engine only
   PICKS among research-derived options; it **NEVER** licenses throwing unrelated
   gear into the search "to see what scores". Thin research → widen the RESEARCH
   (Step 2), not the candidate list with guesses.
   ⛔ **AMP vs PREAMP decides the cab — by TYPE, never by measurement.** A
   `type: amp` capture is a FULL amp — a **combo** (speaker baked in, e.g.
   `nam_fender_deluxe_reverb_a2`) OR a head+cab mic'd (e.g. `nam_marshall_1959_slp_a2`)
   — so it **already has its speaker and NEVER takes a cab**. Only a `type: preamp`
   capture (preamp, no power amp/speaker, e.g. `nam_marshall_jcm_800_2203_a2`) needs a
   cab. The engine decides **by the catalog `type`**: for a `preamp` core it
   auto-inserts a **`type: cab` PLUGIN block** (a catalog cab model id, e.g.
   `ir_marshall_4x12_v30`, supplied via `--cab-model`) right after it — ONLY when
   there is no researched cab already in the chain. For a `type: amp` (combo or
   head+cab) or a `type: body` (acoustic) core it inserts NOTHING. You do NOT detect
   this by hand and there is NO top-octave measurement — the `type` is authoritative.
   The cab plugin's manifest carries a per-capture `output_gain_db` the render
   **applies**, so the cab level is right — a raw `generic_ir` wav would skip that
   normalization and land ~18 dB hot, so it is the OFF-CATALOG escape only (a
   genuinely off-catalog IR you author directly as a
   `{type: ir, model: generic_ir, params:{file}}` block), NEVER a stand-in for a
   catalog cab. Per Rule A the cab candidates are research-derived catalog cab model
   ids. Never author both an amp/preamp and a duplicate cab (double cabinet).
4. **Run `build_preset.py`** (Step 4). It measures the reference once, searches
   the SEARCH slots (amp × drive(s); a cab is auto-inserted only for a `preamp`
   core), tunes the EQ (**gentle TRIM, cap ±6 dB**; dead-top and out-of-range bands
   **held at 0**), sets headroom on the EQ `output_db` so the DI peak lands **as hot
   as possible without clipping** (≈ −1 dBFS, never reaching 0 — there is no limiter,
   so the old −7 dBFS headroom no longer applies), and emits the preset YAML + a
   report JSON. **Below the per-song floor is not done** — read `within` from the report.
   ⛔ **The chain ends at the EQ. NO brickwall limiter, NO volume block.** The
   engine **strips** any `limiter_brickwall` (model) or `volume` (type) you put in
   the base chain and never re-adds them — level/headroom is the EQ `output_db`
   alone. Do not author either block, and do not expect one in the emitted preset.
5. **Below-floor rule — do NOT swap a pinned amp to chase the number.** If the
   report's `proximity_pct` **plateaus well below the floor**, do not crank EQ (the
   engine already caps it at ±6). What you do depends on Rule A:
   - **Pinned amp** (the EXACT researched capture exists): the amp does NOT move.
     A below-floor pinned chain is a real signal — a degraded reference, the wrong
     drive/EQ, or simply a high floor. Regulate the gain-axis / drive / EQ, and if it
     still can't reach the floor, SURFACE that plainly to the user. The number being
     1–2% higher on some other amp is NOT permission to swap the artist's amp.
   - **SEARCH stand-ins** (no exact capture): a plateau across the stand-ins means
     the RESEARCH is too thin — widen the researched candidate set and re-run. The
     engine picks among research-derived stand-ins; on a degraded ref, surface that
     the stand-ins all plateau and let the user's ear decide between them.
6. **ONE tone at a time.** `build_preset.py` builds **ONE tone per run** by
   design. Never batch-rebuild with an auto loop — that ships every preset broken
   at once (it gutted 38 presets). Finalize one tone, write the preset file, relay
   the report, and let the user import/validate when they want.

## ⛔ The degraded-reference trap — when the number LIES

A separated stem from a **mix where the instrument is buried** (e.g. the
guitar in a piano-driven song) is not a guitar spectrum — it is a low-mid
fragment with the top octave stripped by the separator. The engine already
**protects you** from chasing it: it caps the EQ trim at ±6 dB and **holds the
dead-top / out-of-range bands at 0** (it never low-passes the render toward a
dead top, and the `fingerprint_match_target` excludes those bands from
`proximity_pct`). So the old "+10…+15 dB low-mid pile" can no longer happen
through the engine. What CAN still mislead is **which gear scores best**:

- **top octave** (~10 kHz) more than ~30 dB below the ~400 Hz body, AND/OR
- **85 % of the energy rolled off below ~1 kHz**, AND/OR
- a **low `self_floor_pct`** (< ~90 %).

When any holds, the reference is **degraded**. Measured on the real Clocks
guitar (Moisés stem: 10 k at −101 dB, 85 % of energy below 630 Hz): the
darkening build measured **88 %** but its high end sat **−18 dB** below the body
(boxy); the gear-driven bright build measured only **64 %** but had a flat,
guitar-like tilt — the **lower** number was the **right** tone.

**Rule:** on a degraded reference, build the **researched gear** (the amp IS the
timbre), let the engine tune within its ±6 cap, and hand it to the **user's ear**
— this is the one case where the number is actively misleading and only the user
playing can judge. Report the degraded reference plainly ("the stem is a
top-dead, low-mid fragment — matching it would darken the tone; I built the
researched rig bright instead, your ear decides"). A cleaner stem (or the
full-mix guitar) is what would let the number lead again.

Build a faithful tone for a real-world song/artist as a **named preset on
a new slot in an existing chain's bank**. Both paths run the SAME engine
(`build_preset.py`, offline); the MCP/file choice is about **where the emitted
preset is stored** (live bank vs YAML file), **never** about whether the
validation gate runs. The agent **MUST ask the user which path before
touching anything** — see Step −1.

## Chain vs preset vs slot — read this before anything else

**A chain is a top-level group in the rig** (e.g. "Electric Guitar",
"Acoustic", "Bass"). Owns the I/O wiring and an instrument tag.
**Where this preset lives — which chain, or a brand-new one — is
always the user's call** (see **Step 3.1**). This skill may call
`add_chain` when the user explicitly opts in; it never picks or
creates a chain on its own.

**A chain has a BANK of preset slots.** Each slot holds one named preset
(the FX layout for one tone). Slots are referenced by index, the preset's
*display name* lives in `RigPreset.name`, the bank stores `slot → key`.
The user switches between slots at runtime to swap tones live.

**A preset is the FX layout for ONE tone**, stored in one slot of a
chain's bank. One chain can hold many presets.

> "Look for the preset, not the chain." Your job is to write a
> **preset**. The chain is just the rig slot it lives in.

This skill **only ever creates or updates presets**. Crucially, it
**adds a NEW slot to the chain's bank** for the preset — it does **NOT**
edit the chain's currently-loaded blocks (that would destroy the user's
existing active preset). See Step 6.

**Before doing anything else, check whether a preset for this song already
exists.** Overwriting tone work the user spent time on is the worst-case
failure mode for this skill. See Step 0 of the workflow.

## ⛔ VALIDATION GATE — the engine generates a FAITHFUL match number

The job of this skill is: **user gives a reference recording → you
produce a preset whose TIMBRE is as faithful to it as possible.** You
have no ears, so the only thing you can optimise toward is a **number** —
and `build_preset.py` is what computes and drives it. The documented failure
("I send a WAV of the song and the tone is nothing like it") happens when that
number is **meaningless** — for two specific, fixable reasons:

> **1. Compare GUITAR against GUITAR.** A timbre number is only faithful
> if both sides are the isolated guitar. A **full mix** (band + vocals +
> drums + bass + keys) is dominated by everything that is NOT the guitar —
> matching a guitar render to it is hopeless. → **Isolate the guitar from
> the reference FIRST** (source separation — see Step 0). Only ever pass the
> isolated-guitar reference to the engine (`--ref`). If you cannot isolate
> it, say so and ask the user for an isolated stem — do **not** validate
> against a full mix.

> **2. The number measures TIMBRE, not the performance.** The reference is
> almost never the bundled DI re-amped — it's a real take with different
> notes, timing, dynamics and level. So a raw `match_score` (which folds in
> note onsets, silence and loudness) can't converge. The engine's number is
> the **energy-weighted spectral proximity over the reliable range** (the
> level-normalised LTAS distance over signal-bearing windows): it ignores
> *which notes were played* and *how loud*, so it isolates **tonal balance**
> — and it converges. That is the number `build_preset` drives.

> ⛔ **You (the agent) cannot hear. Your own "ear" is NEVER the basis.**
> You cannot decide a render "sounds muffled", "dark", or "the delay is
> too long" — asserting any such verdict from yourself is fabrication
> (the same prohibition as the no-suppositions HARD RULE in Step 0).
> **The engine optimises the faithful NUMBER. The ONLY ear that counts is
> the USER'S, and it enters ONLY when the user explicitly says it's bad**
> ("tá ruim", "muffled", "too dark", "delay too long"). Until then you
> relay the number — you do NOT invent an ear opinion to stop early or to
> change course. When the user *does* say it's bad, that specific complaint
> overrides the number and you act on it.

**Acceptance bar: the report's `within` is true** — `proximity_pct ≥
self_floor_pct − 3`, NOT a fixed 95. `build_preset.py` emits all three fields
in its report JSON; do NOT hand-convert from a dB gap:
- **`proximity_pct`** (0–100) — the **energy-weighted, reliable-range**
  timbre distance of the winning chain. It FALLS on an audible mismatch (a
  sub-bass boom, mud) and is unmoved by an inaudible rolled top.
- **`self_floor_pct`** — the reference's own self-similarity across
  signal-bearing windows (from the fingerprint, carried into the report): the
  **per-song physical ceiling**. You cannot match the reference better than it
  matches itself. Measured ~79–96 % across real songs.
- **`within`** — whether the bar was cleared (`proximity_pct ≥
  self_floor_pct − 3`). **Gate on `within`.**

A fixed 95 is wrong both ways: it chases an impossible number on material whose
floor is 85, and lets a boomy preset that reads 95 pass. The render+compare is
MANDATORY whenever a reference exists (saving without it is a blind guess — the
Clocks v1 failure) — and `build_preset` IS that gate. If `proximity_pct`
**plateaus below the floor** across candidates, widen the researched candidate set
and re-run — but the **pinned amp does not move** (Rule A / the Below-floor rule):
widen the drive / gain-axis / EQ for a pinned amp, the stand-in models only when no
exact capture exists. Only if you genuinely cannot reach the floor do you STOP and
report both numbers as a shortfall. `best_prox` is the
best proximity seen; the per-iteration `refine_history` / `gear_history` are
diagnostics. **`match_score` is NEVER the bar** (it folds in onsets, silence and
level). The user's ear can override at any point, but their *silence* never
lowers the bar.

If the user explicitly says they have **no reference at all**, declare
that **out loud in the chat** before saving — "no reference provided, this
preset is a research-only guess; I cannot validate it" — so the user can decide
whether to provide one or accept the limitation. Silent skipping = failure.

The DI is the bundled `<openrig-di>`, resolved in **Step 0b** from the
install's data root (`assets/audio/input.wav`). You never ask the user for a DI;
only the *wet reference* comes from them. If it is missing from the install,
that is a packaging bug — stop and tell the user, do not improvise.

### Level is NOT timbre — the engine owns headroom, never the ref's RMS

The preset's **output level is set by the engine's headroom pass** (the EQ
`output_db`, targeting the DI peak ≈ −1 dBFS, hot but never clipping) — it is **never** matched to the
reference's RMS. A real reference is often quiet (soft playing, gaps, mastering
headroom); matching its RMS ships a broken-feeling preset. The report's
`peak_db` is the measured DI peak you relay. Any `match_score`/`diff.json`
recommendation about RMS or level is a **level** recommendation and is
**ignored** for tone purposes — the engine's headroom pass owns level,
independently of the reference. (The proximity number never touches level; the
headroom pass never touches timbre.)

## Step −1 — Ask the user: MCP live or YAML file only?

Before touching anything, ask **once** which persistence path the user
wants. This choice is about **where the emitted preset is stored** (live bank vs
YAML file) — **not** about whether the build runs. `build_preset.py` runs
**offline on both paths**; it never requires `--mcp`. Both paths are valid:

> "For this preset, I'll go: **(a) via MCP on the live rig** (I build it
> offline, then import the emitted preset into a new slot in the bank,
> audible immediately — requires OpenRig running with `--mcp`), or
> **(b) YAML file only** (the emitted preset YAML is the deliverable; I
> write it to `<openrig-user-data-root>/presets/<name>.yaml` without
> touching the rig)?" *(render in the user's language at runtime — this
> English template documents the structure, not the literal words to ship)*

* If **(a) MCP** — confirm the MCP tools are wired (precondition below)
  and follow the **MCP persistence** step (Step 6, MCP branch).
* If **(b) file** — the emitted preset YAML is the deliverable; no MCP
  needed. The **only** MCP calls allowed on this path are reads of the
  resources `openrig://plugins`, `openrig://project`, and
  `openrig://plugins/{id}/params` (installedness + schema lookup, when the
  rig happens to be up). **Every other MCP call is forbidden.**
* If the user does not answer, default to **(b) file only** — it is the
  flow that always works (MCP is frequently closed). Mention you can import
  it into the live bank afterward if they start OpenRig with `--mcp`.

## Step 0a — Persistent evaluation directory (BEFORE Step 0)

Everything this skill produces during a build — the analyzer fingerprints, the
renders, the report JSONs, the per-iteration preset snapshots, the iteration
log — must land under a **per-song persistent directory** so it survives a
`/tmp/` wipe, a reboot, a machine migration, or "let me re-validate this preset
next month against the same reference".

### Resolve the evaluations directory, once, at the top of Step 0a

**MCP up:** read the resource `openrig://paths` (added in #582). It returns the
user's effective resolved system paths as JSON:

```jsonc
{
  "data_root": "/Users/.../Library/Application Support/OpenRig",
  "presets_path": "/Users/.../presets",
  "plugins_path": "/Users/.../plugins",
  "evaluations_path": "/Users/.../evaluations"
}
```

Use `evaluations_path` as the root for every artifact (`<openrig-evaluations-root>`).

**MCP closed (the common case):** `openrig://paths` is unavailable, so resolve
from the on-disk config, then the OS default:
1. `<openrig-user-data-root>/config.yaml` → its `evaluations_path` /
   `plugins_path` / `presets_path` keys, if set.
2. Else the OS default data root: macOS →
   `~/Library/Application Support/OpenRig/`, Linux →
   `${XDG_CONFIG_HOME:-~/.config}/OpenRig/`, Windows → `%APPDATA%\OpenRig\`;
   evaluations live under `<data-root>/evaluations/`.

Do NOT hardcode any per-OS path inline; resolve once and reuse. `/tmp/...` dirs
used by the analyzer/render binaries are volatile scratch — pass
`--out-dir`/`--output` at `<openrig-evaluations-root>/<song-slug>/` so outputs
land where they belong from the start.

### Compute the `<song-slug>` and create the directory

`<song-slug>` is derived deterministically from `"<song> - <artist>"` (or
`"<song> - <artist> (<role-group>)"`): lowercase, strip accents, replace any run
of non-`[a-z0-9]` with a single `-`, trim leading/trailing `-`. Keep it stable
across re-builds — the slug is the directory key.

Create (or reuse) `<openrig-evaluations-root>/<song-slug>/` (placeholders —
substitute the real `<song-slug>`, `<role>`, iteration `<N>` at build time):

```text
<openrig-evaluations-root>/<song-slug>/
├── eval.md                       # human-readable iteration log
├── refs/<role>.wav               # copy of user's reference WAV (sha256 verified), one per role
├── fingerprints/ref-<role>.json  # one per role
├── chains/<role>-v<N>.yaml       # the base-chain YAML you authored (engine input)
├── renders/<role>-v<N>.wav       # engine render(s)
├── reports/<role>-v<N>.json      # build_preset report JSON per run
└── presets/
    ├── <role>-v<N>.yaml          # emitted preset snapshot per run
    └── <role>-final.yaml         # the version the user accepted
```

### Reuse vs first-build

- **If `<song-slug>/` already exists**, READ `eval.md` first: prior iteration
  count, last `proximity_pct` vs floor, prior status (`done`/`iterating`/
  `abandoned`), gear mapping, methodology notes. Continue iteration numbering
  from the last `<role>-v<N>`; never overwrite an existing one.
- **If it does not exist**, create it fresh; initialise `eval.md` from the
  template below.
- **Never `rm -rf` an existing `<song-slug>/` to "start clean"** — prior
  renders, reports, and per-iter YAML snapshots are the user's audit trail. If
  something is genuinely corrupted, ask the user before deleting.

The `refs/` subdir specifically exists so **re-evaluation (Step 8) remains
possible months later** — the persistent ref is the only thing that makes
"compare this preset to the same reference next year" tractable.

### Copy the user's reference WAVs (do NOT symlink)

For every reference WAV: compute its sha256; `cp` (NOT `ln -s`) it to
`refs/<role>.wav`; re-compute the destination sha256 and verify it matches — if
not, STOP and surface the mismatch. If `refs/<role>.wav` already exists from a
prior build, compare sha256s: **same hash** → reuse, log "ref unchanged";
**different hash** → ask the user once whether it's a deliberate ref swap or a
mistake. Never silently overwrite a reference prior iterations compared against.

### `eval.md` template

Initialise on first build by **substituting** every `<placeholder>` with the
live build value (real song title, artist, slug, chain id). The skeleton uses
placeholders because **this skill text** doesn't know the song; **your eval.md**
must end up with real values:

```markdown
# <Song> — <Artist>
**Status:** iterating
**Date:** <YYYY-MM-DD>
**Chain:** <chain display name> (<chain id>)
**Slots:** <role>=<slot index>

## Gear research
- <bullet list of researched gear + era + sources>

## Mapping
| Real | OpenRig candidate(s) |
| ---- | -------------------- |
| <real-gear> | <model_id(s)> |

## Iteration log
### <role>
| iter | proximity_pct | self_floor_pct | within | key change |
| ---- | ------------- | -------------- | ------ | ---------- |
| v1   | <pct>         | <floor>        | <bool> | baseline   |

## Param provenance (unverified FX defaults)
- <type/model from report's param_provenance.unverified, surfaced to the user>

## Methodology notes
- <session-specific notes>

## Sources
- <URLs>
```

Set `Status:` to `done` when the user accepts, `abandoned` if they walk away,
`iterating` otherwise. Optionally maintain a global
`<openrig-evaluations-root>/INDEX.md` (one row per song: slug, song, artist,
best `proximity_pct`, last date, status).

## Step 0b — Resolve the engine (`build_preset.py` + `openrig-render` + DI) — BEFORE Step 0

The build gate runs **`build_preset.py`** (the `openrig-tone-analyzer` engine).
It drives the **installed** `openrig-render` — the headless offline renderer
OpenRig ships next to the GUI (issue #741), the **same** `engine::offline::
render_chain` the live rig uses, so an offline render is byte-identical to the
rig. It needs no live runtime and no MCP. Resolve these **once, up front**:

**1. `build_preset.py`** — in the analyzer skill:
`skills/openrig-tone-analyzer/scripts/build_preset.py`, run via its venv
(`skills/openrig-tone-analyzer/.venv/bin/python`, after `./bootstrap.sh`).

**2. `openrig-render` (`--render-bin`)**, in order:
1. `$OPENRIG_RENDER_BIN` if set — explicit override, wins.
2. `command -v openrig-render` — on `PATH` (Linux `.deb`/`.tar.gz` →
   `/usr/bin/openrig-render`).
3. Per-OS install: macOS →
   `/Applications/OpenRig.app/Contents/MacOS/openrig-render` (also
   `$HOME/Applications/...`); Linux → `/usr/bin/openrig-render`; Windows →
   `openrig-render.exe` in the install dir.
4. **Dev tree** (contributor in the source repo): `target/release/openrig-render`.

⚠️ **The installed app may NOT ship `openrig-render` yet** (a 0.1.0-dev
`OpenRig.app` shipped only the GUI `openrig`). When only the dev-tree binary
resolves, it is the working path — but it REQUIRES two extra inputs that map to
`build_preset` flags:
- **`--dyld-lib`** → `DYLD_FALLBACK_LIBRARY_PATH` pointing at the NAM dylib dir
  (`libnam_wrapper.dylib`, e.g. `<OpenRig>/build/nam-*/out/lib`). macOS dev only.
- **`--plugins-root`** → `OPENRIG_PLUGINS_ROOT` =
  `<OpenRig-plugins>/plugins/source` (the source manifests the dev render
  registers).

With a properly bundled **installed** binary, the bundle's `Frameworks` rpath
finds `libnam_wrapper.dylib` and the data root auto-resolves the bundled plugins
— so `--dyld-lib`/`--plugins-root` are omitted. If neither an installed nor a
dev `openrig-render` resolves, **STOP and tell the user to install/update
OpenRig** — do not skip the gate (it is mandatory before "done").

**3. Bundled DI (`--di`).** macOS →
`/Applications/OpenRig.app/Contents/Resources/assets/audio/input.wav`; Linux →
`/usr/share/openrig/assets/audio/input.wav`; dev → `<OpenRig>/assets/audio/
input.wav`. (Or `openrig://paths.data_root` + `/assets/audio/input.wav` when MCP
is up.) You **never** ask the user for a DI.

**4. Cab model (`--cab-model`, optional).** A catalog `type: cab` plugin model id
(e.g. `ir_marshall_4x12_v30`, NOT a `.wav`) the engine auto-inserts ONLY for a
`type: preamp` core — the cab plugin's manifest `output_gain_db` is applied, so the
level is right. Omit for a `type: amp` (combo/head+cab) or already-cabbed base chain.

> ⛔ **`openrig-render` EXITS 0 even when it cannot build a block.** It logs
> `ignoring unsupported or invalid block ...` / `unsupported nam model '<id>'`
> and renders WITHOUT that block — the GUI's bypass-and-continue, NOT a loud
> failure. **A zero exit does NOT prove a complete render.** `build_preset`
> handles this for you: it captures stdout+stderr and treats those markers as a
> **HARD failure** (`assert_no_dropped_blocks`), so a typo'd / uninstalled model
> id can never silently ship a preset missing a researched block. This is why
> you route the render through `build_preset` (and, for Step 8 re-eval, scan the
> raw render output for those markers yourself). Exit `1` = render genuinely
> failed; exit `2` = argument error.

`openrig-render` flags (no `--preset`): `--chain <preset.yaml> --input <DI>
--output <wet.wav>` plus optional `--start/--end/--sample-rate/--block-size/
--bit-depth/--tail-ms`. `--chain` takes a flat `blocks:` list — the exact shape
of a saved preset / the engine's emitted preset.

## Step 0 — Fingerprint the reference audio FIRST (when WAVs are provided)

If the user provided ANY reference WAV, invoke the
**`openrig:openrig-tone-analyzer` skill on each WAV before research, before gear
mapping, before any MCP call**. The fingerprint is a **primary input for tonal
SHAPE** (where the energy sits) — it shapes the EQ direction; research fills in
what the signal cannot reveal (amp model/era, brand of pedal) **and** the
delay/reverb the fingerprint cannot measure reliably. Going straight to research
biases toward what "sounds right on paper"; but the **opposite** failure is just
as real — **over-trusting fragile fingerprint fields** (`centroid`, `RMS`,
`time_fx`) on a sparse/separated stem. Read the caveat below first.

How:

0. **Guitar-only check.** The reference must be the **isolated guitar**. If the
   user sends a **full mix**, isolate the guitar first (source separation — e.g.
   `demucs`) and use only the separated guitar; if you cannot separate it, STOP
   and ask for an isolated stem rather than validating against a mix.
1. For each reference WAV, invoke `openrig:openrig-tone-analyzer` with the file
   path. It writes a JSON fingerprint + spectrogram PNGs and returns the paths.
2. **Read every fingerprint JSON before opening any research URL.** It tells
   you: EQ **shape** to lean toward (centroid + band_energy → direction, a hint
   cross-checked against the spectrogram + LTAS, never a hard target); gain stage
   (gain_character → clean/crunch/high-gain); time effects (**low-confidence, do
   NOT set blocks from these**); role hint (source.kind → preset name).
3. If multiple stems were provided (rhythm + lead, several solos), fingerprint
   **each** separately — they produce different presets.
4. **Persist each fingerprint** into `fingerprints/ref-<role>.json` (`cp` from
   the analyzer's volatile scratch dir). Overwrite an existing one only when the
   ref WAV's sha256 also matches (Step 0a already gated the ref-swap question).

If the user provided **no** reference audio, skip Step 0 and declare out loud:
"no reference WAV provided — analyzer fingerprint skipped, this preset will be
research-only and cannot be validated objectively". The user can then provide a
WAV or accept the limitation.

### ⛔ Fingerprint reliability caveat — which fields lie, and when

A **sparse stem** (mostly silence + a few sustained notes), a **source-separated
stem** (bleed, artifacts), or a **leaky/full mix** distorts the scalar fields:

| Field | Trust | How to use it |
|---|---|---|
| `band_energy` / normalized **LTAS shape** over signal-bearing windows | **Usable as SHAPE** | Directional EQ guide ("more energy 2–4 kHz") — cross-check against the spectrogram. Never a hard target. |
| `centroid` | **Fragile** | On a sparse/separated stem it tracks *which notes were held*, not timbre. Do not low-pass off a low centroid; confirm against the spectrogram + LTAS. |
| `RMS` / loudness | **Never a target** | Reflects performance dynamics + mastering, not tone. Level is the engine's headroom pass, never matched to the ref. |
| `time_fx` (delay/reverb) | **Low-confidence** | Artifact-prone (reverb tail → "long delay"; hall → "spring"). Delay/reverb come from research (Step 2), not from this field. |
| `gain_character` / `tone_profile` | Usable | Clean/crunch/high-gain class is robust. |

**The cross-check is always spectrogram PNG + normalized LTAS shape, not a
single scalar.** When a fragile scalar and the spectrogram/shape disagree, the
spectrogram + shape win. This is the structural reason the validation number is
the **energy-weighted spectral proximity**, not a raw score. (You never
substitute your own ear — you have none; the user's ear is the only override.)

### ⛔ Ref-sanity check — is the top end real, or a separation artifact?

A source-separated stem often **loses its top octave**. The engine detects and
excludes it for you: when the reference's top octave is dead, the
`fingerprint_match_target` marks it (`top_octave_dead`) and the proximity metric
restricts to the trustworthy range, and the EQ trim **holds** the top bands
(never cutting them toward the dead ref). So:
- `proximity_pct` already reflects only the trustworthy range — it will NOT read
  a false 99% off a muffled preset. You still gate on `within`.
- the EQ trim **HOLDS** the top bands; it never low-passes the render.

When the top octave is dead:
- **NEVER hand-cut the top or swap to a darker amp to "match" the dead ref** —
  cutting the top to chase a missing octave is the "99% but sounds muffled" bug.
- **Let the amp's natural voicing carry the presence.** Pick amp candidates on
  the trustworthy range + research; leave the top alone.
- **Tell the user once**, e.g.: *"this stem is source-separated and lost its top
  octave (no real amp is that dark up top), so I'm matching the trustworthy
  range and letting the amp's natural brilho carry the presence — I will NOT
  low-pass the tone to match the dead top. A cleaner isolated stem would let me
  match the full range."* *(render in the user's language at runtime)*

### ⛔ HARD RULE — no suppositions about what the reference contains

> Every claim about what is IN the user's reference WAV must cite a **fingerprint
> field** (or a directly readable artefact: spectrogram PNG, the raw waveform).
> **Cultural priors about the song / artist / era / genre are NOT evidence about
> THIS specific WAV.** If the fingerprint doesn't measure something, you don't
> know it — say so.

**Always forbidden** (even in chat narration):
- Claiming a **playing technique** no fingerprint field measures. The
  fingerprint exposes `tone_profile`, `dynamics_profile`, `presence`,
  `loudness`, `spectrum`, `distortion`, `time_fx`. It does **not** measure
  palm-mute, fingerpicking, alternate/sweep/hybrid picking, tapping, arpeggios,
  chugging, or strumming pattern. Saying "heavy palm-mute" about the user's WAV
  is **fabrication** unless a specific waveform/spectrogram detail supports it
  (and even then, "consistent with X", not "the WAV is X").
- Inferring content from the **song title**, **artist**, **album/era**, or
  **memory of how the song sounds**. The user's WAV might be a cover, a stem
  isolated imperfectly, a different section, a live take, or a remix. Cultural
  priors belong in **research** (Step 1), NOT in claims about the reference.
- Inventing differences between the bundled DI and the user's reference to
  explain a gap ("the DI is clean fingerpicking, the player palm-muted"). Name
  real fingerprint/report deltas, never guessed performance differences.

**How to phrase claims correctly** — pair every observation with its citation:
- ✅ "section 2 of the ref has `tone_profile: high_gain` (conf 0.88) and
  `dynamics_profile: rhythmic` — the render came out `crunch`, THD deficit ~7%."
- ✅ "I cannot assert the player's technique — the analyzer does not measure
  palm-mute. What I can see is `dynamics_profile: rhythmic` and a high onset rate."
- ❌ "the player is probably palm-muting, that's why it's more compressed."
- ❌ "the Metallica riff needs palm-mute, so the gap is because of that."

**Stem vs mix caveat:** an isolated stem's centroid describes the guitar; a
full-mix centroid is dominated by drums/bass/keys and is only an upper bound.
When the WAV is a full mix, treat the centroid as a ceiling, look at the
spectrogram of guitar-only sections, and ask the user for an isolated stem.

### ⛔ HARD RULE — no suppositions about real-world GEAR / tone / history

This is the **transversal** version, applying in **any** turn this skill is
loaded — including a casual chat question with no build running ("how do you get
the Green Day tone?", "what amp does X use?"). **Never state a claim about
real-world gear, signal chains, amp/cab/pedal/pickup models, specs, prices, an
artist's rig, an album's recording setup, or music history from training
memory.** Those priors produced the documented failure: confidently asserting
"Green Day = cranked Marshall, zero pedal, Bill Lawrence L-500XL" — and being
wrong (there was a Boss Blues Driver; the pickup is disputed; the tone is
low-gain, not cranked).

**Every such factual claim must be backed by ONE of:**
1. a **measured number** from the analyzer (fingerprint / `proximity_pct` /
   LTAS / spectrogram), or
2. a **web source you fetched THIS turn** (`WebSearch` / `WebFetch`), URL cited.

If you have neither: **verify first** (`WebSearch`, then cite), or **label it**
explicitly *"(unverified — from training memory)"*. "It's the logical answer" /
"everyone knows X uses Y" = the anti-pattern.

**Red-flag self-check before any chat message stating a gear/tone/history
fact:** "Can I cite a URL I fetched this turn, or a number I measured? If not —
WebSearch now, or label it unverified, or cut it." A plugin hook
(`no-suppositions-guard`) reinforces this, but the rule binds with or without it.

## Precondition (MCP persistence path only) — the MCP server must be connected

Only relevant if the user picked the MCP path (the build itself runs offline):

1. Confirm the OpenRig MCP tools are available (e.g. `apply_rig_nav`,
   `load_chain_preset`, `rename_rig_preset`, `save_chain_preset`) and
   `openrig://project` reads. The OpenRig plugin wires this when OpenRig runs
   with `--mcp`.
2. If the tools/resource are **not** available, STOP. Tell the user to start
   OpenRig with `--mcp` and install the OpenRig plugin (`docs/mcp.md`). Offer the
   file-only path (the emitted YAML) as the alternative. Do NOT silently fall
   back — confirm with the user first.

The rig is shared: changes via MCP are reflected in the open GUI in real time.

## Iron rule — sources of truth for discovery / schema / recipes

Catalog work has three orthogonal questions. Each has an authoritative source —
with an **MCP-closed fallback**, since MCP is frequently down:

1. **"Which `MODEL_ID`s exist AND are installed RIGHT NOW?"** (discovery /
   installedness) →
   - **MCP up:** `openrig://plugins` (every plugin loaded by THIS instance:
     `id`, `display_name`, `brand`, `block_type`, `backend`).
   - **MCP closed:** the **OpenRig-plugins manifests** under the resolved
     `plugins_root` (Step 0a/0b) — each plugin's `manifest.yaml`/`index.json`
     lists its model ids — **plus** the render output-scan (`build_preset`'s
     dropped-block detection): if a candidate id is wrong/uninstalled the run
     hard-fails, so installedness is proven at render time too.
   See **Step 2.5**.

2. **"For a chosen `MODEL_ID`, what are its param paths/types/ranges/defaults/
   enums?"** (schema) → **MCP up:** `openrig://plugins/{id}/params`. **MCP
   closed:** the plugin's manifest (parameter axes/defaults). This matters for
   the **FIXED FX params** you author in the base-chain YAML (Rule B) and for the
   MCP-commit path's `set_block_parameter_*` calls. See **Step 2.6**.

3. **"What knob *values* do real players use? Which amp/cab pairings are
   canonical?"** (recipes) →
   [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md)
   in `jpfaria/OpenRig-plugins`. WebFetch it if not checked out. This answers
   "good starting points", NOT "what's a valid param".

> ⛔ **Source-id vs packed-id suffix (silent-drop trap).** Source manifest ids
> carry an arch suffix (`nam_marshall_1959_slp_a2`); the packed `index.json` (and
> `openrig://plugins`) merge to bare ids (`nam_marshall_1959_slp`). The dev
> render registers the **SOURCE** ids (its `plugins_root` is `…/plugins/source`)
> — so `candidates:` must use the form that matches the **resolved plugins
> root**: source root = arch-suffix ids. A mismatched id is silently dropped at
> exit 0 (and then caught by `build_preset`'s output-scan). Normalize the suffix
> before any installedness membership check.

You MUST NOT:
- Open or grep any file under `crates/block-*/src/` to discover model IDs or
  params. The MCP schema / the manifest IS the runtime.
- Read existing presets to copy `MODEL_ID` strings or param shapes (they drift).
- Guess or invent model IDs or param paths from memory. Dotted (`eq.bass`) and
  bare (`bass`) paths both occur and `bass` ≠ `eq.bass` to the runtime.
- Trust `blocks-reference.md` for **schema** questions — it is the recipes source.

If a model you need is not installed, that is a **missing-capture case** — go to
**Step 2.5**. Do NOT silently substitute. If a model's schema returns
`parameters: []`, it has no exposed params — author it with empty `params: {}`.

## Mandatory inputs

- `<artist>` — band/artist name.
- `<song>` — song title (optional but strongly preferred — gear varies by era).
- `<role>` — `rhythm` / `lead` / `solo` / `clean`. Rhythm and lead almost always
  need DIFFERENT presets. Ask the user once if not given.
- *(optional)* `<reference-audio>` — a WAV stem of the guitar (ideally isolated).
  Lets the engine run the render→compare gate. Without it you cannot validate
  the preset objectively; flag this to the user.

If only `<artist>` is given, ask once for the song and role.

## Workflow — the primary flow (author → `build_preset.py` → relay → persist)

This is the SAME flow on both paths; only the final **persist** step (Step 6)
differs. The build (`build_preset.py`) is always offline.

### 1. Research the signal chain

**The Step 0 fingerprint comes first.** Research fills gaps the analyzer cannot
resolve (specific amp model/era, brand of pedal, recording context) — not to
drive the build. If you have not fingerprinted every reference WAV, go to Step 0.

Hit sources **in order**, stopping when you have a confident gear list
(instrument → pedals → amp → cab → mic). Always cite which sources you used.

| Priority | Source | Why |
|---|---|---|
| 1 | `https://www.tonedb.co/` (search by song or artist) | Crowdsourced, song-specific, often explicit signal chain. JS-heavy — if WebFetch returns 404/empty, fall back to Playwright MCP. |
| 2 | `https://www.groundguitar.com/tone-breakdown/` | Per-song gear listings with chain order. |
| 3 | `https://killerrig.com/` | Numeric knob settings per song. |
| 4 | `https://musicstrive.com/<artist>-amp-settings/` | Settings per song / per guitarist. |
| 5 | `https://www.guitarchalk.com/<player>-amp-settings/` | Player-focused. |
| 6 | `https://prosoundhq.com/...` | Generic recipes; fallback EQ. |
| 7 | `https://blog.andertons.co.uk/sound-like/...` | Gear context per era. |
| 8 | Premier Guitar / Guitar World rig rundowns | Authoritative for era + recording context. |

When two sources disagree on knob values, prefer the one that names the song.
**Fallback ladder when `WebFetch` fails/empties** (common on tonedb.co):
Playwright MCP → WebSearch → ask the user to paste page text. Recipes still come
from `blocks-reference.md`; discovery from `openrig://plugins`/manifests; param
schema from `openrig://plugins/{id}/params`/manifest — never from web research.

### 2. Map gear to a CANDIDATE SET per SEARCH slot (Rule A) — discovery first

> ⛔ **HARD ORDER GATE — discovery BEFORE recipes:**
> 1. **Resolve the installed `id` set** this turn: `openrig://plugins` (MCP up)
>    OR the manifests under the resolved `plugins_root` (MCP closed). Cache it.
> 2. **Shortlist candidate `MODEL_ID`s** by matching the researched gear against
>    `block_type` + `brand` + `display_name` + `backend` (manifest fields when
>    MCP is closed). This is where `Vox AC30` → `nam_vox_ac30_*` happens. **Search
>    the `id` + `display_name` for BOTH the researched amp/model AND the ARTIST
>    NAME** — the catalog carries **artist/song-signature captures** (e.g.
>    `nam_dumble_ods_john_mayer`, the Dookie-Mod `nam_marshall_1959_slp`). An
>    **exact artist-signature or exact-model capture, when it exists, is PINNED as
>    the amp** (Rule A priority 1) — authored as a fixed `{type: amp, model: …}`,
>    NOT thrown into a number-ranked contest against other amp models (the proximity
>    number is too weak to tell amps apart — on a real "Gravity" build it ranked a
>    generic Fender above the artist's actual John-Mayer Dumble by 1.7%). Reaching
>    for a generic stand-in (a plain Fender for a John-Mayer Dumble tone) while the
>    exact capture sits in the catalog is a **Rule A violation** — grep the catalog
>    for the artist first.
> 3. **ONLY THEN** consult `blocks-reference.md` — by `MODEL_ID`, for recipe
>    values (knob ranges per style, pairings). The doc is consulted **after** you
>    have the IDs, never **to find** them.
>
> **FORBIDDEN:** `Read`/`grep`/`WebFetch` on `blocks-reference.md` before step 1;
> greping the doc for amp brands, song/artist names, or gear keywords as a
> discovery query. Discovery is `openrig://plugins`/manifests, always.

**PIN what's exact; SEARCH only what's a guess (Rule A, Step 3 of THE FORM).** When
the EXACT researched capture exists, the amp/preamp/cab is **PINNED** — a fixed
`{type: <slot>, model: <exact capture>}`, optionally with **gain-axis variants of
that ONE model** (`{model, params:{gain:N}}`, one per axis value) so the number
REGULATES the gain without ever swapping the model. Only when NO exact capture
exists do you assemble a multi-model `candidates:` SET for that slot — documented
close stand-ins (plus `none` to try the slot empty), all guesses the number picks
between. For an under-gained / modded amp with no modded capture, use the stock
capture's gain-axis mapping candidates and/or a mod-matched drive. The engine
renders the cartesian product of the SEARCH slots and regulates within the PINNED
ones; you supply only research-derived options.

Prefer NAM amps over Native amps when the song has a real amp model. The Step 0
fingerprint is your primary input for the EQ **shape** (the engine TUNES the EQ;
you don't pre-set it) and the gain class. (`time_fx`/`centroid`/`RMS` are
fragile — see Step 0's caveat; do not set delay/reverb from `time_fx`, do not
EQ-darken off a raw `centroid`, do not target the ref's `RMS`.)

### 2.5. Verify each candidate `MODEL_ID` is installed; route missing captures

The candidate set names specific `MODEL_ID` strings. Before authoring them into
the base chain, cross-check **every** one against the installedness source.

1. **Read the installed `id` set once** (`openrig://plugins` MCP up; manifests
   MCP closed), BEFORE authoring. Cache it. (`build_preset`'s render output-scan
   is the backstop: a wrong/uninstalled id hard-fails the run — but resolve
   upfront, don't rely on the failure as discovery.)
2. **Check every `MODEL_ID`** — including stock blocks (`compressor_studio_clean`,
   `gate_basic`, `eq_eight_band_parametric`, `generic_ir`). Normalize the
   source/packed suffix first (Iron rule). **For every miss, the default proposal
   is `openrig:openrig-tone3000-fetch`** — substitution with a different installed
   plugin is a last-resort fallback, allowed only after the import path was
   attempted and failed OR the user explicitly refused. The ask leads with import:

   > "For the [block/role] the canonical capture is `<MODEL_ID>` (from
   > `<amp/cab/...>`), but it is not installed. I'll attempt to import it from
   > tone3000 via `openrig:openrig-tone3000-fetch <query>` — this gets the
   > authentic capture, though it triggers the issue → PR → qa_audit/pack_plugins
   > flow. Confirm to proceed, or tell me to pick a different path."
   > *(render in the user's language at runtime)*

3. **Apply the user's response:**
   - **(a) Confirm import.** Invoke `openrig:openrig-tone3000-fetch`. On success,
     after the file lands under OpenRig-plugins and clears the
     qa_audit/pack_plugins gate, the user's instance must reload its catalog
     (`reload_plugin_catalog`) before the id appears; re-read the installed set
     to confirm. On failure (no hit, fetch error, qa_audit block, user veto), you
     may go to (b) — but ask explicitly, naming the failure mode; never fall
     through silently.
   - **(b) Substitute — only after (a) was attempted and closed.** Ask WHICH
     specific substitute; present 3–5 candidates with matching `block_type` and
     adjacent `brand`/`display_name`, let the user pick. Record it in the Step 5
     provenance (`substituted <wanted> → <used> per user OK`).
   - **(c) Abort.** Stop the build; save nothing partial.

   **One ask per missing capture** (or batch them in one message, each with its
   own tone3000 query). Do NOT collapse into a unilateral "substitute/import all".

4. Do not author the base chain until every candidate `MODEL_ID` is present OR
   explicitly substituted with the user's OK.

### 2.6. (Optional / FIXED-FX + MCP-commit) Read the param schema for the params you author

`build_preset` does NOT call `set_block_parameter_*` — it authors the preset from
your base-chain YAML. So the live-schema **param-setting mechanics** here apply
only to the **MCP-commit path** (if you ever tweak a placed block) — NOT to the
core flow. But you still author **FIXED FX params** (Rule B) and **gain-axis
candidate params** in the YAML, so when MCP is reachable, read
`openrig://plugins/<MODEL_ID>/params` (or the manifest when closed) to author
**valid param paths/values**:

- **Which param paths exist** — paths are often dotted (`eq.bass`,
  `noise_gate.threshold_db`); two amps in a family can expose different paths.
- **Valid range/step** (`domain.FloatRange.{min,max,step}`) and **enum options**
  (`domain.Enum.options[].value`) so a value isn't clamped/rejected.
- **`default_value`** — fall back to it when neither a recipe nor the fingerprint
  constrains the param.

`openrig-render` silently ignores an unknown param path (it does not drop the
block), so an unvalidated FIXED-FX path fails quietly. **MCP up:** validate paths
against the schema. **MCP closed:** flag the authored params as "unverified
paths" to the user and recommend loading the emitted YAML once in OpenRig to
check the GUI for any silently-ignored params. The amp/drive **axis** params come
from the chosen SEARCH candidate (the capture's own axis, Rule A) and need no
schema lookup; the EQ is always TUNED by the engine, never authored with gains.

For the **MCP-commit path only**, the typed-tool mapping (decided by the schema's
`domain` field) is: `FloatRange`/`IntRange` → `set_block_parameter_number`;
`Bool` → `set_block_parameter_bool`; `Enum` → `select_block_parameter_option`
(pass `value`, not `label`); else → `set_block_parameter_text`. This mapping is
NOT used by the core build flow — the engine authors the preset directly.

### 3. Author the base-chain YAML

Write a flat `blocks:` list in signal order to
`<openrig-evaluations-root>/<song-slug>/chains/<role>-v<N>.yaml`. Realise the
COMPLETE researched rig (Step 2 of THE FORM): SEARCH slots carry `candidates:`,
FIXED FX carry researched `params:` + a `provenance:` tag, the ONE
`eq_eight_band_parametric` is the TUNE slot (flat — the engine trims it).

```yaml
id: <song-slug>-<role>
name: "<Song> — <Artist> (<role>)"
blocks:
  - type: dynamics            # FIXED pass-through (researched: MXR Dyna Comp)
    model: compressor_studio_clean
    params: { ratio: 4, threshold_db: -18 }
    provenance: unverified    # default knobs, no documented source -> surfaced
  - type: gain                # SEARCH the drive ('none' = try the slot empty)
    candidates: [none, nam_ibanez_ts9_a2, nam_proco_rat_a2]
  - type: amp                 # SEARCH the amp; gain-axis variants + ':full_rig'
    candidates:
      - nam_marshall_1959_slp_a2
      - { model: nam_marshall_1959_slp_a2, params: { gain: 8 } }
      - { model: nam_marshall_1959_slp_a2, params: { gain: 10 } }
      - nam_mesa_dual_rect_a2:full_rig          # cab baked in -> engine skips cab
  - type: filter              # the corrective EQ the engine TUNES (starts flat)
    model: eq_eight_band_parametric
  - type: delay               # FIXED pass-through (time from tempo math)
    model: digital_clean
    params: { time_ms: 343, feedback: 28, mix: 30 }
    provenance: derived       # delay time computed from the song BPM
  - type: reverb              # FIXED pass-through; no provenance -> 'unverified'
    model: hall
    params: { mix: 14 }
```

Rules the engine enforces (so author accordingly):
- The ONE `eq_eight_band_parametric` filter is the TUNE slot. Any OTHER filter is
  a FIXED pass-through. Do not author EQ band gains — the engine starts it flat,
  trims ±6, and appends it last; you never position it by hand.
- Do NOT author a `limiter_brickwall` or a `volume` block — the engine **strips**
  both (the chain ends at the EQ; level is the EQ `output_db`).
- A `:full_rig` candidate (or `full_rig: true` mapping) means the cab is baked in
  — never also author a separate cab for that amp.
- `candidates:` and `provenance:` are build-time metadata, stripped from the
  emitted preset.
- **Do NOT add `tuner_chromatic` or `spectrum_analyzer`** — they are rig-wide
  utilities, not chain blocks (the runtime rejects them).

### 4. Run `build_preset.py`

```bash
skills/openrig-tone-analyzer/.venv/bin/python skills/openrig-tone-analyzer/scripts/build_preset.py \
  --base-chain <…>/chains/<role>-v<N>.yaml \
  --ref        <…>/refs/<role>.wav \
  --cab-model  <catalog type:cab model id>  # optional; omit for a full-rig base chain \
  --render-bin <openrig-render-bin>    # Step 0b \
  --di         <openrig-di>            # Step 0b \
  --out-preset <…>/presets/<role>-v<N>.yaml \
  --out-report <…>/reports/<role>-v<N>.json \
  --name "<Song> — <Artist> (<role>)" --id <song-slug>-<role>
# Dev tree only — add: --plugins-root <OpenRig-plugins>/plugins/source
#                       --dyld-lib    <OpenRig>/build/nam-*/out/lib   (macOS dev)
```

The engine: measures the reference once (fingerprint floor + LTAS target);
classifies SEARCH/TUNE/FIXED; searches amp × drive(s) (a cab is auto-inserted only for a `preamp` core) and
picks the best proximity; EQ-refines the winner (±6 cap, dead-top/out-of-range
held); sets headroom on the EQ `output_db` (DI peak ≈ −1 dBFS, hot but never clipping); writes the
preset YAML + report JSON. It catches any silently-dropped block from the render
output and HARD-fails — so a clean run means every researched block built.

If the run **fails** (`assert_no_dropped_blocks` or a non-zero render exit), it's
a bad model id / param — fix the base chain (check the id against the installed
set + the suffix form) and re-run. Do NOT ship.

### 5. Relay the report (incl. unverified FX defaults) + update `eval.md`

The report JSON carries: `amp` / `amp_type` / `amp_params`, `drives` /
`drive_params`, `core`, `cab_model`, `fixed_fx_preserved`, **`param_provenance`**
(`blocks` + `unverified`), `proximity_pct`, `self_floor_pct`, **`within`**,
`best_prox`, `peak_db`, `reliable_range_hz`, `refine_history`, `gear_history`.

**Chat reply provenance summary** (every build):
1. **Chain + slot + preset name** (the actual rig values, never skill examples).
2. **Mapping table**: real gear → the **chosen** amp/drive(s)/cab from the report
   (`amp`, `amp_params`, `drives`, `cab_model`). Mark Step-2.5 substitutions
   explicitly (both wanted and used id).
3. **Match numbers**: `proximity_pct` vs `self_floor_pct`, and `within`. If
   `within` is false, say the gear plateaued below the floor and what you'll
   widen (or that the floor is the honest ceiling).
4. **Headroom**: the report's `peak_db` (e.g. "DI peak −1.1 dBFS", max without clipping).
5. **Unverified FX defaults**: read `param_provenance.unverified` and **surface
   each to the user** ("the comp + reverb knobs are sensible defaults, not
   sourced — tell me if you have the real values"). Never present a default as
   sourced.
6. **Cite sources** you fetched. **Point at the eval dir**
   (`<openrig-evaluations-root>/<song-slug>/`) for the full audit trail.

**`eval.md`** (per build): append an iteration row (`proximity_pct`,
`self_floor_pct`, `within`, key change); populate `## Gear research`,
`## Mapping`, `## Param provenance`, `## Methodology notes`, `## Sources` from
the real research; set `Status:` (`iterating`/`done`/`abandoned`); update a
global `INDEX.md` row if you keep one.

### 6. Persist the emitted preset

**File-only path (default):** the emitted `presets/<role>-v<N>.yaml` IS the
deliverable. Copy it to the user's presets dir
`<openrig-user-data-root>/presets/"<Song> — <Artist> (<role>)".yaml` (ask once if
a non-default `presets_path` is configured) and snapshot it as
`presets/<role>-final.yaml` on accept. Tell the user: *"To hear it, open
OpenRig, select chain `<chain>`, and use **Load Preset** pointing at this file.
The in-memory rig was not touched."* *(render in the user's language at runtime)*

**MCP path:** import the emitted preset into a **NEW slot** — never overwrite,
never a manual `add_block`/`set_block_parameter_*` build:

0. **Check first whether a preset for this song already exists** across all
   chains (`openrig://chains/<chain>/presets`, `openrig://presets`). If a
   candidate exists, STOP and ask whether to **replace**, **save alongside**
   (e.g. ` (v2)`), or **show only**. Never overwrite without confirmation.
1. **Read `openrig://project` and ALWAYS ask where to put this preset** —
   **Step 3.1** below (the chain-pick / create-new-chain mechanics, unchanged).
2. **Add a NEW empty slot:** `apply_rig_nav { chain, kind: { Preset: -1 } }`. The
   `-1` adds an empty slot and makes it active — it does **NOT** touch any
   existing preset's blocks. This is the safe path; from here you load into a
   clean slot.
3. **Load the emitted preset into that slot.** Place the engine's
   `presets/<role>-v<N>.yaml` into the new slot — `load_chain_preset` on the
   written file, or `cp` it into the configured `presets_path` and reload the
   bank. The blocks come from the engine, verbatim — you do not re-author them.
4. **Name + commit:** `rename_rig_preset { chain, name: "<Song> — <Artist>
   (<role>)" }` then `save_chain_preset { chain, name }`. Do **not** call
   `save_project` (the preset is the unit of work). Snapshot the live YAML back
   to `presets/<role>-v<N>.yaml` if it differs.

#### Step 3.1 — Where to put the preset (MCP path) — new slot, never overwrite

**Read `openrig://project` and ALWAYS ask the user.** List every chain (id,
display name, `instrument`, short block summary) as a numbered menu — **including
when only one chain matches** — plus a final "create new chain" option. Do NOT
auto-pick.

> "Where do you want to put this preset?
> **(1)** chain `<id>` ('<name>', instrument `<x>`, blocks: `<summary>`)
> ...
> **(N+1) create new chain** — I'll ask for name + instrument + I/O devices."
> *(render in the user's language at runtime)*

You MAY recommend one option, but **MUST wait for the user's explicit pick**.
Auto-selecting because "only one chain matches" is forbidden, as is a single-line
"use `<chain>`? (y/n)" — render the full menu always.

**If the user picks `(N+1) create new chain`:**
1. **Name + instrument prompts** (in one ask). Never infer the instrument from
   the song or chain name; re-ask the missing one explicitly.
2. **Read `openrig://devices`** ONCE, immediately before the menus, and render
   TWO numbered menus (input, output) using the actual `<label>` + `device_id`.
   Recommend allowed, but wait for an explicit pick per side; render the menu
   even with one device. Y/n shortcut forbidden.
3. **Channels + mode prompts** per chosen device (`[1]` mono, `[1,2]` stereo;
   mode `mono`/`stereo`/`dual_mono`). Suggest a default in the ask, never
   self-apply. Re-ask any of the four unanswered (in-device, in-channels+mode,
   out-device, out-channels+mode).
4. **Build the Chain payload and call `add_chain`:**
   ```json
   { "chain": { "enabled": true, "instrument": "<from 1>", "blocks": [
     { "id": "rig:input",  "kind": { "Input":  { "entries": [{ "device_id": "<…>", "channels": [<…>], "mode": "<…>" }] } } },
     { "id": "rig:output", "kind": { "Output": { "entries": [{ "device_id": "<…>", "channels": [<…>], "mode": "<…>" }] } } }
   ] } }
   ```
   `Input.entries[]`/`Output.entries[]` are arrays (multi-device is possible but
   not the default). If `add_chain` errors, **STOP and surface the exact error**
   — do not retry with mutated values or fall back to a different device.
5. **Continue the import into the new chain id.**

**Zero chains:** go straight to create-new (still asking name + instrument + I/O)
but say "your rig has no chains yet — I'll create one". **Exactly one chain:**
still render the menu (option 1 = it, option 2 = create new). **No answer:** ask
once more or stop — never decide for them.

### Plan reference (electric guitar default — adjust per song style)

The base chain you author (Step 3) is the COMPLETE researched rig. A typical
electric layout, in signal order:

```text
1.  dynamics / <compressor>   FIXED   parallel-style clean compression (provenance per Rule B)
2.  dynamics / <noise gate>   FIXED   research/noise-driven — include + ENABLE for a noisy high-gain NAM capture; skip a genuinely clean part
3.  gain     / <drive(s)>     SEARCH  the DRIVE STAGE — candidates per Rule A; STACK 2-3 in series when researched
4.  amp      / <amp>          PIN/SEARCH  EXACT capture in catalog -> PIN it {type:amp,model:X} + gain-axis variants of THAT model (number regulates gain, never swaps amp); only when no exact capture -> SEARCH stand-ins / ':full_rig' (Rule A)
5.  (cab)                     auto    engine auto-inserts a type:cab plugin ONLY for a type:preamp core (--cab-model, applies output_gain_db); a type:amp (combo OR head+cab) already has its speaker → never cabbed
6.  filter   / eq_eight_band  TUNE    the engine trims it (±6) and appends it last — you author it flat
7.  delay    / <delay>        FIXED   time from BPM math (provenance: derived) — a tone with NO reverb AND NO delay is a research red flag
8.  reverb   / <reverb>       FIXED   room for rhythm, hall for lead
```

> ⛔ **The drive stage is first-class and STACKS.** An electric tone almost
> always has at least one drive; players run two or three (clean boost → TS →
> Big Muff). Author one `gain` SEARCH slot per pedal, in the researched order. A
> cranked/modded amp's gain is covered by the amp's **gain-axis** candidates
> (Rule A), not by defaulting to amp-only. The ONLY electric exception is a
> genuinely clean part (drop the drive slots). "The amp crunch is enough" is a
> rationalization unless research shows the part was truly pedal-free.

Adjust per style: **Clean/acoustic** — drop the drive slots and gate, clean amp,
add an acoustic `body`/IR. **Funk/clean rhythm** — keep the compressor, lower amp
gain. **Lead solo** — more delay mix, hall reverb. **Delay-driven (Edge/Mayer
rhythm)** — delay time = dotted-eighth at the song BPM (`60000/bpm*1.5/2`),
feedback ~25–35%, mix ~30–40%. **Doom/drone** — drop boost, raise reverb mix,
tape-style delay.

### Knob translation note (MCP-commit path / FIXED-FX authoring only)

NAM amp captures bake knobs into the capture; what the *block* exposes varies per
plugin (there is no universal NAM control surface). For the **amp/drive SEARCH
slots** you do not set knobs — you offer **gain-axis candidates** (Rule A) and
the engine picks. For **FIXED FX** you author params in the YAML from research +
the schema (Step 2.6). Three schema patterns you'll meet (decide per-plugin,
never assume): **structural-only** (enum/select + I/O level; shape via the EQ
TUNE slot), **full continuous knobs** (bass/mid/treble on the block), and
**`parameters: []`** (fixed processor — `params: {}`). Which pattern a given
`MODEL_ID` is, is only knowable from its schema/manifest.

## Step 8 — Re-evaluation of an existing preset

Use when the user asks to re-validate a preset that already exists ("compara de
novo X com a ref", "rerun the compare for <song>"). NOT a fresh build — no
research, no rebuild. A strict **render-current-YAML → compare → log** cycle.

Preconditions: (1) `openrig-render` resolves (Step 0b) — re-eval runs offline on
either path; (2) `refs/<role>.wav` exists (else ask the user for the original ref
and run Step 0a + Step 0 to backfill); (3) the preset YAML exists (the live
`presets/...yaml` OR `presets/<role>-final.yaml` — ask which if they diverge).

Flow:
1. **Read `eval.md`** to recover chain, gear mapping, last index. Use a
   `<role>-vREEVAL-<YYYY-MM-DD>` index (date suffix — re-evals don't bump `<N>`).
2. **Render the current preset YAML** directly:
   `<openrig-render-bin> --chain <preset.yaml> --input <openrig-di> --output
   <…>/renders/<role>-vREEVAL-<date>.wav`. ⚠️ **Scan the render's stdout+stderr
   for `ignoring unsupported or invalid block` / `unsupported nam model`** — exit
   0 does NOT prove a complete render. If a marker appears, the YAML references a
   dropped block; surface it, don't compare a partial render.
3. **Compare** against the persistent ref:
   `.venv/bin/python scripts/compare.py <…>/refs/<role>.wav
   <…>/renders/<role>-vREEVAL-<date>.wav --output <…>/diffs/<role>-vREEVAL-<date>.json`.
4. **Append a re-eval row** to `eval.md` (do NOT flip `Status:` from `done`). If
   the user wants to actually tune from the result, that's a fresh build (re-run
   `build_preset.py`, continuing `<N>`).
5. **Chat reply**: the new proximity, the diff vs the prior best (from `eval.md`),
   and the diff-file path.

Re-eval does NOT mutate the rig, does NOT call `save_chain_preset`.

## Validation before declaring done

- [ ] You fingerprinted every reference WAV (Step 0) BEFORE research and any MCP
      call, and the reference is the **isolated guitar** (separated from a mix if
      needed, or you stopped and asked for a stem) — never a full-band mix.
- [ ] You resolved `<openrig-user-data-root>` / `<openrig-evaluations-root>` per
      OS (or via `openrig://paths` / `config.yaml`) at the top of Step 0a and
      used the resolved value everywhere. No `~/.openrig/` literal in any output.
- [ ] You created `<openrig-evaluations-root>/<song-slug>/` with the full subtree
      (`refs/`, `fingerprints/`, `chains/`, `renders/`, `reports/`, `presets/`,
      `eval.md`); ref WAVs `cp`'d (NOT symlinked) and sha256-verified;
      fingerprints persisted into `fingerprints/`.
- [ ] The base-chain YAML names **only installed** `MODEL_ID`s (every candidate
      cross-checked against `openrig://plugins` / the manifests in **Step 2.5**,
      suffix-normalized), with the right form for the resolved plugins root.
      Missing captures went through Step 2.5 with `tone3000-fetch` as the primary
      proposal; any substitution was the user's explicit pick from a list, after
      import was closed, recorded in Step 5 provenance.
- [ ] The base chain has the COMPLETE researched rig — every drive/comp/mod/
      delay/reverb the research showed — with FIXED-FX params tagged
      `provenance:` (Rule B), the artist's EXACT capture PINNED (`{type: amp,
      model: X}` + gain-axis variants of that one model) and stand-in candidate
      SETs only where no exact capture exists (Rule A), ONE flat
      `eq_eight_band_parametric` TUNE slot, NO `limiter_brickwall`/`volume`, NO
      `tuner_chromatic`/`spectrum_analyzer`.
- [ ] You ran **`build_preset.py`** (not a hand-built `add_block` loop, not a
      manual eq_match loop). It completed without `assert_no_dropped_blocks` /
      render failure — so every researched block built. The render used the
      bundled `<openrig-di>`, never a user DI.
- [ ] You gated on the report's **`within`** (`proximity_pct ≥ self_floor_pct −
      3`), NOT a fixed 95, NOT `match_score`, NOT a hand-converted dB gap. If it
      plateaued below the floor you widened the drive / gain-axis / EQ (or the
      stand-in models where no exact capture exists) and re-ran — you did NOT swap
      a pinned amp to chase the number, and did NOT call a below-floor preset done
      (unless the floor IS the honest ceiling, which you reported plainly).
- [ ] You relayed the report's `peak_db` (the engine's headroom pass set the EQ
      `output_db` to ≈ −1 dBFS, hot but never clipping; you did NOT match the ref's RMS, did NOT add a
      limiter/volume, did NOT hand-stage level).
- [ ] You surfaced every `param_provenance.unverified` FX default to the user —
      no default presented as sourced.
- [ ] You did NOT set delay/reverb from `time_fx`, did NOT EQ-darken off a raw
      `centroid`, did NOT assert a sonic verdict of your own. The user's ear
      redirected the build ONLY when the user said it's bad.
- [ ] **Persist (file path):** the emitted preset YAML is the deliverable; it was
      copied to the presets dir and snapshotted to `presets/<role>-final.yaml` on
      accept. **Persist (MCP path):** you checked for a pre-existing preset, ran
      the Step 3.1 menu (no auto-pick; `add_chain` only with all four prompt
      blocks answered + `openrig://devices` read), added a NEW slot via
      `apply_rig_nav Preset(-1)`, loaded the emitted preset, set the name via
      `rename_rig_preset`, committed via `save_chain_preset`, and did NOT call
      `save_project`, did NOT touch any input/output/insert block.
- [ ] `eval.md` was updated per build with the proximity/floor/within row and
      `Status:` per outcome.

## Red flags — STOP

- **Hand-building the preset with `add_block`/`set_block_parameter_*` instead of
  authoring a base chain and running `build_preset.py`.** The engine owns the
  render → gear search → EQ trim → headroom loop. Your job is the base-chain YAML
  + relaying the report. (The only MCP mutations are the Step 6 import:
  `apply_rig_nav Preset(-1)` → load → `rename_rig_preset` → `save_chain_preset`.)
- **Authoring a `limiter_brickwall` or `volume` block** (or expecting one in the
  emitted preset). The engine STRIPS both — the chain ends at the EQ; level is
  the EQ `output_db` alone (`peak_db` ≈ −1 dBFS, hot but never clipping).
- **Trusting a zero render exit as proof of a complete render.** `openrig-render`
  exits 0 even when it drops a block (`ignoring unsupported or invalid block` /
  `unsupported nam model`). `build_preset` HARD-fails on those markers
  (`assert_no_dropped_blocks`); on a raw Step 8 render, scan the output yourself.
- **Throwing an unrelated amp/pedal into `candidates:` "to see what scores".**
  SEARCH candidates are research-derived ONLY (Rule A): the exact capture,
  documented close stand-ins, gain-axis variants of the modded capture, or a
  mod-matched drive. Thin research → widen the RESEARCH (Step 2), not the
  candidate list with guesses.
- **Letting the number SWAP the artist's actual amp.** On a real "Gravity" build
  the proximity ranked a generic `nam_fender_deluxe_reverb` (67.81%) above the
  artist's `nam_dumble_ods_john_mayer` (66.10%) — a 1.7% noise gap, nothing clearing
  the floor. When the EXACT capture exists you PIN it (`{type: amp, model: …}`) and
  regulate its gain-axis; the number NEVER picks the amp. A below-floor pinned chain
  is a degraded-ref / wrong-drive / high-floor signal you surface — not a license to
  ship the Fender.
- **A generic stand-in when the EXACT artist/model capture is in the catalog.**
  Grep the catalog for the artist + model FIRST (e.g. `nam_dumble_ods_john_mayer`);
  if it's installed, it's the PINNED amp — never a plain Fender "because it's close".
- **Leaving timbre blocks at default while only the EQ moves** — "todos os blocos têm
  regulagens" (every block has adjustments). Author each block's params from research
  (Rule B) and regulate the amp gain-axis + the drive + the EQ together — never the
  EQ alone with every other block at its engine/plugin default.
- **Shipping a chain with ZERO reverb AND ZERO delay** without a cited source
  confirming the part is dry — almost always a research miss (a recorded guitar
  nearly always carries some ambience). Re-research the artist's ambience or cite the
  dryness. **And leaving a noisy high-gain NAM capture UNGATED** — author + enable a
  `dynamics` gate when research or the measured noise floor calls for it.
- **Presenting a guessed FX knob (comp/mod/delay/reverb) as if researched.** If a
  param isn't documented or derivable, set a default, tag the block
  `provenance: unverified`, and surface it from the report's `unverified` list
  (Rule B). The proximity number never sets these feel params.
- **Adding a cab after a `type: amp` capture** (a combo OR a head+cab — speaker
  baked in) — double cabinet. The engine auto-inserts a cab ONLY for a `type: preamp`
  core; a `type: amp` is a full amp and never gets one. Never author both.
- **Chasing the raw `match_score`, a fixed 95, or a hand-converted dB gap.**
  Gate on the report's **`within`** (`proximity_pct ≥ self_floor_pct − 3`). The
  raw score folds in onsets/silence/level and can't converge on a real recording
  (the "Gravity" 166→131 dB stall).
- **Asserting your OWN sonic verdict** ("sounds muffled/dark/the delay is too
  long"). You cannot hear — that is fabrication (Step 0's no-suppositions rule).
  Act on the measurement; the only ear that redirects the build is the **user's**,
  and only when they actually say it's bad. **Dismissing the user's ear** when
  they DO say it's bad is equally forbidden — that complaint overrides the number.
- **Setting delay/reverb from `time_fx`** (a reverb tail reads as an 865 ms
  delay; a hall reads as "spring"). Delay/reverb come from research + the song.
- **Low-passing / EQ-darkening off a low `centroid`** on a sparse/separated stem
  (it tracks *which notes were held*). Read it as directional shape cross-checked
  against the spectrogram + LTAS.
- **Matching the reference's RMS / level.** A real reference is often quiet; the
  engine gain-stages the DI peak to ≈ −1 dBFS, hot but never clipping independently of the ref.
- **Reporting "done" without running `build_preset.py`** when a reference exists.
  This is the failure the user called out: "you're missing the most important
  thing. you should run the render." A research-only preset is a guess.
- **Silently substituting a missing capture** instead of proposing
  `openrig:openrig-tone3000-fetch` first (Step 2.5). Substitution is a fallback,
  not a peer — and still requires the user picking the specific substitute from a
  list. Documenting it after the fact does not authorize a unilateral decision.
- **Greping `blocks-reference.md` for a brand/song/artist to "find" a
  `MODEL_ID`.** That's discovery — discovery is `openrig://plugins` / the
  manifests, always. The doc is a recipe lookup keyed by `MODEL_ID`, consulted
  after the IDs are known.
- **`set_block_parameter_*` / authoring a param path from memory** instead of the
  schema/manifest. `bass` ≠ `eq.bass`; the wrong path is silently ignored.
- **Saying "I'll persist this rule in memory" / proposing any write to
  `~/.claude/projects/*/memory/`** to capture a user correction. Corrections go
  into the **SKILL** (this file) or the project's **`CLAUDE.md`** — local memory
  is per-machine, doesn't ship with the plugin. See the project's `CLAUDE.md`.
- **Claiming a playing technique** (palm-mute, fingerpicking, sweep, tapping,
  arpeggio, chugging, strumming) about the user's WAV. The fingerprint does NOT
  measure technique — stating it is fabrication (Step 0 HARD RULE).
- **Using song/artist/era/genre knowledge as evidence about THIS WAV.** Cultural
  priors feed research (Step 1), never claims about the audio.
- **Calling `add_chain` without `openrig://devices` + both I/O menus + explicit
  device/channels/mode picks** (a chain without wired Input + Output is unusable),
  or **auto-picking a chain** in Step 3.1.
- **`rm -rf`-ing an existing `<song-slug>/`** to "start clean" (erases the audit
  trail — continue numbering), or **leaving renders/reports in `/tmp/`** to "copy
  later" (write directly to the eval dir), or **symlinking** the ref instead of
  `cp` (breaks `tar`-portability).
- **Hardcoding `~/.openrig/`** or any per-OS path inline (resolve once in Step 0a).
- **Opening any reference / planning the FX layout before invoking
  `openrig:openrig-tone-analyzer` on every reference WAV.** Step 0 comes first.

## Common rationalizations — forbidden

| Rationalization | Reality |
|---|---|
| "I'll hand-build it with `add_block` / hand-tune the EQ — same result" | No. `build_preset.py` is the deterministic FORM: it searches the gear, tunes the EQ within ±6, holds dead-top bands, and sets headroom in one pass. A hand loop is exactly the stale manual workflow this skill replaced. Author the base chain, run the engine, relay the report. |
| "I'll add a safety limiter / output volume so it doesn't clip" | The engine STRIPS `limiter_brickwall` and `volume`. The chain ends at the EQ; headroom is the EQ `output_db` (DI peak ≈ −1 dBFS, hot but never clipping, report `peak_db`). Authoring either is wasted — and wrong. |
| "The render exited 0, so the preset is complete" | `openrig-render` exits 0 even when it drops a block (`ignoring unsupported or invalid block` / `unsupported nam model`). `build_preset` scans the output and hard-fails; a raw Step 8 render you scan yourself. Exit code alone proves nothing. |
| "The installed app has no `openrig-render`, I'll skip the gate" | Use the dev-tree `target/release/openrig-render` with `--render-bin`, plus `--dyld-lib` (NAM dylib) and `--plugins-root <…>/plugins/source` (Step 0b). Only if NO render binary resolves do you STOP and tell the user to install/update OpenRig — never silently skip. |
| "Proximity is stuck at 88%, that's close enough / best I can get" | The bar is the report's `within` (within ~3% of `self_floor_pct`), not a fixed 95. If 88% is below the floor, widen the researched candidate set (amp/drive/cab, gain-axis). If 88% IS within ~3% of the floor (the material's own ceiling), you're DONE — stop chasing an impossible number. |
| "I'll convert `total_gap_db` to a % / gate on the dB gap / chase `match_score`" | The report emits `proximity_pct` + `self_floor_pct` + `within` directly. Read and gate on `within`. `match_score` folds in level/onsets/silence and never converges on a real recording. |
| "The ref is dark up top, so I'll cut the top / pick a darker amp to match it" | If the top octave is dead it's a separated stem that lost its brilho — no real amp is that dark. The engine excludes those bands and HOLDS them; let the amp's natural brilho carry the presence. Never cut the top or swap darker to chase a dead top. |
| "The user sent the whole song, I'll compare against that" | A full mix is dominated by drums/bass/vocals — matching a guitar render is hopeless. Isolate the guitar first; if you can't, ask for a stem. Compare guitar-against-guitar only. |
| "It sounds muffled to me, so I'll EQ-brighten / the delay sounds too long" | You have no ears — a sonic opinion from you is fabrication. Act on the measurement; the only ear is the **user's**, on their word. |
| "The user says it's muffled but the number looks fine — I'll trust the number" | When the **user** says it's bad, that overrides the number — act on the specific complaint. The measurement is your default basis; the user's stated verdict is the override. |
| "The fingerprint says delay 865 ms / 39% — I'll set the delay block to that" | `time_fx` is artifact-prone (that 865 ms was a reverb tail; the "spring" a smooth hall). Delay/reverb come from research + the song. Weak corroborator only. |
| "The stem's centroid is ~480 Hz, the tone is dark — I'll low-pass" | On a sparse/separated stem the centroid tracks *which notes were held*, not timbre. Read it as directional shape, cross-check the spectrogram + LTAS, never low-pass off the scalar. |
| "The reference RMS is quiet, I'll match it" | Level is never matched to the ref. The engine gain-stages the DI peak to ≈ −1 dBFS, hot but never clipping, independently of the reference. Matching RMS ships a broken preset. |
| "I built it from research, no need to render" | Research = educated guess. `build_preset.py` is mandatory when a reference exists; the only validated preset is one the engine rendered + measured to the floor. Clocks v1 (saved without rendering) was thrown away. |
| "I'll toss extra amps/pedals into `candidates:` to see what scores" | Rule A: candidates are research-derived ONLY — the exact capture, documented close stand-ins, gain-axis variants of the modded capture, or a mod-matched drive. The engine picks among researched gear; it never blesses unrelated gear. Thin research → widen Step 2. |
| "No modded capture exists, so the amp will just be under-gained" | Use the capture's own **gain-axis** as candidates: `{model, params:{gain:N}}`, one variant per axis value (Rule A). The number picks the right gain; the amp's gain IS timbre. If the capture has no axis, add a mod-matched drive candidate. |
| "The number ranked a Fender above the John-Mayer Dumble, so I'll ship the Fender" | The proximity number is too weak to tell amps apart — 67.81% vs 66.10% is a 1.7% noise gap, and nothing cleared the floor. When the EXACT capture exists you PIN it (`{type: amp, model: …}`) and regulate its gain-axis; the number NEVER picks the amp. A below-floor pinned chain is a degraded-ref / wrong-drive / high-floor signal you surface, not a reason to swap the artist's amp. |
| "A generic Fender is close enough, no need to hunt the exact capture" | Grep the catalog for the artist + model first (e.g. `nam_dumble_ods_john_mayer`). If the exact capture is installed, it's the PINNED amp. "Use what the artist uses, and keep regulating" — a stand-in is only for when no exact capture exists. |
| "I'll just regulate the EQ, the other blocks are fine at default" | Regulating is multi-block: the amp's gain-axis + the drive + the EQ trim all move toward the reference, and every feel block (comp/gate/delay/reverb/mod) carries researched params (Rule B), never the engine default. A run where only the EQ moved is wrong — "todos os blocos têm regulagens" (every block has adjustments). |
| "No reverb or delay in my chain — the record was probably dry" | "Probably dry" is an assumption, not a source. Zero reverb AND zero delay is a red flag: re-research the artist's ambience or cite a source confirming it's dry. And a noisy high-gain NAM capture needs an enabled gate when its noise floor calls for it — don't ship it ungated. |
| "I don't have the comp's exact knobs, I'll set values and move on" | Set the default, but tag the block `provenance: unverified` and surface it from the report's `unverified` list (Rule B). Never present a default as sourced. The number never sets feel params. |
| "The record used a 4×12, so I'll author a cab after the NAM amp too" | A `type: amp` capture (combo OR head+cab) already has its speaker — a separate cab double-cabinets. The engine auto-inserts a cab ONLY for a `type: preamp` core (via `--cab-model`, a catalog `type: cab` plugin id). Supply `--cab-model` for preamp cores; never author a cab after a `type: amp`. |
| "I'll point `--cab-model` at a 4×12 IR `.wav` / use a `generic_ir` block for the cab" | A catalog cab is a `type: cab` PLUGIN whose manifest `output_gain_db` the render applies — that's the right level. A raw `generic_ir` wav skips that normalization and lands ~18 dB hot. `--cab-model` takes a catalog model id, never a wav; `generic_ir` is the OFF-CATALOG escape only (a genuinely off-catalog IR), authored directly in the base chain. |
| "`tone3000-fetch` is heavy, I'll just substitute" | Cost is the user's decision. Step 2.5 leads with `tone3000-fetch`; substitution is a fallback, and even then you ask which specific substitute. They asked for THE tone, not A tone. |
| "I'll grep `blocks-reference.md` for `vox ac30` / `streets` to find the `MODEL_ID`" | That's discovery — discovery is `openrig://plugins` / the manifests, ALWAYS. The doc is a recipe lookup keyed by `MODEL_ID`, consulted after. |
| "I remember this param path from a similar amp" | Different plugins in a family use different paths (dotted vs flat). An unknown FIXED-FX path is silently ignored by the render. Read the schema/manifest (Step 2.6). |
| "Only one chain matches the instrument, I'll go straight to it" | Step 3.1 always renders the menu and waits for the pick, even with one match. Auto-picking is the exact behaviour the step blocks. |
| "The user pre-confirmed the chain in the args / a prior chat" | If you cannot paste a verbatim sentence from the user THIS turn saying "use chain X", they did not. Present the Step 3.1 menu. Cross-session memory is forbidden. |
| "The Metallica riff is obviously high_gain — I'll skip the fingerprint" | Step 0 is unconditional. The WAV could be a cover, a different take, a clean mix. Cultural prior + "obvious" = the failure this skill blocks. Read the fingerprint. |
| "I'll research first, then fingerprint" | Wrong order. Research without the fingerprint biases toward what sounds right on paper. Step 0 before Step 1. |
| "The user corrected me — I'll save the lesson to memory" | Local memory is per-machine, doesn't ship with the plugin. A correction becomes an edit in `SKILL.md` or the project's `CLAUDE.md`. Memory ≠ persistence. |
| "MCP isn't connected, I'll just write the YAML" | The file-only path (emitted YAML) is a first-class, valid path — but the user picked the path in Step −1. Don't silently switch; if they chose MCP, stop and ask. |
| "Step 0a bookkeeping is overhead, the user wants the tone" | Step 0a IS delivering the tone: without `<song-slug>/`, re-validation (Step 8) is impossible. Bookkeeping is what makes the tone auditable, portable, re-comparable. |

## Anti-patterns (all paths)

- ❌ **Hand-building the preset (`add_block` + `set_block_parameter_*`) instead of
  `build_preset.py`.** The engine is the build. Manual MCP mutations are ONLY the
  Step 6 import (`apply_rig_nav Preset(-1)` → load → rename → save).
- ❌ **Authoring `limiter_brickwall` / `volume`** — the engine strips both.
- ❌ **A second `eq_eight_band_parametric`** — there is ONE TUNE slot; any other
  filter is a FIXED pass-through.
- ❌ **A cab after a `type: amp` capture** (combo or head+cab — speaker baked in).
  A cab auto-inserts ONLY for a `type: preamp` core.
- ❌ **`tuner_chromatic` / `spectrum_analyzer` in the chain** — rig-wide
  utilities, rejected by the runtime.
- ❌ **Inventing a model name that "sounds right"** — every id is a hard-matched
  string (and an unmatched one is silently dropped at exit 0).
- ❌ **A `preamp` block for a full-amp song** — `preamp` has no power-amp/cab;
  songs almost always want `amp`.
- ❌ (MCP path) **Editing the chain's current blocks / `apply_rig_nav`-skipping**
  to write a preset — switch to a NEW slot first; **calling `save_project`**
  instead of `save_chain_preset`; **overwriting an existing preset** without
  asking; **`add_chain` with `blocks: []`** or inferred device_ids.
- ❌ **Silently switching MCP↔file** without the user's explicit Step −1 answer.
- ❌ **Stopping at "saved" when a reference was provided** — `build_preset.py` is
  the gate; run it before declaring done.
