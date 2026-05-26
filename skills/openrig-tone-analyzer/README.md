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
```

Both commands print the resolved output directory on their last line. Open
the PNGs to inspect; feed the JSON to your downstream consumer.

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
