# tone-analyzer Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the pure audio analyzer from `skills/openrig-tone-analyzer/` into a new repo `jpfaria/tone-analyzer` (pip package + CLI + Claude plugin), and make OpenRig-claude's `openrig-tone-builder` consume it as a dependency.

**Architecture:** The five OpenRig-agnostic modules (`_common`, `analyze`, `compare`, `eq_match`, `make_correction_ir`) become the `tone_analyzer` package with a `tone-analyzer` console script. The OpenRig-coupled engine (`build_preset`, `resolve_gear`, `catalog`, `lint_chain`, `validate_chain`) moves into `skills/openrig-tone-builder/scripts/` and imports `tone_analyzer` from a venv installed from git.

**Tech Stack:** Python 3.11+, setuptools via `pyproject.toml`, pytest, numpy/scipy/librosa/soundfile/matplotlib/pyloudnorm, GitHub Actions, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-09-07-tone-analyzer-extraction-design.md`

## Global Constraints

- New repo path on disk: `~/Projetos/github.com/jpfaria/tone-analyzer`. GitHub: `jpfaria/tone-analyzer`, public, license GPL-3.0 (copy of OpenRig-claude's `LICENSE`).
- Package name `tone_analyzer`; distribution name `tone-analyzer`; console script `tone-analyzer`; plugin name `tone-analyzer`; marketplace name `tone-analyzer`; skill name `tone-analyzer`. Version `0.1.0`.
- Runtime deps pinned exactly: `numpy==2.1.3 scipy==1.14.1 librosa==0.10.2.post1 soundfile==0.12.1 matplotlib==3.9.2 pyloudnorm==0.1.1`. Dev: `pytest==8.3.3`. `pyyaml` is NOT an analyzer dependency.
- Output contract unchanged: `--out-dir`, JSON schemas, PNG/PDF names, last stdout line = out-dir.
- All committed text in English. Commit trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- OpenRig-claude ships as `1.0.0` with annotated tag `v1.0.0`; tone-analyzer ships as `0.1.0` with annotated tag `v0.1.0`. Push tags by name, never rely on `--follow-tags`.
- Source snapshot for the import: OpenRig-claude `69a1a09`.

---

### Task 1: Scaffold the `tone_analyzer` package and make its tests pass

**Files:**
- Create: `~/Projetos/github.com/jpfaria/tone-analyzer/pyproject.toml`
- Create: `~/Projetos/github.com/jpfaria/tone-analyzer/tone_analyzer/__init__.py`
- Create: `~/Projetos/github.com/jpfaria/tone-analyzer/tone_analyzer/cli.py`
- Create (copied + import-rewritten): `tone_analyzer/{_common,analyze,compare,eq_match,make_correction_ir}.py`
- Create (copied + import-rewritten): `tests/{conftest,test_analyze,test_compare,test_eq_match,test_common,test_determinism,test_no_network,test_fingerprint_match_target}.py`, `tests/__init__.py`, `tests/fixtures/*.wav`, `tests/fixtures/generate.py`
- Create: `tests/test_cli.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `tone_analyzer.analyze.main(argv) -> int`, `tone_analyzer.compare.main(argv) -> int`, `tone_analyzer.eq_match.main(argv) -> int`, `tone_analyzer.make_correction_ir.main(argv) -> int`, `tone_analyzer.cli.main(argv=None) -> int`; console script `tone-analyzer {analyze|compare|eq-match|correction-ir} …`.
- Produces for Task 4: `tone_analyzer._common` (functions `load_audio`, `third_octave_ltas`, `fingerprint_match_target`, `trustworthy_band_mask`, `weighted_spectral_proximity_pct`, `compute_spectral_rolloff_hz`, `round_for_json`, constant `THIRD_OCTAVE_CENTERS_HZ`) and `tone_analyzer.eq_match` (`next_band_gains`, `next_highpass_hz`, `normalized_ltas`) — unchanged bodies.

- [ ] **Step 1: Create the repo skeleton and copy the analyzer files**

```bash
SRC=~/Projetos/github.com/jpfaria/OpenRig-claude/skills/openrig-tone-analyzer
DST=~/Projetos/github.com/jpfaria/tone-analyzer
mkdir -p "$DST/tone_analyzer" "$DST/tests/fixtures"
cd "$DST" && git init -q
for m in _common analyze compare eq_match make_correction_ir; do cp "$SRC/scripts/$m.py" tone_analyzer/; done
for t in conftest test_analyze test_compare test_eq_match test_common test_determinism test_no_network test_fingerprint_match_target; do cp "$SRC/tests/$t.py" tests/; done
touch tests/__init__.py
cp "$SRC"/tests/fixtures/*.wav "$SRC/tests/fixtures/generate.py" tests/fixtures/
cp ~/Projetos/github.com/jpfaria/OpenRig-claude/LICENSE LICENSE
printf '%s\n' '.venv/' '__pycache__/' '*.pyc' '*.pyo' '.pytest_cache/' '*.egg-info/' 'build/' 'dist/' '.DS_Store' > .gitignore
```

- [ ] **Step 2: Rewrite imports and drop the `sys.path` hacks**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer
sed -i '' -e 's/^from scripts import /from tone_analyzer import /' -e 's/^from scripts\./from tone_analyzer./' tone_analyzer/*.py tests/*.py
# delete the sys.path.insert lines and the comment right above them in package modules
sed -i '' -e '/^# Allow `python scripts\/.*` invocation/d' -e '/^sys\.path\.insert(0, str(_HERE\.parent))$/d' tone_analyzer/*.py
grep -n "_HERE" tone_analyzer/*.py
```
For each module where `_HERE` is now only assigned and never read, delete the `_HERE = Path(__file__).resolve().parent` line (and `from pathlib import Path` / `import sys` if they become unused — check with `grep -n "Path\b\|sys\." <file>`).

Then in `tests/conftest.py` delete these lines (the package is installed, no path hack needed):
```python
import sys
...
SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
```
Also `tests/fixtures/generate.py`: change its docstring `openrig-tone-analyzer` → `tone-analyzer`, and the run hint to `.venv/bin/python tests/fixtures/generate.py`. Change docstring mentions of `requirements.txt` to `pyproject.toml`.

Verify nothing references the old names:
```bash
grep -rn "scripts\.\|from scripts\|openrig" tone_analyzer tests | grep -v "openrig-render\|openrig_render"
```
Expected: no output except possibly comments in `_common.py`/`compare.py` that talk about "the openrig-tone-builder orchestrator" — change those to "the orchestrator (caller)".

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tone-analyzer"
version = "0.1.0"
description = "Pure-function guitar tone analyzer: WAV in, fingerprint JSON + spectrograms out; A/B compare and EQ-match."
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.11"
authors = [{ name = "João Paulo Faria" }]
dependencies = [
  "numpy==2.1.3",
  "scipy==1.14.1",
  "librosa==0.10.2.post1",
  "soundfile==0.12.1",
  "matplotlib==3.9.2",
  "pyloudnorm==0.1.1",
]

[project.optional-dependencies]
dev = ["pytest==8.3.3"]

[project.scripts]
tone-analyzer = "tone_analyzer.cli:main"

[project.urls]
Homepage = "https://github.com/jpfaria/tone-analyzer"

[tool.setuptools.packages.find]
include = ["tone_analyzer*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`README.md` is referenced above, so create a one-line placeholder now (Task 2 writes the real one):
```bash
echo "# tone-analyzer" > README.md
```

- [ ] **Step 4: Write `tone_analyzer/__init__.py`**

```python
"""tone-analyzer: pure-function guitar tone analysis (WAV in, JSON/PNG out)."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Write the failing CLI test `tests/test_cli.py`**

```python
"""The `tone-analyzer` console script dispatches to each module's main()."""

from __future__ import annotations

from pathlib import Path

import pytest

from tone_analyzer import cli


def test_no_args_prints_usage_and_exits_2(capsys):
    rc = cli.main([])
    assert rc == 2
    assert "analyze" in capsys.readouterr().err


def test_help_exits_0(capsys):
    rc = cli.main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    for cmd in ("analyze", "compare", "eq-match", "correction-ir"):
        assert cmd in out


def test_unknown_command_exits_2(capsys):
    rc = cli.main(["frobnicate"])
    assert rc == 2
    assert "frobnicate" in capsys.readouterr().err


def test_analyze_dispatch_writes_fingerprint(clean_di_path: Path, tmp_path: Path):
    out = tmp_path / "out"
    rc = cli.main(["analyze", str(clean_di_path), "--out-dir", str(out)])
    assert rc == 0
    assert (out / "fingerprint.json").is_file()
```

- [ ] **Step 6: Create the venv, install editable, run the CLI test to see it fail**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer
python3 -m venv .venv && .venv/bin/pip install --quiet --upgrade pip && .venv/bin/pip install --quiet -e ".[dev]"
.venv/bin/pytest tests/test_cli.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'tone_analyzer.cli'`.

- [ ] **Step 7: Write `tone_analyzer/cli.py`**

```python
"""Console entry point: `tone-analyzer <command> [args…]`.

Each subcommand delegates to the module's own `main(argv)` so the argparse
surface of `analyze`, `compare`, `eq_match` and `make_correction_ir` stays the
single source of truth.
"""

from __future__ import annotations

import sys

from tone_analyzer import analyze, compare, eq_match, make_correction_ir

_COMMANDS = {
    "analyze": analyze.main,
    "compare": compare.main,
    "eq-match": eq_match.main,
    "correction-ir": make_correction_ir.main,
}

USAGE = """usage: tone-analyzer <command> [args...]

commands:
  analyze        <in.wav> [--out-dir DIR]                 fingerprint.json + spectrograms + analysis.pdf
  compare        <ref.wav> <wet.wav> [--out-dir DIR] ...  diff.json + A/B spectrogram
  eq-match       <ref.wav> <wet.wav> --gains g1,...,g8    next 8-band EQ gains toward the reference
  correction-ir  ...                                      minimum-phase correction IR from an LTAS gap

Run `tone-analyzer <command> --help` for that command's options.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(USAGE, file=sys.stderr)
        return 2
    if args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = args[0], args[1:]
    fn = _COMMANDS.get(cmd)
    if fn is None:
        print(f"tone-analyzer: unknown command '{cmd}'", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    return int(fn(rest))


if __name__ == "__main__":
    sys.exit(main())
```

Check `make_correction_ir.main`'s actual argparse arguments (`grep -n add_argument tone_analyzer/make_correction_ir.py`) and make the `correction-ir` usage line match them.

- [ ] **Step 8: Run the full suite**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer && .venv/bin/pytest -q
```
Expected: all tests PASS (the seven copied test modules + `test_cli.py`). If `test_determinism` compares against golden values and fails, the cause is an import-path change altering nothing numerical — investigate before touching goldens; do NOT regenerate goldens to make it pass.

- [ ] **Step 9: Smoke the console script**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer
.venv/bin/tone-analyzer analyze tests/fixtures/clean_di.wav --out-dir /tmp/ta-smoke && ls /tmp/ta-smoke
```
Expected: last stdout line is `/tmp/ta-smoke`; listing shows `fingerprint.json`, `analysis.pdf`, `spec_*.png`.

- [ ] **Step 10: Commit**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer
git add -A
git commit -m "feat: import pure analyzer from OpenRig-claude@69a1a09 as tone_analyzer package

analyze / compare / eq_match / make_correction_ir + tests and WAV fixtures,
re-rooted from skills/openrig-tone-analyzer/scripts into an installable
package with a \`tone-analyzer\` console script.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Claude plugin wrapper, bootstrap, README, CI

**Files:**
- Create: `bootstrap.sh`
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`
- Create: `skills/tone-analyzer/SKILL.md`
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Produces: plugin `tone-analyzer` installable via `/plugin marketplace add jpfaria/tone-analyzer` + `/plugin install tone-analyzer@tone-analyzer`; skill `tone-analyzer:tone-analyzer`. The skill runs `${CLAUDE_PLUGIN_ROOT}/bootstrap.sh` then `${CLAUDE_PLUGIN_ROOT}/.venv/bin/tone-analyzer …`.

- [ ] **Step 1: Write `bootstrap.sh`** (stamp on `pyproject.toml`, editable install of the plugin root itself)

```bash
#!/usr/bin/env bash
# Idempotent venv setup for tone-analyzer (used by the Claude skill and by humans).
# First run: ~30-60 s. Subsequent runs: <1 s if pyproject.toml is unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
STAMP="$VENV_DIR/.pyproject.sha"

if command -v sha256sum >/dev/null 2>&1; then
  CURRENT_SHA="$(sha256sum pyproject.toml | awk '{print $1}')"
else
  CURRENT_SHA="$(shasum -a 256 pyproject.toml | awk '{print $1}')"
fi

if [ -d "$VENV_DIR" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$CURRENT_SHA" ]; then
  exit 0
fi

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e ".[dev]"

echo "$CURRENT_SHA" > "$STAMP"
```
`chmod +x bootstrap.sh`.

- [ ] **Step 2: Verify bootstrap is idempotent**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer && rm -rf .venv && ./bootstrap.sh && time ./bootstrap.sh && .venv/bin/tone-analyzer --help | head -3
```
Expected: second run < 1 s; help prints usage.

- [ ] **Step 3: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "tone-analyzer",
  "description": "Pure-function guitar tone analyzer: fingerprint a WAV, A/B compare a render against a reference, compute EQ-match gains. No rig, no network — JSON + spectrograms on disk.",
  "version": "0.1.0",
  "author": { "name": "João Paulo" },
  "homepage": "https://github.com/jpfaria/tone-analyzer"
}
```

- [ ] **Step 4: Write `.claude-plugin/marketplace.json`**

```json
{
  "name": "tone-analyzer",
  "owner": { "name": "João Paulo", "url": "https://github.com/jpfaria/tone-analyzer" },
  "plugins": [
    {
      "name": "tone-analyzer",
      "source": "./",
      "description": "Analyze guitar audio (fingerprint JSON + spectrograms), compare a render to a reference, and compute EQ-match gains. Pure function on disk — never touches a rig."
    }
  ]
}
```

- [ ] **Step 5: Write `skills/tone-analyzer/SKILL.md`**

Start from `~/Projetos/github.com/jpfaria/OpenRig-claude/skills/openrig-tone-analyzer/SKILL.md` and apply exactly these edits:

1. Frontmatter `name: tone-analyzer`. Description: keep the trigger phrases; replace the last two sentences with: `Does NOT modify any rig or project and makes no network calls. Orchestrators (e.g. OpenRig's tone-builder) consume this skill's JSON.`
2. Title `# tone-analyzer`. First paragraph: `Pure-function audio analyzer + A/B comparator. Callers consume the JSON output to adjust their signal chain; this skill itself never mutates anything outside --out-dir.`
3. Iron rule 1 → `**No side effects outside \`--out-dir\`.** No MCP calls, no rig edits, no project writes — every chain touch is the caller's job.` Merge old rule 2 into it (keep the "no stdout chatter beyond the out-dir line" clause).
4. Rule 3: `"It sounds like a Mesa Rectifier" is research, not measurement — never claim it from audio.` Rule 3b: drop the trailing `(openrig-tone-builder carries the full rule.)`.
5. "First-run bootstrap" section becomes:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bootstrap.sh"      # idempotent; <1 s on subsequent runs
   ```
   with the note: `The venv lives at ${CLAUDE_PLUGIN_ROOT}/.venv (gitignored). Outside a plugin install, CLAUDE_PLUGIN_ROOT is the repo root.`
6. Workflow step 2 commands become:
   ```bash
   TA="${CLAUDE_PLUGIN_ROOT}/.venv/bin/tone-analyzer"
   "$TA" analyze <input.wav> [--out-dir DIR]
   "$TA" compare <ref.wav> <wet.wav> [--out-dir DIR] [--ref-section IDX] [--wet-section IDX]
   "$TA" eq-match <ref.wav> <wet.wav> --gains <g1,…,g8> [--hp-hz HZ] [--output FILE]
   ```
   Replace every remaining `analyze.py`/`compare.py`/`eq_match.py` mention with `analyze`/`compare`/`eq-match`.
7. In the `eq-match` paragraph: `used by the openrig-tone-builder Step 6.3 loop` → `used by an orchestrator's EQ loop`; `The orchestrator (openrig-tone-builder) feeds … via set_block_parameter_number` → `The caller feeds the EQ's current gains in, applies new_gains, re-renders, and loops until proximity_pct ≥ 95.`
8. Replace the "Pick `--out-dir` from MCP" paragraph with: `**\`--out-dir\`.** Callers pass an absolute directory they own. When omitted the script falls back to \`/tmp/tone-analyzer/<unix_ts>/\` so a one-shot manual run still works.` Then change the fallback default in `tone_analyzer/analyze.py` and `compare.py` from `/tmp/openrig-analyzer/` to `/tmp/tone-analyzer/` (grep `openrig-analyzer`), and update any test asserting on that path.
9. Workflow step 5 → `**Stop at the diff.** Adjusting a chain is the caller's job.`
10. Anti-pattern 1 → `Calling any rig/MCP tool because "it would be faster to also adjust the chain."`
11. "Output schemas" section: replace the spec link with `See README.md (Output schemas).` Keep the short-form bullets.
12. Grep the result: `grep -n "openrig\|OpenRig\|tone-builder" skills/tone-analyzer/SKILL.md` — the only allowed hits are the description's parenthetical "(e.g. OpenRig's tone-builder)".

- [ ] **Step 6: Write `README.md`**

```markdown
# tone-analyzer

Pure-function guitar tone analyzer. WAV in → JSON + spectrogram PNGs out.
No network, no DAW, no rig: the only side effect is files under `--out-dir`.

- **`analyze <wav>`** — `fingerprint.json` (schema 3: global + per-section
  loudness / spectrum / distortion / time-FX descriptors, honest match target),
  `spec_*.png`, `analysis.pdf`.
- **`compare <ref.wav> <wet.wav>`** — auto-picks the reference section that best
  matches the wet signal, emits `diff.json` (`proximity_pct`, `match_score`,
  ranked `recommendations[]`) plus an A/B spectrogram.
- **`eq-match <ref.wav> <wet.wav> --gains g1,…,g8`** — next 8-band EQ gains that
  move the wet render's normalised LTAS shape toward the reference.
- **`correction-ir`** — minimum-phase correction IR from an LTAS gap.

## Install

```bash
pip install "tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.1.0"
tone-analyzer analyze track.wav
```

Or clone and run `./bootstrap.sh` (creates `.venv/` with an editable install).

## Claude plugin

```
/plugin marketplace add jpfaria/tone-analyzer
/plugin install tone-analyzer@tone-analyzer
```

The `tone-analyzer` skill bootstraps its own venv on first use and exposes the
same three commands to the agent. It never touches a rig — orchestrators
(e.g. OpenRig's `openrig-tone-builder`) consume its JSON.

## Output schemas

- `fingerprint.json`: `source`, `global`, `sections[]` (each with `loudness`,
  `spectrum`, `distortion`, `time_fx`, `labels`), `fingerprint_match_target`
  (`third_octave_centers_hz`, `ltas_norm_db`, `reliable_mask`,
  `reliable_range_hz`, `top_octave_dead`, `self_floor_pct`).
- `diff.json`: `reference.matched_section_id`, `rendered`, `proximity_pct`
  (0–100, level-independent timbre; band-limited when `ref_top_octave_dead`),
  `ref_top_octave_dead`, `match_score`, `delta.*`, `recommendations[]`
  (`target`, `action`, `rationale`), `converged`.
- `eq-match` JSON: `new_gains[8]`, `proximity_pct`, `band_gap_db`,
  `total_gap_db`, `new_highpass_hz`, `ref_top_octave_dead`, `trustworthy_bands_hz`.

Files longer than 600 s are rejected; trim first.

## Development

```bash
./bootstrap.sh
.venv/bin/pytest -q
.venv/bin/python tests/fixtures/generate.py   # regenerate WAV fixtures (seeded)
```

## License

GPL-3.0 — see `LICENSE`.
```

- [ ] **Step 7: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: sudo apt-get update && sudo apt-get install -y libsndfile1
      - run: pip install -e ".[dev]"
      - run: pytest -q
```

- [ ] **Step 8: Run the suite once more and commit**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer && .venv/bin/pytest -q && git add -A && git commit -m "feat: Claude plugin wrapper, bootstrap, README, CI

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Publish `jpfaria/tone-analyzer`

**Files:** none new.

- [ ] **Step 1: Create the GitHub repo and push**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer
git branch -M main
gh repo create jpfaria/tone-analyzer --public --description "Pure-function guitar tone analyzer: fingerprint, A/B compare, EQ-match. Python CLI + Claude plugin." --source=. --remote=origin --push
```

- [ ] **Step 2: Tag and push the tag by name**

```bash
git tag -a v0.1.0 -m v0.1.0 && git push origin v0.1.0
git ls-remote --tags origin | grep v0.1.0
```
Expected: one line ending in `refs/tags/v0.1.0`.

- [ ] **Step 3: Verify install-from-git in a throwaway venv**

```bash
python3 -m venv /tmp/ta-git && /tmp/ta-git/bin/pip install --quiet "tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.1.0" && /tmp/ta-git/bin/tone-analyzer analyze ~/Projetos/github.com/jpfaria/tone-analyzer/tests/fixtures/clean_di.wav --out-dir /tmp/ta-git-out | tail -1 && ls /tmp/ta-git-out/fingerprint.json
```
Expected: prints `/tmp/ta-git-out` then the file path.

---

### Task 4: Move the engine into `skills/openrig-tone-builder/` and consume `tone_analyzer`

**Files (OpenRig-claude):**
- Create: `skills/openrig-tone-builder/scripts/{__init__,build_preset,resolve_gear,catalog,lint_chain,validate_chain}.py`, `scripts/native_models.yaml`
- Create: `skills/openrig-tone-builder/tests/{__init__,conftest,test_build_preset,test_resolve_gear,test_catalog,test_lint_chain,test_validate_chain}.py`, `tests/fixtures/catalog/**`
- Create: `skills/openrig-tone-builder/requirements.txt`, `bootstrap.sh`, `.gitignore`
- Modify: `skills/openrig-tone-builder/scripts/build_preset.py` (imports + docstring)
- Delete: `skills/openrig-tone-analyzer/` (whole directory)

**Interfaces:**
- Consumes: `tone_analyzer._common`, `tone_analyzer.eq_match.{next_band_gains,next_highpass_hz,normalized_ltas}` from Task 1, installed via git at `v0.1.0` from Task 3.
- Produces: `skills/openrig-tone-builder/.venv/bin/python skills/openrig-tone-builder/scripts/build_preset.py …` (the path the SKILL.md in Task 5 documents). `resolve_gear.py` defaults `native_models.yaml` relative to itself — unchanged.

- [ ] **Step 1: Move the files with `git mv`**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude
TB=skills/openrig-tone-builder; TA=skills/openrig-tone-analyzer
mkdir -p $TB/scripts $TB/tests/fixtures
for m in __init__ build_preset resolve_gear catalog lint_chain validate_chain; do git mv $TA/scripts/$m.py $TB/scripts/; done
git mv $TA/scripts/native_models.yaml $TB/scripts/
for t in __init__ test_build_preset test_resolve_gear test_catalog test_lint_chain test_validate_chain; do git mv $TA/tests/$t.py $TB/tests/; done
git mv $TA/tests/fixtures/catalog $TB/tests/fixtures/catalog
git mv $TA/.gitignore $TB/.gitignore
git mv $TA/bootstrap.sh $TB/bootstrap.sh
git rm -rq $TA
rm -rf $TA
git status --short | head -30
```
Expected: renames (`R`) for the engine files, deletions (`D`) for the analyzer modules/tests/WAV fixtures/README/SKILL.md/requirements.txt. `$TA` no longer exists on disk.

- [ ] **Step 2: Write `skills/openrig-tone-builder/requirements.txt`**

```
tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.1.0
pyyaml==6.0.3
pytest==8.3.3
```

- [ ] **Step 3: Fix `bootstrap.sh`'s header comment**

Change line 2 from `# Idempotent venv setup for openrig-tone-analyzer.` to `# Idempotent venv setup for the openrig-tone-builder engine (build_preset.py & co).` Everything else stays (it hashes `requirements.txt`, which is what we want).

- [ ] **Step 4: Rewrite imports in `build_preset.py`**

Replace lines 99–102 (currently):
```python
from scripts import _common  # noqa: E402
from scripts import lint_chain, resolve_gear, validate_chain  # noqa: E402
from scripts.catalog import load_catalog  # noqa: E402
from scripts.eq_match import next_band_gains, next_highpass_hz  # noqa: E402
```
with:
```python
from tone_analyzer import _common  # noqa: E402
from tone_analyzer.eq_match import next_band_gains, next_highpass_hz  # noqa: E402

from scripts import lint_chain, resolve_gear, validate_chain  # noqa: E402
from scripts.catalog import load_catalog  # noqa: E402
```
and the late import near line 1142 `from scripts.eq_match import normalized_ltas` → `from tone_analyzer.eq_match import normalized_ltas`.

In the module docstring, replace the sentence `The analyzer scripts and venv resolve relative to this file (\`sys.executable\`, \`Path(__file__)\`)` with `The analyzer is the \`tone_analyzer\` package (pip dependency, see requirements.txt); sibling engine modules resolve relative to this file`.

Confirm: `grep -n "from scripts\|scripts\." skills/openrig-tone-builder/scripts/*.py` shows only `lint_chain`, `resolve_gear`, `validate_chain`, `catalog` targets.

- [ ] **Step 5: Write `tests/conftest.py` for the engine tests**

```python
"""Path setup: make `scripts.*` importable from the skill root."""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
```

Then in `tests/test_build_preset.py` change `from scripts import _common  # noqa: E402` → `from tone_analyzer import _common  # noqa: E402` (keep `from scripts import build_preset as bp`). Update its docstring's first line: `(scripts/build_preset.py)` stays correct; no other edits.

- [ ] **Step 6: Bootstrap and run the engine tests**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude/skills/openrig-tone-builder
./bootstrap.sh && .venv/bin/pytest -q tests
.venv/bin/python scripts/build_preset.py --help >/dev/null && echo HELP-OK
.venv/bin/python scripts/resolve_gear.py --help >/dev/null && echo RESOLVE-OK
```
Expected: all tests PASS; `HELP-OK`, `RESOLVE-OK`.

- [ ] **Step 7: Confirm no stale references in code**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude && grep -rn "openrig-tone-analyzer\|from scripts import _common\|scripts/analyze.py\|scripts/compare.py\|scripts/eq_match.py" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs --exclude-dir=.pytest_cache .
```
Expected: hits only in `skills/openrig-tone-builder/SKILL.md` and the three READMEs (fixed in Task 5).

- [ ] **Step 8: Commit (no push yet — Task 5 bumps the version in the same push)**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude
git add -A skills
git commit -m "refactor(tone-builder): engine moves under openrig-tone-builder, analyzer becomes the tone-analyzer pip dependency

build_preset / resolve_gear / catalog / lint_chain / validate_chain now live in
skills/openrig-tone-builder/scripts and import tone_analyzer (pinned to
jpfaria/tone-analyzer@v0.1.0 in requirements.txt). skills/openrig-tone-analyzer
is removed; the pure analyzer is published as its own plugin.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Docs, version bump 1.0.0, ship

**Files:**
- Modify: `skills/openrig-tone-builder/SKILL.md` (lines ~540–560, ~602–625, ~872, ~1241 and every `openrig:openrig-tone-analyzer`)
- Modify: `README.md`, `README.pt-BR.md`, `README.es-ES.md` (skill table row, ASCII diagram line 44, Requirements line 75)
- Modify: `.claude-plugin/plugin.json` (`version` → `1.0.0`)
- Modify: `.gitignore` (add `.dev-rules/`)

- [ ] **Step 1: SKILL.md — add prerequisites block after the H1**

Insert right after `# OpenRig Tone Builder`:

```markdown
## Prerequisites — the `tone-analyzer` plugin

Reference fingerprinting (Step 0) is the **`tone-analyzer:tone-analyzer`** skill,
shipped as its own plugin. Check it is installed before starting; if not, tell
the user to run:

```
/plugin marketplace add jpfaria/tone-analyzer
/plugin install tone-analyzer@tone-analyzer
```

The offline engine (`build_preset.py`, Step 0b) lives in this skill's `scripts/`
and installs the same analyzer as a pip dependency via `./bootstrap.sh` (run
from `skills/openrig-tone-builder/`; idempotent).
```

- [ ] **Step 2: SKILL.md — replace analyzer references**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude
F=skills/openrig-tone-builder/SKILL.md
sed -i '' -e 's#`openrig:openrig-tone-analyzer`#`tone-analyzer:tone-analyzer`#g' \
          -e 's#skills/openrig-tone-analyzer/#skills/openrig-tone-builder/#g' \
          -e 's#(the `openrig-tone-analyzer` engine)#(this skill'"'"'s offline engine)#g' "$F"
grep -n "tone-analyzer" "$F"
```
Then read each remaining hit and fix by hand:
- Step 0b item 1 should read: `**1. \`build_preset.py\`** — \`skills/openrig-tone-builder/scripts/build_preset.py\`, run via its venv (\`skills/openrig-tone-builder/.venv/bin/python\`, after \`./bootstrap.sh\` in that directory).`
- Step 0 item 1: `invoke \`tone-analyzer:tone-analyzer\` with the file path (it runs \`tone-analyzer analyze <wav> --out-dir …\` — pass \`<evaluations_path>/<ts>/\` from Step 0a as the out-dir; the analyzer never reads MCP itself).`
- Any sentence saying the analyzer "falls back to `/tmp/openrig-analyzer`" → `/tmp/tone-analyzer`.

- [ ] **Step 3: READMEs**

In each of `README.md`, `README.pt-BR.md`, `README.es-ES.md`:
1. Delete the `**openrig-tone-analyzer**` table row.
2. Line 44 diagram: keep the `tone-analyzer (verify render vs. reference)` box — it is still accurate — but change the label to `tone-analyzer plugin`.
3. Requirements bullet becomes (EN; translate for PT/ES):
   `- **tone-analyzer plugin** — \`/plugin marketplace add jpfaria/tone-analyzer\` then \`/plugin install tone-analyzer@tone-analyzer\`. Python 3.11+; it self-bootstraps a virtualenv on first use. The tone-builder's offline engine installs the same package via \`skills/openrig-tone-builder/bootstrap.sh\`.`

- [ ] **Step 4: Version bump + gitignore**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude
sed -i '' 's/"version": "0.22.0"/"version": "1.0.0"/' .claude-plugin/plugin.json
grep '"version"' .claude-plugin/plugin.json
printf '.dev-rules/\n' >> .gitignore
grep -rn "openrig-tone-analyzer" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs --exclude-dir=.pytest_cache . ; echo "exit=$?"
```
Expected: version line shows `1.0.0`; grep prints nothing and `exit=1`.

- [ ] **Step 5: Commit, push, tag, push tag, verify**

```bash
cd ~/Projetos/github.com/jpfaria/OpenRig-claude
git add -A
git commit -m "feat(tone-builder)!: depend on the tone-analyzer plugin; drop openrig-tone-analyzer; bump 1.0.0

BREAKING: the openrig-tone-analyzer skill is removed. Install
jpfaria/tone-analyzer (plugin + pip package) — tone-builder's Step 0 now
invokes tone-analyzer:tone-analyzer and its engine imports tone_analyzer.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin main
git tag -a v1.0.0 -m v1.0.0 && git push origin v1.0.0
git ls-remote --tags origin | grep -E "v1\.0\.0"
```
Expected: one line ending in `refs/tags/v1.0.0`.

- [ ] **Step 6: Final cross-repo verification**

```bash
cd ~/Projetos/github.com/jpfaria/tone-analyzer && .venv/bin/pytest -q
cd ~/Projetos/github.com/jpfaria/OpenRig-claude/skills/openrig-tone-builder && .venv/bin/pytest -q tests
gh run list -R jpfaria/tone-analyzer --limit 1
```
Expected: both suites green; the CI run on tone-analyzer is queued/passing (report its status honestly).
