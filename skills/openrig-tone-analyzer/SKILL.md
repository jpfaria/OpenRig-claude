---
name: openrig-tone-analyzer
description: |
  Use when the user asks to analyze a guitar audio file ("analisa esse áudio",
  "compara o som que saiu com a referência", "validar o timbre X", "fingerprint
  do som", "analyze this track", "compare these two takes"). Runs as a pure
  function: in = WAV files, out = JSON + spectrogram PNGs on disk. Handles
  multi-minute tracks (returns per-section fingerprints) and short renders
  alike. Does NOT call MCP, does NOT modify the rig, does NOT touch any
  OpenRig project. The openrig-tone-builder skill orchestrates the validation
  loop using this skill's outputs.
---

# openrig-tone-analyzer

Pure-function audio analyzer + A/B comparator. The orchestration loop in
`openrig-tone-builder` consumes the JSON output to adjust the chain
deterministically. This skill itself never invokes MCP tools or
`openrig --render`.

## Iron rules

1. **No MCP calls.** Not "to be helpful," not "just this once." Every block
   touch is the orchestrator's job.
2. **No persistence outside `--out-dir`.** No `$HOME` caches, no project
   writes, no stdout chatter beyond a single line announcing the out-dir.
3. **No name claims from audio.** "It sounds like a Mesa Rectifier" comes
   from `openrig-tone-builder`'s web research, not from this skill.
   `gain_character` is a four-bucket enum, not a model name.
3b. **No playing-technique claims.** Never label a take "palm-muted",
   "gallop", "fingerpicked", "sweep-picked", "tremolo-picked" — the
   fingerprint does not measure technique, and a song's/artist's
   reputation is not evidence. Describe only what the analyzer reports
   (`dynamics_profile`, crest factor, transient density) or what is
   directly visible in the spectrogram. If you infer from a signal, make
   the chain explicit ("crest 15 dB ⇒ gaps between hits"), never jump to
   a named technique. (`openrig-tone-builder` carries the full rule.)
4. **Heuristic section labels only.** Sections are tagged with
   `tone_profile + dynamics_profile + presence`. Never `verse`, `chorus`,
   `bridge`, `solo` as labels — that requires music-theoretic structure
   this analyzer doesn't measure.
5. **`match_score` is a technical distance.** When surfacing it in chat,
   say so explicitly — e.g. "technically 0.71 — this is a measured
   distance, not a measure of how close it sounds to a human ear."
   *(Render in the user's language at runtime; this English example
   documents the framing, not the literal words.)*
6. **English in code, comments, JSON, summaries.** Chat with the user stays
   in their language; everything persisted to disk is English.

## Prerequisites

```bash
which ffmpeg                            # required for non-PCM decode fallback
python3 --version                       # must be ≥ 3.10
```

If either fails, stop and tell the user what to install.

## First-run bootstrap

```bash
cd skills/openrig-tone-analyzer
./bootstrap.sh                          # idempotent; <1 s on subsequent runs
```

The venv at `.venv/` is gitignored. The bootstrap stamps the requirements
hash so it knows when to reinstall.

## Workflow

1. **Decide the mode** from how many WAV files the user gave you:
   - 1 file → **analyze**.
   - 2 files → **compare** (first = reference, second = wet/rendered).
2. **Run it:**
   ```bash
   .venv/bin/python scripts/analyze.py <input.wav> [--out-dir DIR]
   # or
   .venv/bin/python scripts/compare.py <ref.wav> <wet.wav> [--out-dir DIR] [--ref-section IDX] [--wet-section IDX]
   ```
   The script prints the resolved out-dir on its last line.

   **Pick `--out-dir` from MCP, not from `/tmp`.** OpenRig #582 exposes
   the user's evaluations directory via the `openrig://paths` resource
   (`evaluations_path` field — already an absolute, OS-correct path).
   The ORCHESTRATOR (`openrig-tone-builder`) reads it via MCP and
   passes it down to this script as `--out-dir <evaluations_path>/<ts>/`,
   keeping this analyzer's iron rule 1 intact (no MCP calls from
   here). When no caller passes `--out-dir`, the script falls back to
   `/tmp/openrig-analyzer/<unix_ts>/` so a one-shot manual run still
   works.

   `--wet-section` accepts an int index (pin a specific wet section) or the
   literal `auto` (opt into the smarter auto-pick that skips silent background
   sections). Omitted = section 0 (backward-compatible default).
3. **Read the PNGs as visual evidence.** Use the Read tool on each
   `spec_*.png` or `ab_spec.png`. They're real images and you can see them.
4. **Summarize in chat:**
   - **analyze**: one short paragraph per section — gain character,
     dynamics, presence, and any notable time-FX (delay/reverb estimates).
     Mention the `spec_global.png` for the full overview.
   - **compare**: lead with `match_score` (and the caveat from iron rule 5),
     then the matched section ID + reason, then the top 2-3 recommendations
     as one sentence each.
5. **Hand off to the orchestrator** if the user asked for a tone-builder
   loop — that's `openrig-tone-builder`'s job. This skill stops at the
   diff.

## Long files

Files > 600 s are rejected with `"file too long (max 600 s): <path>, got X s"`.
If the user has a long track, ask them to trim it first (e.g., to the chorus
or to a specific minute range) before re-running.

## Anti-patterns

- ❌ Calling MCP tools because "it would be faster to also adjust the chain."
- ❌ Claiming `match_score = 0.95` means "sounds identical to a human." It's
  a weighted technical distance.
- ❌ Inventing music-theoretic section names. Use the tag triple as-is.
- ❌ Writing to anywhere outside `--out-dir`. No exceptions.
- ❌ Naming the amp/pedal model from audio alone.
- ❌ Computing or guessing `output_gain_db` for any block — not this skill's
  concern.

## Output schemas

See `docs/superpowers/specs/2026-05-26-openrig-tone-analyzer-design.md`.
Short form:

- `fingerprint.json` v2: `source`, `global`, `sections[]` (each with
  `loudness`, `spectrum`, `distortion`, `time_fx`, `labels`).
- `analysis.pdf`: human-readable report emitted by `analyze.py` alongside
  the JSON + PNGs. Multi-page, landscape letter: (1) cover with source
  metadata + global LUFS/peak/stereo, (2) full-track mel spectrogram with
  section boundaries, (3+) one page per section showing labels / loudness
  / spectrum / distortion / time_fx + band-energy table + the section's
  mel spectrogram. Hand this to the user when they ask for the analysis
  in a single document. Filename is fixed (`analysis.pdf`) so callers
  can find it deterministically; lives in the same `--out-dir` as the
  JSON.
- `diff.json` v2: `reference.matched_section_id`, `rendered`, `match_score`,
  `delta.*`, `recommendations[]` (priority-sorted, each with `target`,
  `action`, `rationale`), `converged`.

## When something looks off

If section counts seem clearly wrong on a real track (e.g., a riff is split
into 8 sections, or a 4-minute song is reported as 1 section), say so to
the user. The segmentation `k = ceil(duration_s / 30)` heuristic is
deliberately conservative — bug reports from real usage are how it gets
better.

When the wet is a render through a DI that has a silent intro (a common
case with the bundled `input.wav`), the wet's `section_0` will be
silence — auto-comparison against that biases the diff. Pin
`--wet-section IDX` to the section that carries the target tone
character (run `analyze.py wet.wav` first to see the sections).
