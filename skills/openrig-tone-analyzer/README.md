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
toward the reference, plus `total_gap_db`. The `openrig-tone-builder` Step
6.3 loop applies the gains, re-renders, and repeats until the gap plateaus.

`build_preset.py` is the deterministic **FORM** of the openrig-tone-builder
skill as ONE portable tool: it builds **ONE tone per run** (never a batch),
entirely **offline**, from a surviving reference. The caller researches the
**COMPLETE** rig (compressor, wah, pitch, modulation, delay, reverb, acoustic
body — every researched element) and passes it as a **base-chain YAML**: a flat
`blocks:` list in signal order. Each block the tool should SEARCH carries a
`candidates:` list instead of a fixed `model`; the ONE `eq_eight_band_parametric`
filter is the slot the tool TUNES; every other researched block is preserved
**verbatim, in place**. The loop:

1. measures the reference **once** — the honest `fingerprint_match_target`
   (reliable range/mask + per-song `self_floor_pct` BAR) and the 1/3-octave
   LTAS target;
2. **classifies the base chain** — **SEARCH** (the `preamp`/`amp`/`body` core +
   `gain` drive(s) + `cab`, i.e. the blocks carrying `candidates:`), **TUNE**
   (the `eq_eight_band_parametric` filter), and **FIXED** pass-through
   (`dynamics`/`wah`/`pitch`/`mod`/`delay`/`reverb`/any non-EQ filter/a
   researched cab — kept verbatim, never dropped, reordered, or re-voiced);
3. **gear search** — enumerates the cartesian product over the SEARCH slots'
   candidate lists (the literal `none` keeps that slot **empty**; multiple
   `gain` slots search a drive **stack**). For each combo it renders the **full
   chain** (all FIXED FX present) and scores `weighted_spectral_proximity_pct`
   over the reliable range; the best combo wins. `--cab-ir` auto-inserts a
   `generic_ir` cab right after the amp **only** when the amp renders **direct**
   (head-only, top octave within ~15 dB of the body), there is no researched cab
   already, and the amp is not `:full_rig` (a full-rig capture already has the cab);
4. **EQ refine** on the winner — a **gentle TRIM capped at ±6 dB** (not the old
   ±24); the dead-top and out-of-range bands are **held at 0**. Iterates until
   `within_floor` / plateau / iteration cap;
5. **headroom** — sets the EQ `output_db` so the DI peak lands ~ −7 dBFS.

⛔ **The chain ends at the EQ** — `build_preset` adds **NO brickwall limiter and
NO volume block**, and **strips** any `limiter_brickwall` / `volume` present in
the base chain (the predecessor `rebuild_preset.py` wrongly re-enabled a limiter
and applied raw uncapped gains; this supersedes and deletes it).

✅ **Model ids are validated against the engine.** `openrig-render` exits 0 even
when it cannot build a block (it logs `ignoring unsupported or invalid block` /
`unsupported nam model '<id>'` and renders WITHOUT it), so `build_preset`
captures the render output and treats those markers as a **hard failure** — a
typo'd or uninstalled model id can never silently ship a preset missing a block.

The cab IR loads through the portable `generic_ir` block, whose wav is the
`params.file` key (`type: ir, model: generic_ir`). It drives the **installed**
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
  - type: gain                # SEARCH the drive ('none' = try the slot empty)
    candidates: [none, nam_ibanez_ts9_a2, nam_proco_rat_a2]
  - type: amp                 # SEARCH the amp (':full_rig' candidate => no cab)
    candidates: [nam_marshall_1959_slp_a2, nam_marshall_jcm_800_a2]
  - type: filter              # the corrective EQ the tool TUNES (starts flat)
    model: eq_eight_band_parametric
  - type: delay               # FIXED pass-through (time from tempo math)
    model: digital_clean
    params: { time_ms: 343, feedback: 28, mix: 30 }
  - type: reverb              # FIXED pass-through
    model: hall
    params: { mix: 14 }
```

```bash
# Installed app (macOS) — one tone:
.venv/bin/python scripts/build_preset.py \
  --base-chain /path/to/eval/<song>/chains/rhythm.yaml \
  --ref        /path/to/eval/<song>/refs/rhythm.wav \
  --cab-ir     /path/to/irs/mesa_4x12_v30.wav \
  --render-bin /Applications/OpenRig.app/Contents/MacOS/openrig-render \
  --di         /Applications/OpenRig.app/Contents/Resources/assets/audio/input.wav \
  --out-preset /path/to/eval/<song>/presets/rhythm.yaml \
  --name "Song (rhythm)" --id song-rhythm
# --cab-ir is optional: omit it for a full-rig / already-cabbed base chain.
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
hold-mask, headroom normalisation, YAML round-trip, direct-capture / cab
detection, dropped-block detection) and the injected combo-search + EQ-refine
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
