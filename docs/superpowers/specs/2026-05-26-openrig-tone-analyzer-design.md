# openrig-tone-analyzer — design spec

**Repo:** `OpenRig-claude` (plugin `openrig`)
**New artifact:** `skills/openrig-tone-analyzer/`
**Issue:** [#8](https://github.com/jpfaria/OpenRig-claude/issues/8)
**Status:** approved 2026-05-26; ready for implementation plan.

## Problem

The `openrig-tone-builder` validation loop has no measurement step. The user
listens to a rendered chain and reports "wrong," but the builder can't see
*which block*, *which parameter*, *by how much*. Without a deterministic diff
between the reference recording and the chain's wet output, the loop cannot
self-correct — it just retries blind.

This skill adds the measurement half. Pure function: WAVs in, JSON + PNGs out.
No MCP, no `openrig --render`, no orchestration. The tone-builder consumes
this output in a separate follow-up.

## Scope (v1)

**In:**

- Two modes: `analyze <wav>` and `compare <ref.wav> <wet.wav>`.
- **Multi-section fingerprints.** Real guitar tracks have intro / verse /
  chorus / solo / silence — single-fingerprint-per-track dilutes the tone
  signal. `fingerprint.json` returns an array of section fingerprints with
  structural boundaries detected from spectral features.
- Per-section descriptors: loudness, spectrum, distortion, time-fx estimates.
- Global descriptors: LUFS-integrated, stereo, duration.
- `compare`: auto-picks the ref section that best matches the wet's profile
  and diffs against that section. Override via `--ref-section <idx>`.
- Spectrogram PNGs: one global view with section boundaries overlaid, one
  per-section focused view.
- Recommendations array in `diff.json` consumable by the tone-builder
  orchestrator.

**Out (explicit non-goals):**

- Naming exact amp/pedal models from audio — that's the tone-builder's web
  research.
- Real-time analysis. Files only.
- A GUI. JSON + PNGs are the contract.
- Calling MCP tools or `openrig --render`. The orchestrator does that.
- Multi-take aggregation, cross-song libraries, genre classification.
- Music-theoretic labels (verse/chorus). Section labels are heuristic tags
  on tone/dynamics/presence only.
- Files longer than 10 minutes. Aborts with explicit message.

## Architecture

```
skills/openrig-tone-analyzer/
├── SKILL.md                  # invocation contract + workflow
├── README.md                 # human-facing notes
├── requirements.txt          # pinned exact versions
├── bootstrap.sh              # idempotent venv setup
├── .gitignore                # ignores .venv/, __pycache__/, *.pyc, /tmp output
├── scripts/
│   ├── analyze.py            # IN: wav | OUT: fingerprint.json + spec_*.png
│   ├── compare.py            # IN: ref.wav wet.wav | OUT: diff.json + ab_spec.png
│   └── _common.py            # shared spectral + segmentation helpers
└── tests/
    ├── fixtures/
    │   ├── generate.py       # deterministic synth (seeded numpy)
    │   ├── clean_di.wav
    │   ├── distorted_di.wav
    │   ├── reverb_tail.wav
    │   ├── delayed_echo.wav
    │   └── multi_section.wav # 3 sections: clean → high-gain → clean tail
    └── test_*.py
```

The deliverable is **runnable Python**, plus a Markdown SKILL.md that tells
Claude when and how to invoke it. The Python is the implementation; the skill
is the dispatcher.

## Tool stack

- **Python ≥ 3.10** (the user's macOS already has 3.11+).
- **`ffmpeg`** at PATH for non-PCM decoding fallback (`brew install ffmpeg`).
- **Pinned libraries** in `requirements.txt`:
  ```
  numpy==2.1.3
  scipy==1.14.1
  librosa==0.10.2.post1
  soundfile==0.12.1
  matplotlib==3.9.2
  pyloudnorm==0.1.1
  ```
  If a wheel mismatch surfaces during implementation (macOS arm64 / Linux
  x86_64 CI), pin down a closest compatible set and document the override in
  the PR. Determinism tests will catch silent drift.
- **Local venv** at `skills/openrig-tone-analyzer/.venv/`, created by
  `bootstrap.sh` on first run. Venv is gitignored.

No Rust dep, no OpenRig dep, no network at runtime.

## JSON contracts (authoritative)

### `fingerprint.json` v2

```json
{
  "schema_version": 2,
  "source": {
    "path": "/abs/path/to/ref.wav",
    "sha256": "deadbeef...",
    "sample_rate_hz": 48000,
    "channels": 2,
    "duration_s": 218.42
  },
  "global": {
    "lufs_integrated": -10.1,
    "peak_db": -0.7,
    "stereo": {
      "is_stereo": true,
      "ms_balance_ratio": 0.82,
      "lr_correlation": 0.91
    }
  },
  "sections": [
    {
      "id": "section_0",
      "start_s": 0.00,
      "end_s": 12.42,
      "labels": {
        "tone_profile": "clean",
        "dynamics_profile": "sparse",
        "presence": "background"
      },
      "loudness": {
        "rms_db": -22.4,
        "peak_db": -8.1,
        "crest_factor_db": 14.3
      },
      "spectrum": {
        "bands_hz": [80, 160, 320, 640, 1280, 2560, 5120, 10240],
        "band_energy_db": [-28.1, -24.3, -20.8, -18.0, -17.2, -19.5, -23.9, -31.4],
        "spectral_centroid_hz": 1420.0,
        "spectral_rolloff_hz_85pct": 3200.0,
        "spectral_flatness": 0.22
      },
      "distortion": {
        "thd_estimate_pct": 1.8,
        "odd_to_even_harmonic_ratio_db": 1.2,
        "gain_character": "clean",
        "gain_character_confidence": 0.91
      },
      "time_fx": {
        "reverb_rt60_s": 0.8,
        "reverb_rt60_confidence": 0.62,
        "delay_present": false,
        "delay_time_ms_estimate": null,
        "delay_feedback_estimate_pct": null,
        "modulation_present": false,
        "modulation_rate_hz": null,
        "modulation_depth_estimate": null
      }
    },
    {
      "id": "section_1",
      "start_s": 12.42,
      "end_s": 47.18,
      "labels": {
        "tone_profile": "high_gain",
        "dynamics_profile": "rhythmic",
        "presence": "lead"
      },
      "loudness": { "...": "..." },
      "spectrum": { "...": "..." },
      "distortion": { "...": "..." },
      "time_fx": { "...": "..." }
    }
  ]
}
```

**All numeric values rounded to 4 decimal places** for byte-identical
determinism. All metrics are **advisory** — best-effort estimates, not ground
truth.

#### Per-section descriptor details

- **`loudness.rms_db`, `peak_db`, `crest_factor_db`** — computed on the
  section's samples only.
- **`spectrum.band_energy_db`** — 8-band log-spaced (80 → 10240 Hz), median
  across STFT frames in the section (median, not mean — robust to outliers
  like pinch harmonics or string scrapes).
- **`spectrum.spectral_centroid_hz`** — median across frames.
- **`distortion.thd_estimate_pct`** — measured on a clip-detection-style
  proxy: ratio of energy at harmonic multiples to fundamental energy, picked
  on the section's most stable tonal frame (lowest centroid variance).
- **`distortion.gain_character`** — `clean | crunch | distortion | high_gain`.
  Decision rules (documented in `_common.py`, pinned in tests):
  - `clean`     — THD < 3%
  - `crunch`    — 3% ≤ THD < 10%
  - `distortion`— 10% ≤ THD < 25%
  - `high_gain` — THD ≥ 25%, OR (THD ≥ 15% AND band[2560] − band[640] > 6 dB)
  Confidence = distance from nearest boundary in normalized units, clipped to
  `[0, 1]`. Crest factor was considered but dropped as a gate — sustained
  clean playing has low crest by default and shouldn't be misclassified as
  crunch.
- **`time_fx.reverb_rt60_s`** — estimated from the decay tail of detected
  note-offs within the section. If no clean decay is detectable, RT60 is set
  to null and confidence to 0.0.
- **`time_fx.delay_present`** — autocorrelation peak above 60 ms with
  prominence > 0.3.

#### Section labels (heuristic)

Labels are **tags**, not names. The orchestrator filters by tag combination.

- **`tone_profile`** — same enum as `gain_character`.
- **`dynamics_profile`**:
  - `sparse`    — onset rate < 1.0/s **or** RMS variance > 8 dB
  - `rhythmic`  — onset rate ≥ 2.5/s and RMS variance ≤ 8 dB
  - `sustained` — onset rate < 2.5/s and crest_factor_db < 10
- **`presence`** (RMS relative to track's loudest section):
  - `lead`       — within −3 dB of the loudest section
  - `rhythm`     — −3 to −10 dB
  - `background` — below −10 dB

#### Section detection algorithm

1. Compute frame-level features at 1 s hop, 2 s window: RMS, spectral
   centroid, spectral flatness, onset strength envelope.
2. Build a self-similarity matrix over those features (cosine distance).
3. Apply `librosa.segment.agglomerative` with target `k = ceil(duration_s / 30)`,
   clamped to `[2, 12]`.
4. Enforce a minimum section length of **8 s** by merging any shorter section
   into the more-similar neighbor.
5. Recompute features per section on the actual samples (not the frame
   summaries) so the values are honest to the section content.

For a track ≤ 8 s, return a single section spanning the whole file (skip
segmentation).

### `diff.json` v2

```json
{
  "schema_version": 2,
  "reference": {
    "fingerprint_sha256": "abc123...",
    "matched_section_id": "section_2",
    "matched_section_reason": "best tone_profile+dynamics_profile match to wet"
  },
  "rendered": {
    "fingerprint_sha256": "def456...",
    "section_id": "section_0"
  },
  "match_score": 0.71,
  "delta": {
    "rms_db":               { "wet_minus_ref": -2.1, "verdict": "wet quieter" },
    "spectral_centroid_hz": { "wet_minus_ref": -340, "verdict": "wet darker" },
    "band_energy_db": [
      { "band_hz":   80, "delta_db":  1.2 },
      { "band_hz":  160, "delta_db":  0.8 },
      { "band_hz":  320, "delta_db": -0.3 },
      { "band_hz":  640, "delta_db": -1.4 },
      { "band_hz": 1280, "delta_db": -2.9 },
      { "band_hz": 2560, "delta_db": -3.8 },
      { "band_hz": 5120, "delta_db": -2.1 },
      { "band_hz":10240, "delta_db":  0.4 }
    ],
    "thd_estimate_pct":     { "wet_minus_ref": -4.2, "verdict": "wet less distorted" },
    "reverb_rt60_s":        { "wet_minus_ref": -0.6, "verdict": "wet shorter tail" },
    "delay_present":        { "ref": true,  "wet": false, "verdict": "wet missing delay" },
    "modulation_present":   { "ref": false, "wet": false, "verdict": "ok" },
    "alignment_confidence": 0.92
  },
  "recommendations": [
    { "priority": 1, "target": "amp",
      "action": "increase gain by ~15%",
      "rationale": "THD lower by 4.2 pts and 2-5 kHz energy lower by ~3 dB — wet is cleaner than ref" },
    { "priority": 2, "target": "eq_eight_band_parametric",
      "action": "boost 2 kHz band by +3 dB (Q ~1.0)",
      "rationale": "mid-range energy deficit at 1.28–2.56 kHz" },
    { "priority": 3, "target": "delay",
      "action": "enable delay block, time ~380 ms, feedback ~25%, mix ~12%",
      "rationale": "reference shows periodic echo at 380 ms; wet has none" },
    { "priority": 4, "target": "reverb",
      "action": "increase room_size to extend tail by ~0.6 s",
      "rationale": "RT60 deficit of 0.6 s" }
  ],
  "converged": false,
  "convergence_threshold": { "match_score_min": 0.85, "max_abs_band_delta_db": 2.0 }
}
```

#### Section auto-pick (`compare`)

When the user runs `compare ref.wav wet.wav` without `--ref-section`:

1. Analyze both inputs. The wet is usually short (one `openrig --render`
   take) and yields 1 section; the ref is the full track and yields N.
2. For each ref section, compute a similarity score against the wet's
   primary section using the same metric pieces as `match_score` but without
   the time-fx terms (those are noisier). Pick the highest-scoring ref
   section.
3. Record the choice and reason in `reference.matched_section_*`.
4. If wet has > 1 section, do greedy section-to-section matching and emit
   `diff.json.sections[]` instead of a single delta — schema reserves this
   array for the future, **v2 emits the single-section shape** because the
   typical orchestrator wet is a single take.

#### `match_score` weighting

A single 0..1 number combining normalized deltas. Higher is closer.

```
match_score = 0.40 * band_energy_term
            + 0.15 * centroid_term
            + 0.25 * thd_term
            + 0.10 * rt60_term
            + 0.10 * delay_presence_term
```

Each term is `1 - clip(normalized_delta, 0, 1)`. Normalization constants:

- band_energy: RMS of band deltas in dB, normalized by 12 dB
- centroid: |delta_hz| normalized by 1500 Hz
- thd: |delta_pct| normalized by 20 pp
- rt60: |delta_s| normalized by 2.0 s
- delay_presence: 1.0 if both agree, 0.0 if they disagree

These are perceptually motivated (mids weigh most; THD matters more than
centroid for distortion). **Weights are pinned in tests** — changing them
requires updating the pinned values with a one-line justification.

#### Time alignment

`wet.wav` from `openrig --render` typically has a trailing silent tail; ref
does not. Latencies differ. Approach:

1. Cross-correlate first ~2 s of both signals (mono mixdown, RMS-normalized).
2. If peak normalized cross-correlation > 0.6, use that lag.
3. Else fall back to `librosa.onset.onset_detect` on both, pair earliest
   onsets, use their offset.
4. If both fail, set `alignment_confidence` < 0.3 and skip time-domain
   metrics that need alignment (delay-time estimate); spectrum/loudness
   metrics still computable.

### Spectrogram PNGs

- **`spec_global.png`** — Mel spectrogram of the whole file, log-frequency Y,
  dB color scale, time in seconds. Vertical dashed lines at every section
  boundary; section IDs labeled along the top.
- **`spec_section_<N>.png`** — Per-section, 4 s window centered on the
  section's loudest 4 s subwindow. Same axes, same color scale.
- **`ab_spec.png`** (compare only) — Side-by-side: ref's matched section on
  the left, wet on the right. Shared color scale.

All PNGs ≥ 1024×512, with axis labels, color bar, title showing source
filename + section id.

## Modes

### `analyze <input.wav> [--out-dir DIR]`

- Decode via `soundfile`. On failure (non-PCM, exotic codec), fall back to
  invoking `ffmpeg` to transcode to a temp PCM WAV.
- Reject files > 10 minutes with `"file too long (max 600 s)"`.
- Run section detection + per-section descriptors + global descriptors.
- Emit `fingerprint.json`, `spec_global.png`, `spec_section_<N>.png` for
  each section.
- Default `--out-dir`: `/tmp/openrig-analyzer/<unix_ts>/`. Skill prints the
  resolved path so Claude can read the PNGs.

### `compare <ref.wav> <wet.wav> [--out-dir DIR] [--ref-section IDX]`

- Internally run `analyze` on both (cache by `sha256(wav)` for cheap repeat
  comparisons).
- Time-align as described above.
- Auto-pick ref section unless `--ref-section` is passed.
- Emit `diff.json`, `ab_spec.png`.

## SKILL.md shape

```yaml
---
name: openrig-tone-analyzer
description: |
  Use when the user asks to analyze a guitar audio file ("analisa esse
  áudio", "compara o som que saiu com a referência", "validar o timbre X",
  "fingerprint do som"). Runs as a pure function: in = wav files, out =
  JSON + spectrogram PNGs on disk. Does NOT call MCP, does NOT modify the
  rig. Handles multi-minute tracks (returns per-section fingerprints) and
  short renders alike. The openrig-tone-builder skill orchestrates the
  validation loop using this skill's outputs.
---
```

Body covers: prerequisite check, bootstrap, mode dispatch, reading PNGs as
visual evidence, surfacing the top recommendations in chat, and the
anti-patterns list (no MCP calls, no name-claims from audio, no persistence
outside out-dir).

## Acceptance criteria (TDD)

Write failing tests first. Each criterion below maps to one or more tests
under `tests/`.

- [ ] `bootstrap.sh` is idempotent: first run < 60 s, second run < 2 s wall.
- [ ] `analyze` on `clean_di.wav` produces `fingerprint.json` v2 with all
      fields non-null, non-NaN, types and ranges valid.
- [ ] `analyze` on the same WAV twice produces byte-identical
      `fingerprint.json`. All randomness seeded; floats rounded to 4
      decimals.
- [ ] `analyze` on `multi_section.wav` (3 synthesized sections: clean →
      high_gain → clean tail) yields **exactly 3 sections** with the
      expected `tone_profile` labels (`clean`, `high_gain`, `clean`).
- [ ] `compare` on identical WAVs yields `match_score ≥ 0.99` and empty
      `recommendations`.
- [ ] `compare` on `clean_di.wav` vs `distorted_di.wav` yields
      `match_score < 0.5` and at least one recommendation targeting `amp`
      with a gain-related action.
- [ ] `compare` correctly time-aligns when wet has a trailing silent tail
      (fixture: pad clean with 1.5 s of silence).
- [ ] `compare` flags `delay_present: ref=true, wet=false` on
      `delayed_echo.wav` (ref) vs `clean_di.wav` (wet).
- [ ] `compare` flags missing reverb tail (RT60 delta > 0.5 s) on
      `reverb_tail.wav` vs `clean_di.wav`.
- [ ] `compare` on a long multi-section ref vs a short wet picks the ref
      section whose `tone_profile` matches the wet's, recorded in
      `reference.matched_section_id`.
- [ ] `--ref-section 1` overrides auto-pick.
- [ ] **No network calls** during analyze or compare. Test:
      `socket.socket` monkey-patched to raise on connect; both modes succeed.
- [ ] Spectrogram PNGs render ≥ 1024×512 with axis labels, color bar,
      log-frequency Y, time-in-seconds X. Section boundaries visible on
      `spec_global.png`.
- [ ] Files > 600 s rejected with explicit message before any heavy work.
- [ ] Full fixture test suite runs in < 90 s on macOS arm64.
- [ ] `.venv/`, `__pycache__/`, `*.pyc` excluded by `.gitignore`.

## Determinism strategy

- Set `numpy.random.seed(42)` and `random.seed(42)` at the top of every
  script entry point.
- Pin `librosa` random-state args (`random_state=42`) on any call that
  accepts one (e.g., agglomerative segmentation if it has stochastic init).
- Round all floats in JSON output to 4 decimal places via a shared
  `_common.round_for_json()` helper.
- Hash every fixture's `fingerprint.json` and pin the hash in
  `tests/test_determinism.py`. Any code change that perturbs the hash must
  update it with a one-line justification in the PR.

## Anti-patterns (encoded in SKILL.md)

- ❌ Claiming match_score reflects "how it sounds to a human." It's a
  weighted technical distance. Surface the caveat when relevant.
- ❌ Claiming to identify exact amp/pedal models from audio.
- ❌ Persisting output anywhere outside the configured `--out-dir`.
- ❌ Calling MCP tools or `openrig --render` "to be helpful." Out of scope.
- ❌ Returning a music-theoretic section name (`verse`, `chorus`). Use the
  heuristic label tags.
- ❌ Computing or assuming `output_gain_db` for any block.

## Error handling

All errors abort before any heavy work. Single message per failure class.

| condition | message |
|---|---|
| file not found | `"file not found: <path>"` |
| file > 600 s | `"file too long (max 600 s): <path>, got <X> s"` |
| unreadable audio | `"could not decode audio: <path>"` (after ffmpeg fallback) |
| missing dep on first run | `"run ./bootstrap.sh first"` (if `.venv` missing) |
| `--ref-section` out of range | `"--ref-section <N> out of range (have 0..<max>)"` |

## Verification plan

End-to-end on committed fixtures plus one manual run on a user-provided
real guitar track:

1. **Synthesized happy paths** — all acceptance criteria above run
   automatically via `pytest`.
2. **Real-track smoke** — user provides one full guitar track. Run
   `analyze` on it, inspect the section count, labels, `spec_global.png`,
   and a couple of `spec_section_*.png` together. Adjust the segmentation
   `k` heuristic only if the result is obviously wrong (e.g., a 4-section
   song reported as 1 section, or a 1-section riff reported as 8).
3. **Compare smoke** (deferred until OpenRig#552 ships the render CLI) —
   take a `--render` output of any chain and compare against the real
   track; sanity-check the picked ref section and the top recommendations.

## Sequencing

1. OpenRig#552 (offline render CLI) — separate repo, separate timeline.
2. **This skill** — single PR, this issue, this repo.
3. Follow-up: teach `openrig-tone-builder` to invoke
   `analyzer.compare(ref, wet)` in a loop, apply top recommendations via
   MCP, iterate until `match_score ≥ 0.85` with `max |band_delta| ≤ 2 dB`.

## Constraints

- **English** everywhere in docs, commits, code comments, manifest output,
  user-facing summaries. Skill `description` may include pt-BR trigger
  phrases (the user works in pt-BR), but no other Portuguese in artifacts.
- **No** Rust / OpenRig / MCP dependency at runtime.
- **No** network at runtime.
- **Pinned** library versions.
- macOS arm64 + Linux x86_64. Windows is best-effort; bootstrap may need
  adjustment.
- Pure function: never persist state outside `--out-dir`. No `$HOME` caches,
  no stdout beyond a one-line resolved-out-dir summary.
