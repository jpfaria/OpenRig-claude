# openrig-tone-analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Tasks use checkbox (`- [ ]`) syntax.

**Goal:** Ship `skills/openrig-tone-analyzer/` — a pure-function audio analyzer + A/B comparator skill that emits structured JSON + spectrogram PNGs from guitar audio files. Multi-section fingerprints for full-length tracks; auto-section-pick in compare mode.

**Architecture:** Python + Markdown. The skill dispatcher is `SKILL.md`; the implementation is two scripts (`analyze.py`, `compare.py`) sharing `_common.py`. Tests under `tests/`, fixtures synthesized deterministically by `tests/fixtures/generate.py`. Local venv via `bootstrap.sh`. No code-level coupling to OpenRig / MCP.

**Spec:** `docs/superpowers/specs/2026-05-26-openrig-tone-analyzer-design.md`

**Out of scope here** (explicit, do NOT do):
- Teaching `openrig-tone-builder` to call this analyzer in a loop — follow-up PR.
- The `openrig --render` CLI itself — lives in OpenRig#552.
- Bumping `plugin.json` manually — `auto-bump.yml` handles it after merge.
- Windows support — best-effort, no testing.

---

## File structure

| Path | Action | Responsibility |
|---|---|---|
| `skills/openrig-tone-analyzer/SKILL.md` | Create | Invocation contract + workflow + anti-patterns. |
| `skills/openrig-tone-analyzer/README.md` | Create | Human-facing notes. |
| `skills/openrig-tone-analyzer/requirements.txt` | Create | Pinned exact versions. |
| `skills/openrig-tone-analyzer/bootstrap.sh` | Create | Idempotent venv setup. |
| `skills/openrig-tone-analyzer/.gitignore` | Create | `.venv/`, `__pycache__/`, `*.pyc`. |
| `skills/openrig-tone-analyzer/scripts/_common.py` | Create | Shared spectral + segmentation helpers. |
| `skills/openrig-tone-analyzer/scripts/analyze.py` | Create | Mode entry: analyze. |
| `skills/openrig-tone-analyzer/scripts/compare.py` | Create | Mode entry: compare. |
| `skills/openrig-tone-analyzer/tests/fixtures/generate.py` | Create | Deterministic WAV synth. |
| `skills/openrig-tone-analyzer/tests/fixtures/*.wav` | Generate + commit | Pinned test fixtures. |
| `skills/openrig-tone-analyzer/tests/test_common.py` | Create | Unit tests for helpers. |
| `skills/openrig-tone-analyzer/tests/test_analyze.py` | Create | Integration tests for analyze mode. |
| `skills/openrig-tone-analyzer/tests/test_compare.py` | Create | Integration tests for compare mode. |
| `skills/openrig-tone-analyzer/tests/test_determinism.py` | Create | Pinned-hash tests. |
| `skills/openrig-tone-analyzer/tests/test_no_network.py` | Create | socket monkey-patch test. |

---

## Task 1: Scaffold skill directory + bootstrap

**Files:** `SKILL.md`, `README.md`, `requirements.txt`, `bootstrap.sh`, `.gitignore`.

- [ ] **1.1** Create `requirements.txt` with pinned versions from the spec:
  ```
  numpy==2.1.3
  scipy==1.14.1
  librosa==0.10.2.post1
  soundfile==0.12.1
  matplotlib==3.9.2
  pyloudnorm==0.1.1
  pytest==8.3.3
  ```

