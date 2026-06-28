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
entirely **offline**, from a surviving reference. The loop:

1. measures the reference **once** — the honest `fingerprint_match_target`
   (reliable range/mask + per-song `self_floor_pct` BAR) and the 1/3-octave
   LTAS target;
2. **gear search** — for each amp × drive candidate (the literal `none` token
   keeps amp-only in the search), plus a **cab IR** *only* when the amp capture
   is **direct** (head-only, top octave within ~15 dB of the body), it builds
   the chain `drive(s) → amp → cab → EQ(flat)`, renders, and scores
   `weighted_spectral_proximity_pct` over the reliable range; the best combo
   wins. A `full_rig` capture already contains the cab and never gets one;
3. **EQ refine** on the winner — a **gentle TRIM capped at ±6 dB** (not the old
   ±24); the dead-top and out-of-range bands are **held at 0**. Iterates until
   `within_floor` / plateau / iteration cap;
4. **headroom** — sets the EQ `output_db` so the DI peak lands ~ −7 dBFS.

⛔ **The chain ends at the EQ** — `build_preset` adds **NO brickwall limiter and
NO volume block** (the predecessor `rebuild_preset.py` wrongly re-enabled a
limiter and applied raw uncapped gains; this supersedes and deletes it).

The cab IR loads through the portable `generic_ir` block, whose wav is the
`params.file` key (`type: ir, model: generic_ir`). It drives the **installed**
`openrig-render` (the headless renderer OpenRig ships next to the GUI, issue
#741) — same engine as the live rig, no `--mcp`, no live runtime. Point
`--render-bin` and `--di` at the install; the binary auto-resolves the bundled
plugins and (on macOS) `libnam_wrapper.dylib` via its bundle, so
`--plugins-root`/`--dyld-lib` are needed only in a dev tree:

```bash
# Installed app (macOS) — one tone:
.venv/bin/python scripts/build_preset.py \
  --ref     /path/to/eval/<song>/refs/rhythm.wav \
  --amps    nam_jcm800_a1,nam_5150_a1 \
  --drives  nam_tubescreamer_a1,none \
  --cab-ir  /path/to/irs/mesa_4x12_v30.wav \
  --render-bin /Applications/OpenRig.app/Contents/MacOS/openrig-render \
  --di         /Applications/OpenRig.app/Contents/Resources/assets/audio/input.wav \
  --out-preset /path/to/eval/<song>/presets/rhythm.yaml \
  --name "Song (rhythm)" --id song-rhythm
# An amp token may carry ':full_rig' (e.g. nam_jmp_1_full_rig:full_rig) to
# declare a full-rig capture, which skips the cab unconditionally.
# Linux install: --render-bin /usr/bin/openrig-render
#                --di         /usr/share/openrig/assets/audio/input.wav

# Dev tree (uncommitted plugins / dylib not yet in a bundle) — add overrides:
#   --render-bin target/release/openrig-render \
#   --di /path/to/OpenRig/assets/audio/input.wav \
#   --plugins-root /path/to/OpenRig-plugins/plugins/source \
#   --dyld-lib /path/to/nam/out/lib   # macOS dev only, for libnam_wrapper.dylib
```

The pure layer (chain assembly, EQ grid, the ±6 cap + hold-mask, headroom
normalisation, YAML round-trip, direct-capture / cab detection) and the
injected gear-search + EQ-refine loops are unit-tested in
`tests/test_build_preset.py` with the render/measurement calls injected, so the
whole FORM is verified without the Rust binary or real WAVs.

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
