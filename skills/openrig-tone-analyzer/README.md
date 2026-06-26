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

`rebuild_preset.py` automates that whole loop **offline** for rebuilding a
preset from a surviving reference, without the live rig: it drives
`openrig-render --chain <flat-preset.yaml>` against the bundled DI and
`eq_match.py` against the reference, sets the 8-band EQ to the absolute gains
returned each pass, and repeats until `within_floor` (or a plateau / cap),
then gain-normalises the EQ and runs a headroom pass to land the DI peak
~ -7 dBFS. The render binary, DI, and plugins root are passed as arguments
(they live in the OpenRig app / OpenRig-plugins), so the script stays
portable:

```bash
.venv/bin/python scripts/rebuild_preset.py \
  --ref   /path/to/eval/<song>/refs/rhythm.wav \
  --base  /path/to/eval/<song>/presets/rhythm-base.yaml \
  --out-dir /path/to/eval/<song> --role rhythm \
  --render-bin /path/to/openrig-render \
  --di /path/to/OpenRig/assets/audio/input.wav \
  --plugins-root /path/to/OpenRig-plugins/plugins/source \
  --dyld-lib /path/to/nam/out/lib   # macOS only, for libnam_wrapper.dylib
```

The pure layer (grid setup, absolute-gain application, headroom
normalisation, loop control) is unit-tested in
`tests/test_rebuild_preset.py` with the render/eq_match calls injected, so
the loop logic is verified without the Rust binary.

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
