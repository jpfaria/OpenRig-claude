# openrig-tone-analyzer

Pure-function audio analyzer for guitar tones. Two modes:

- **`analyze <wav>`** — emits `fingerprint.json` (v2 schema with per-section
  descriptors) and spectrogram PNGs to a temp directory.
- **`compare <ref.wav> <wet.wav>`** — auto-picks the reference section that
  best matches the wet signal, emits `diff.json` with ranked recommendations
  for adjusting the chain, plus an A/B spectrogram.

No network. No MCP. No `openrig --render`. The skill never mutates the rig
or any OpenRig project — orchestration belongs in `openrig-tone-builder`.

## Manual run

```bash
cd skills/openrig-tone-analyzer
./bootstrap.sh                          # idempotent venv setup
.venv/bin/python scripts/analyze.py /path/to/track.wav
.venv/bin/python scripts/compare.py /path/to/ref.wav /path/to/wet.wav
.venv/bin/python scripts/eq_match.py /path/to/ref.wav /path/to/wet.wav --gains 0,0,0,0,0,0,0,0
```

`analyze.py`/`compare.py` print the resolved output directory on their last
line. Open the PNGs to inspect; feed the JSON to your downstream consumer.

`eq_match.py` is a pure measurement step (no rig, no network): given the
reference, the wet render, and the EQ's current 8 band gains, it emits the
next gains (`new_gains`) that move the render's normalised LTAS shape
toward the reference, plus `total_gap_db`. `build_preset.py`'s internal
refine loop applies the gains (capped ±6, dead-top bands held), re-renders,
and repeats until `within` / plateau / the iteration cap.