- [ ] **1.2** Create `bootstrap.sh`:
  - Detects existing `.venv/`; if present and `requirements.txt` hash unchanged (stamped into `.venv/.requirements.sha`), exits in < 1 s.
  - Otherwise: `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, write the sha stamp.
  - `chmod +x bootstrap.sh` in the same commit.

- [ ] **1.3** Create `.gitignore`:
  ```
  .venv/
  __pycache__/
  *.pyc
  ```

- [ ] **1.4** Create `SKILL.md` with the frontmatter from the spec. Body covers:
  - Prerequisite check (`python3 --version`, `which ffmpeg`).
  - First-run bootstrap.
  - Mode dispatch: 1 WAV → analyze; 2 WAVs → compare.
  - Reading PNGs as visual evidence (Claude can view image files; surface this).
  - Surfacing top recommendations in one-sentence-each chat.
  - Anti-patterns list verbatim from the spec.

- [ ] **1.5** Create `README.md` — short, English. Two paragraphs: what it does, how to run it manually (`./bootstrap.sh && .venv/bin/python scripts/analyze.py path/to.wav`).

- [ ] **1.6** Run `./bootstrap.sh` once locally to confirm venv setup works on the dev machine. Don't commit the `.venv/` (gitignored).

- [ ] **1.7** Commit: `feat(skill): scaffold openrig-tone-analyzer skeleton + bootstrap`.

---

## Task 2: Write fixture generator + generate fixtures

**Files:** `tests/fixtures/generate.py`, `tests/fixtures/*.wav`.

The fixture generator is committed so fixtures can be regenerated if needed; the generated WAVs are also committed so tests don't require running the generator.

- [ ] **2.1** Implement `tests/fixtures/generate.py`:
  - Hard-coded `np.random.seed(42)` at top.
  - Sample rate: 22050 Hz mono 16-bit (small files, sufficient for tests).
  - Helper: `synth_di(duration_s, fundamental_hz, harmonics)` — sum of sine partials with light vibrato. Models a clean DI signal.
  - Helper: `apply_softclip(signal, gain)` — `tanh(gain * x)`, models tube saturation.
  - Helper: `apply_convolve_reverb(signal, rt60_s)` — convolve with `exp(-t * 6.91 / rt60)` * white noise, normalize.
  - Helper: `add_delay(signal, time_ms, feedback, mix)` — feedback delay line.
  - Generate and write:
    - `clean_di.wav` — 4 s of synth_di(330 Hz, 5 harmonics), no FX.
    - `distorted_di.wav` — same DI, `apply_softclip(gain=8)`. (Should classify as `high_gain`.)
    - `reverb_tail.wav` — clean DI, `apply_convolve_reverb(rt60_s=1.4)`.
    - `delayed_echo.wav` — clean DI, `add_delay(time_ms=380, feedback=0.25, mix=0.3)`.
    - `clean_with_silence.wav` — `clean_di.wav` padded with 1.5 s trailing silence (for time-alignment test).
    - `multi_section.wav` — concatenate (clean DI, 8 s) + (softclip DI gain=12, 12 s) + (clean DI, 8 s). Total 28 s. Tests sectioning.

- [ ] **2.2** Run `python3 tests/fixtures/generate.py` to produce the WAVs. Verify each is ≤ 200 KB and total directory size ≤ 1.5 MB.

- [ ] **2.3** Commit: `feat(tests): fixture generator + synthesized test WAVs`.

---

## Task 3: Implement `_common.py` helpers — TDD

**Files:** `scripts/_common.py`, `tests/test_common.py`.

Pattern: write the failing test first, then the minimum implementation to pass it, refactor, commit.

- [ ] **3.1** `load_audio(path) -> tuple[np.ndarray, int]`. Test: loads each fixture, returns float32 in `[-1, 1]`, channels axis 0 if stereo. Tests for the `> 600 s` rejection (synthesize a 601 s silent WAV in a tmp dir).

- [ ] **3.2** `mono_mixdown(signal) -> np.ndarray`. Test: stereo input → mono output equals `mean(axis=0)`.

- [ ] **3.3** `compute_rms_db(signal) -> float`. Test: known-amplitude sine returns expected dBFS (within 0.1 dB).

- [ ] **3.4** `compute_peak_db(signal) -> float`. Test: known peak returns expected dBFS.

- [ ] **3.5** `compute_band_energy_db(signal, sr) -> list[float]` over the spec's 8 bands. Test: a 1 kHz sine has its energy concentrated in the `[640, 1280)` band.

- [ ] **3.6** `compute_spectral_centroid_hz(signal, sr) -> float` (median across frames). Test: a 1 kHz sine returns ≈ 1000 Hz.

- [ ] **3.7** `estimate_thd_pct(signal, sr) -> float`. Implementation: pick the loudest tonal frame (lowest centroid variance over a 100 ms window), compute the ratio of energy at the 2nd–5th harmonic bins to the fundamental bin. Test: pure sine returns < 1%; `apply_softclip(sine, gain=8)` returns > 15%.

- [ ] **3.8** `classify_gain_character(thd_pct, crest_db, band_energy_db) -> tuple[str, float]`. Decision rules from the spec. Test pinned cases: `(thd=1.0, crest=14)` → `("clean", ~0.85)`; `(thd=20, crest=8)` → `("distortion", ~0.5)`; `(thd=35, ...)` → `("high_gain", >0.9)`.

- [ ] **3.9** `estimate_rt60_s(signal, sr) -> tuple[float | None, float]` (value, confidence). Detect a decay tail; if none, return `(None, 0.0)`. Test: clean DI returns low confidence; reverb tail fixture returns ~1.4 s with confidence > 0.5.

- [ ] **3.10** `detect_delay(signal, sr) -> tuple[bool, int | None, float | None]` (present, time_ms, feedback_pct). Autocorrelation on a centered 4-s window. Test: clean returns `(False, None, None)`; `delayed_echo.wav` returns `(True, ~380, ~25)`.

- [ ] **3.11** `compute_lufs_integrated(signal, sr) -> float` via `pyloudnorm`. Test: known-loudness sine returns expected LUFS within 0.5 dB.

- [ ] **3.12** `segment_track(signal, sr) -> list[Section]`. Implementation per spec (frame features → self-similarity → agglomerative → 8 s merge). Returns list of `(start_s, end_s)` tuples. Tests:
  - Short clip (4 s) returns exactly 1 section spanning the whole file.
  - `multi_section.wav` returns exactly 3 sections, boundaries within ±1 s of `[0, 8, 20, 28]`.

- [ ] **3.13** `align_signals(ref, wet, sr) -> tuple[int, float]` (lag_samples, confidence). Cross-correlate → onset-detect fallback. Test:
  - Identical signals: lag = 0, confidence > 0.9.
  - Wet padded with leading silence: lag matches the padding, confidence > 0.6.
  - Two unrelated signals: confidence < 0.3.

- [ ] **3.14** `round_for_json(value, ndigits=4)` — recursive over dicts/lists/floats. Test: nested dict with floats and ints round-trips identically; `np.float64` cast to Python `float`.

- [ ] **3.15** Commit after each helper passes its tests, or batch into one commit per logical group (3.1–3.4 loudness, 3.5–3.8 spectrum, 3.9–3.10 time-fx, 3.11–3.13 segmentation+align, 3.14 plumbing). Squash-style is fine.

---

## Task 4: Implement `analyze.py` — TDD

**Files:** `scripts/analyze.py`, `tests/test_analyze.py`.

- [ ] **4.1** CLI shape: `analyze.py <input.wav> [--out-dir DIR]`. Argparse, no other flags. Default out-dir per spec.

- [ ] **4.2** Top-level flow:
  ```
  signal, sr = load_audio(path)
  sections = segment_track(signal, sr)
  fingerprint = build_fingerprint(signal, sr, sections, path)
  write_fingerprint_json(fingerprint, out_dir)
  render_spec_global_png(signal, sr, sections, out_dir)
  for s in sections: render_spec_section_png(signal, sr, s, out_dir)
  print(out_dir)
  ```

- [ ] **4.3** `build_fingerprint(...)`: assembles the schema-v2 dict from helper outputs. Hash source via `sha256(open(path, 'rb').read())`. All floats round to 4 decimals.

- [ ] **4.4** `render_spec_global_png` — librosa.display.specshow on the mel spectrogram, axvline at each section boundary, axis labels, title, color bar. PIL-check dimensions ≥ 1024×512 in test.

- [ ] **4.5** `render_spec_section_png` — picks the loudest 4 s window within the section (sliding 4 s RMS, argmax), shows that window only. Same axis style.

- [ ] **4.6** Tests in `test_analyze.py`:
  - `test_clean_di_basic` — all fields present, types/ranges OK, exactly 1 section, `tone_profile == "clean"`.
  - `test_multi_section` — exactly 3 sections, labels = `["clean", "high_gain", "clean"]`.
  - `test_determinism` — run twice into different out-dirs, hash both `fingerprint.json` files, assert equal. (This complements `test_determinism.py` which pins the literal hash value.)
  - `test_png_dimensions` — open every output PNG with `PIL.Image`, assert size ≥ (1024, 512).
  - `test_long_file_rejected` — synthesize a 601 s silence WAV in tmp, run analyze, expect `SystemExit` with the spec's exact message.

- [ ] **4.7** Commit: `feat(analyzer): analyze mode with v2 fingerprint + global/section PNGs`.

---

## Task 5: Implement `compare.py` — TDD

**Files:** `scripts/compare.py`, `tests/test_compare.py`.

- [ ] **5.1** CLI shape: `compare.py <ref.wav> <wet.wav> [--out-dir DIR] [--ref-section IDX]`.

- [ ] **5.2** Top-level flow:
  ```
  ref_fp = run_analyze_cached(ref_path)
  wet_fp = run_analyze_cached(wet_path)
  lag, align_conf = align_signals(ref_signal, wet_signal, sr)
  matched_section = pick_ref_section(ref_fp, wet_fp) if --ref-section is None else ref_fp.sections[idx]
  delta = compute_delta(matched_section, wet_fp.sections[0])
  match_score = compute_match_score(delta)
  recommendations = build_recommendations(delta, matched_section, wet_fp.sections[0])
  diff = assemble_diff(...)
  write_diff_json(diff, out_dir)
  render_ab_spec_png(matched_section, wet_fp.sections[0], out_dir)
  print(out_dir)
  ```

- [ ] **5.3** `run_analyze_cached(path)` — sha256 the file; if `/tmp/openrig-analyzer-cache/<sha>.json` exists, load it; else run analyze and write the cache. Cache dir gitignored implicitly (in `/tmp`).

- [ ] **5.4** `pick_ref_section(ref_fp, wet_fp)` — for each ref section, compute the no-time-fx similarity (band_energy + centroid + thd terms only) against `wet_fp.sections[0]`; return the argmax. Tie-break by closest `tone_profile` label.

- [ ] **5.5** `compute_delta` and `compute_match_score` — per spec. Weights pulled from a module-level `WEIGHTS = {...}` dict (pinned in `test_compare.py`).

- [ ] **5.6** `build_recommendations` — emits the four-target template (amp, eq_eight_band_parametric, delay, reverb) based on which deltas exceed thresholds. Each item has `priority`, `target`, `action`, `rationale`. Sorted by priority.

- [ ] **5.7** `render_ab_spec_png` — two-panel matplotlib figure, shared color scale, titles showing each side's section id.

- [ ] **5.8** Tests in `test_compare.py`:
  - `test_identical` — same WAV twice, `match_score ≥ 0.99`, recommendations empty.
  - `test_clean_vs_distorted` — `clean_di.wav` vs `distorted_di.wav`, `match_score < 0.5`, ≥ 1 recommendation with `target == "amp"` and "gain" in action.
  - `test_trailing_silence_alignment` — `clean_di.wav` vs `clean_with_silence.wav`, `alignment_confidence > 0.6`, `match_score > 0.95` (signals are the same after alignment).
  - `test_missing_delay_flagged` — `delayed_echo.wav` vs `clean_di.wav`, `delta.delay_present == { ref: true, wet: false, ... }`, recommendation `target == "delay"`.
  - `test_missing_reverb_flagged` — `reverb_tail.wav` vs `clean_di.wav`, `delta.reverb_rt60_s.wet_minus_ref < -0.5`, recommendation `target == "reverb"`.
  - `test_auto_section_pick` — `multi_section.wav` (ref, 3 sections) vs `distorted_di.wav` (wet, 1 section). Expect `matched_section_id == "section_1"` (the high_gain middle).
  - `test_ref_section_override` — same inputs, `--ref-section 0`, expect `matched_section_id == "section_0"`.
  - `test_weights_pinned` — assert `WEIGHTS == { ... }` exact values. Changing weights forces this test to update.

- [ ] **5.9** Commit: `feat(analyzer): compare mode with auto section-pick + recommendations`.

---

## Task 6: Cross-cutting tests + final checks

**Files:** `tests/test_determinism.py`, `tests/test_no_network.py`.

- [ ] **6.1** `test_determinism.py`: run `analyze` on each committed fixture into a tmp dir, hash the resulting `fingerprint.json` and assert each matches a literal pinned hash. Hashes are filled in after the first successful run; subsequent code changes that perturb them must update the literals with a one-line justification in the PR commit.

- [ ] **6.2** `test_no_network.py`: monkey-patch `socket.socket` to raise on `__init__`. Import and run both `analyze.main` and `compare.main` on a fixture. Assert no exception. (If `librosa` or `matplotlib` try to fetch anything on first import, this will surface it.)

- [ ] **6.3** Run the full suite locally — target ≤ 90 s wall on the dev machine.
  ```
  cd skills/openrig-tone-analyzer
  ./bootstrap.sh
  .venv/bin/pytest -q
  ```

- [ ] **6.4** Commit: `test(analyzer): pin determinism hashes + assert no network`.

---

## Task 7: Smoke + PR

- [ ] **7.1** Manual smoke on a real guitar track (user will provide). Run analyze, inspect the section count and labels in `fingerprint.json` and the `spec_global.png`. Adjust the segmentation `k` heuristic ONLY if obviously wrong (e.g., a riff is split into 8 sections, or a 4-minute song is reported as 1 section). Any tuning must keep the synthesized fixture tests passing.

- [ ] **7.2** Final lint pass: every script starts with `#!/usr/bin/env python3` if executable; no `print()` debug leftovers; no stdout beyond the resolved out-dir; English-only comments.

- [ ] **7.3** Push branch + open PR to `main`:
  ```bash
  git push -u origin feature/issue-8
  gh pr create \
    --title "feat(skill): openrig-tone-analyzer — multi-section fingerprint + A/B comparator" \
    --body "$(cat <<'EOF'
  Adds `skills/openrig-tone-analyzer/` — a pure-function audio analyzer + A/B comparator that feeds the openrig-tone-builder validation loop.

  - `analyze` emits a v2 fingerprint with per-section descriptors (loudness, spectrum, distortion, time-fx) for full-length guitar tracks.
  - `compare` auto-selects the ref section whose tone profile best matches the wet, then emits a diff + ranked recommendations consumable by the orchestrator.
  - No MCP, no `openrig --render`, no network at runtime. Determinism hashes pinned.

  Closes #8.

  Spec: `docs/superpowers/specs/2026-05-26-openrig-tone-analyzer-design.md`
  Plan: `docs/superpowers/plans/2026-05-26-openrig-tone-analyzer.md`

  Follow-up: teach openrig-tone-builder to invoke `analyzer.compare(ref, wet)` after each chain build.
  EOF
  )"
  ```

- [ ] **7.4** Comment on issue #8 with the PR URL. Don't close the issue — `Closes #8` in the PR body handles that on merge.

---

## Verification gates

Each task ends with a verification step **before** marking it done:

- Task 1: `./bootstrap.sh && ./bootstrap.sh` — second invocation < 2 s.
- Tasks 3–5: `pytest tests/test_<that_task>.py -q` green.
- Task 6: full `pytest -q` green, total wall < 90 s.
- Task 7: PR opens, CI (if any) green.

If a verification step fails, fix in place and re-run before moving on. **Never** mark a task done with red tests.