`build_preset.py` is the deterministic **FORM** of the openrig-tone-builder
skill as ONE portable tool: it builds **ONE tone per run** (never a batch),
entirely **offline**, from a surviving reference. The caller researches the
**COMPLETE** rig (compressor, wah, pitch, modulation, delay, reverb, acoustic
body — every researched element) and passes it as a **base-chain YAML**: a flat
`blocks:` list in signal order. The timbre-determining **CORE** (a `type:
amp`/`preamp`/`body` block) is recognised **by its type**, whether it is
**PINNED** (a fixed `model:` — the artist's actual amp, used verbatim) or
**SEARCHED** (a `candidates:` list of gain-axis or stand-in variants). Other
slots the tool should search (`gain` drives, a `cab`) carry a `candidates:` list
instead of a fixed `model`; the ONE `eq_eight_band_parametric` filter is the slot
the tool TUNES; every other researched block is preserved **verbatim, in place**.
The loop:

1. measures the reference **once** — the honest `fingerprint_match_target`
   (reliable range/mask + per-song `self_floor_pct` BAR) and the 1/3-octave
   LTAS target;
2. **classifies the base chain** — **SEARCH** (the `preamp`/`amp`/`body` core —
   identified **by type**, whether PINNED to a fixed `model:` or given a
   `candidates:` list — plus the `gain` drive(s) + `cab` carrying `candidates:`),
   **TUNE** (the `eq_eight_band_parametric` filter), and **FIXED** pass-through
   (`dynamics`/`wah`/`pitch`/`mod`/`delay`/`reverb`/any non-EQ filter/a
   researched cab — kept verbatim, never dropped, reordered, or re-voiced). A
   **PINNED** core is a single variant used verbatim, but still the
   direct-detected, cabbable, **recorded** core — the number REGULATES it (EQ
   trim, gain-axis when given as candidates, drive, cab, level) but NEVER swaps a
   pinned amp **model**;
3. **gear search** — enumerates the cartesian product over the SEARCH slots'
   candidate lists (the literal `none` keeps that slot **empty**; multiple
   `gain` slots search a drive **stack**). For each combo it renders the **full
   chain** (all FIXED FX present) and scores `weighted_spectral_proximity_pct`
   over the reliable range; the best combo wins. `--cab-model` auto-inserts a
   **`type: cab` PLUGIN block** (a catalog cab model id, e.g.
   `ir_marshall_4x12_v30`) right after the core **only** when the chosen core is
   a **`type: preamp`** (a preamp captures the preamp stage only — no power amp,
   no speaker — so it needs a cab), there is no researched cab already, and a
   `--cab-model` was given. A **`type: amp`** capture is a **FULL amp** — a combo
   (speaker baked in, e.g. `nam_fender_deluxe_reverb_a2`) OR a head+cab mic'd
   (e.g. `nam_marshall_1959_slp_a2`) — and is **never** cabbed; a `type: body`
   (acoustic) and a `:full_rig` are never cabbed either. The decision is a **pure
   catalog-type check** — no render-to-measure, no top-octave heuristic; the
   catalog `type` is authoritative. The cab plugin's manifest carries a
   per-capture `output_gain_db` that the render **applies**, so the cab level is
   right;
4. **EQ refine** on the winner — a **gentle TRIM capped at ±6 dB** (not the old
   ±24); the dead-top and out-of-range bands are **held at 0**. Iterates until
   the report's `within` is true / plateau / iteration cap;
5. **headroom** — sets the EQ `output_db` so the DI peak lands **as hot as
   possible without clipping** (~ −1 dBFS, window [−1.5, −0.5], never reaching
   0 dBFS — "max without clipping"). There is **no limiter**, so the old −7 dBFS
   headroom no longer applies. The output cap is raised to **+30 dB** so the pass
   can compensate a deep cab attenuation (a `type: cab` plugin applies its
   manifest `output_gain_db` ≈ −18 dB; the old +12 cap could not reach the target
   with a cab, so the preset shipped ~6–11 dB too quiet). A clip-guard backs the
   level down if a measured peak ever reaches 0 dBFS.

✅ **Pre-render validate + lint gate.** Before any render, `build_preset` builds
the **offline catalog** (when `--plugins-root` is given) and gates the base chain:
`validate` HARD-FAILS on an unknown model id or an off-axis plugin param (every
candidate is expanded and checked), and `lint` HARD-FAILS on any block-level
policy finding (e.g. an authored `limiter_brickwall`). Either aborts the build
**before** rendering — a hallucinated id can never reach the renderer. Warn-level
lint findings and validation warnings ride into the report under `lint` /
`validation_warnings`. With no `--plugins-root` the gate is skipped (best-effort;
the render-time dropped-block check remains the backstop).

⛔ **The chain ends at the EQ** — `build_preset` adds **NO brickwall limiter and
NO volume block**, and **strips** any `limiter_brickwall` / `volume` present in
the base chain (the predecessor `rebuild_preset.py` wrongly re-enabled a limiter
and applied raw uncapped gains; this supersedes and deletes it).

✅ **Model ids are validated against the engine.** `openrig-render` exits 0 even
when it cannot build a block (it logs `ignoring unsupported or invalid block` /
`unsupported nam model '<id>'` and renders WITHOUT it), so `build_preset`
captures the render output and treats those markers as a **hard failure** — a
typo'd or uninstalled model id can never silently ship a preset missing a block.

The auto-inserted cab is a **`type: cab` plugin block** (`--cab-model <cab_model_id>`):
the render loads the cab plugin and **applies its per-capture `output_gain_db`**, so
the cab comes in at the correct level. A raw `generic_ir` block (`type: ir, model:
generic_ir`, wav in `params.file`) is the **off-catalog escape only** — it bypasses
the catalog `output_gain_db` (a raw wav lands ~18 dB hot relative to the normalised
plugin), so it must **never** stand in for a catalog cab. Use it only for a genuinely
off-catalog IR the user supplies as a wav, authored directly in the base chain (it is
then a FIXED researched cab). It drives the **installed**
`openrig-render` (the headless renderer OpenRig ships next to the GUI, issue
#741) — same engine as the live rig, no `--mcp`, no live runtime. Point
`--render-bin` and `--di` at the install; the binary auto-resolves the bundled
plugins and (on macOS) `libnam_wrapper.dylib` via its bundle, so
`--plugins-root`/`--dyld-lib` are needed only in a dev tree.

The **base-chain YAML** (flat `blocks:` in signal order):

```yaml
id: green_day_basket_case_rhythm
name: Green Day - Basket Case (rhythm)
blocks:
  - type: dynamics            # FIXED pass-through (researched: MXR Dyna Comp)
    model: compressor_studio_clean
    params: { ratio: 4, threshold_db: -18 }
    provenance: unverified    # default knobs, no documented source -> surfaced
  - type: gain                # SEARCH the drive ('none' = try the slot empty)
    candidates: [none, nam_ibanez_ts9_a2, nam_proco_rat_a2]
  - type: amp                 # PINNED core: the artist's actual amp, fixed model
    model: nam_marshall_1959_slp_a2   # used verbatim; the number never swaps it
  - type: filter              # the corrective EQ the tool TUNES (starts flat)
    model: eq_eight_band_parametric
  - type: delay               # FIXED pass-through (time from tempo math)
    model: digital_clean
    params: { time_ms: 343, feedback: 28, mix: 30 }
    provenance: derived       # delay time computed from the song BPM
  - type: reverb              # FIXED pass-through
    model: hall
    params: { mix: 14 }       # no `provenance:` key -> reported as `unverified`
```

### Pinning the artist's actual amp (the CORE is identified by type)

The proximity number is **too weak to discriminate amp MODELS**: on a real John
Mayer "Gravity" run a generic Fender (`nam_fender_deluxe_reverb_a2`, 67.81 %) beat
the artist's actual Dumble (`nam_dumble_ods_john_mayer_a2`, 66.10 %) by ~1.7 % —
inside the noise. So the agent **PINS** the artist's actual amp as a single fixed
`model:`, and the number only **REGULATES** (EQ trim, gain-axis, drive, cab,
level) — it never swaps the model:

```yaml
- type: amp                          # a PINNED core: fixed model, NO candidates
  model: nam_dumble_ods_john_mayer_a2
```

A `type: amp`/`preamp`/`body` block is the CORE **whether pinned or searched** —
it is recognised by its **type**, not by the presence of `candidates:`. A pinned
core is the **full** core: `--cab-model` auto-inserts a cab **only** when the core
is a `type: preamp` (a `type: amp` combo / head+cab and a `type: body` acoustic
are never cabbed), and it is recorded as the chosen amp/core in the report — it
is **never** a FIXED pass-through. To
regulate the pinned amp's drive, give the **same** model as gain-axis candidates
(see below): two `gain` values of one model are two variants, so the number picks
the louder/cleaner without ever choosing a different amp. Reserve a multi-model
`candidates:` list for the genuine **stand-in** case (no capture of the artist's
exact amp exists yet).

### Param-bearing search candidates (`{model, params}`)

A SEARCH slot's `candidates:` entry is EITHER a **bare model-id string** (rendered
at the capture's DEFAULT params) OR a **mapping** carrying per-candidate params:

```yaml
- type: amp
  candidates:
    - nam_marshall_plexi                                    # bare string -> default params
    - { model: nam_marshall_1959_slp_a2, params: { gain: 8 } }
    - { model: nam_marshall_1959_slp_a2, params: { gain: 10 } }   # same model, cranked
```

This lets the search **sweep a capture's own gain/character axis**: many NAM
captures expose a discrete param axis (e.g. the "1959 SLP Dookie-Mod" capture
`nam_marshall_1959_slp_a2` has a `gain` axis `[2, 5, 8, 10]` whose default is
low). Each mapping is a **distinct search variant** — two `gain` values of one
model are two combos — so the EXACT modded-amp capture can be rendered cranked
instead of losing the search to a stand-in amp + drive purely because it was
under-gained at its default. The chosen variant's `params` are applied to that
block both in the render and in the final preset. An optional `full_rig: true`
on a mapping is equivalent to the `:full_rig` string suffix; `none` stays a bare
string sentinel (empty slot). The mechanism is general — it applies to every
SEARCH slot (amp/preamp/body core, gain drives, cab), not just amps.

These searched amp/drive/core params are **core-timbre, chosen by the proximity
number** (the amp's gain IS the timbre) — they are NOT FIXED-FX provenance and do
NOT appear under `param_provenance`. The report records the chosen variant's
params under `amp_params` / `drive_params` / `core_params` (and in each
`gear_history` entry) so the winning axis value is visible.

### Optional `provenance:` helper key (param provenance, Rule B)

Any block MAY carry an optional `provenance:` helper key declaring where its FX
params came from — `sourced` (documented in a rig rundown / interview),
`derived` (computed, e.g. a delay time from the song BPM), or `unverified` (a
sensible default with no source). Like `candidates:`, it is **metadata, stripped
from the emitted preset** — it never becomes a real OpenRig param. An **absent
marker is treated as `unverified`** (conservative: a default presented without a
source must never read as sourced). The marker is for the **FIXED FX params**;
a SEARCH slot (amp/drive chosen by the number) need not carry one.

The report JSON surfaces it under **`param_provenance`**:

```jsonc
"param_provenance": {
  "blocks": [                                   // every FIXED FX block's class
    { "type": "dynamics", "model": "compressor_studio_clean", "provenance": "unverified" },
    { "type": "delay",    "model": "digital_clean",           "provenance": "derived" },
    { "type": "reverb",   "model": "hall",                    "provenance": "unverified" }
  ],
  "unverified": [                               // explicit list to tell the user
    { "type": "dynamics", "model": "compressor_studio_clean" },
    { "type": "reverb",   "model": "hall" }
  ]
}
```

The `unverified` list is the set of FX blocks whose params are a default with no
source — the tone-builder reports these to the user, never presenting a default
as if it were sourced. The proximity number never optimizes a FIXED FX param
(comp/mod/delay/reverb feel is set from source/default, not by the metric).

```bash
# Installed app (macOS) — one tone:
.venv/bin/python scripts/build_preset.py \
  --base-chain /path/to/eval/<song>/chains/rhythm.yaml \
  --ref        /path/to/eval/<song>/refs/rhythm.wav \
  --cab-model  ir_mesa_os_4x12_v30 \
  --render-bin /Applications/OpenRig.app/Contents/MacOS/openrig-render \
  --di         /Applications/OpenRig.app/Contents/Resources/assets/audio/input.wav \
  --out-preset /path/to/eval/<song>/presets/rhythm.yaml \
  --name "Song (rhythm)" --id song-rhythm
# --cab-model is a catalog `type: cab` model id (NOT a wav); the render applies its
# output_gain_db so the level is right. It auto-inserts ONLY when the core is a
# `type: preamp` (a `type: amp`/combo, `type: body`, and `:full_rig` are never
# cabbed). Optional: omit for an amp / full-rig / already-cabbed base chain. (The
# old --cab-ir <wav> is removed — it bypassed the cab normalization.)
# --name/--id default to the base chain's own `name`/`id`.
# Linux install: --render-bin /usr/bin/openrig-render
#                --di         /usr/share/openrig/assets/audio/input.wav

# Dev tree (uncommitted plugins / dylib not yet in a bundle) — add overrides:
#   --render-bin target/release/openrig-render \
#   --di /path/to/OpenRig/assets/audio/input.wav \
#   --plugins-root /path/to/OpenRig-plugins/plugins/source \
#   --dyld-lib /path/to/nam/out/lib   # macOS dev only, for libnam_wrapper.dylib
```

The pure layer (base-chain classification, chain assembly, EQ grid, the ±6 cap +
hold-mask, headroom normalisation, YAML round-trip, type-driven cab
decision, dropped-block detection) and the injected combo-search + EQ-refine
loops are unit-tested in `tests/test_build_preset.py` with the
render/measurement calls injected, so the whole FORM is verified without the
Rust binary or real WAVs.

## Schema

- `fingerprint.json` and `diff.json` — see
  `docs/superpowers/specs/2026-05-26-openrig-tone-analyzer-design.md`.

## Tests

```bash
.venv/bin/pytest -q
```

Fixtures under `tests/fixtures/` are synthesized deterministically by
`tests/fixtures/generate.py` (seeded `numpy.random`); regenerate by running
that script if a library upgrade shifts the synthesis.
