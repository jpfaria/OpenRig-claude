# tone-analyzer extraction — design

**Date:** 2026-09-07
**Status:** approved

## Goal

Move the pure-function audio analyzer out of `skills/openrig-tone-analyzer/` into a
standalone repo `jpfaria/tone-analyzer` that is BOTH a pip-installable Python package
with a CLI AND a Claude plugin. The OpenRig-coupled engine (`build_preset`,
`resolve_gear`, `catalog`, `lint_chain`, `validate_chain`) stays in OpenRig-claude,
inside `skills/openrig-tone-builder/`, and consumes `tone_analyzer` as a pip dependency.

Decisions taken during brainstorming:

- Shape of the new repo: Python package + CLI + Claude plugin in one repo.
- Consumption: OpenRig-claude removes the analyzer skill entirely; `openrig-tone-builder`
  requires the `tone-analyzer` plugin installed (for the skill) and pins the package
  in its own `requirements.txt` (for `build_preset.py`). No submodule, no thin wrapper.
- History: fresh repo, initial commit "import from OpenRig-claude@69a1a09".
- Scope: only the pure analyzer moves (`_common`, `analyze`, `compare`, `eq_match`,
  `make_correction_ir` + their tests and WAV fixtures).

## Section 1 — `jpfaria/tone-analyzer`

```
tone-analyzer/
├── pyproject.toml            # package `tone_analyzer`, console script `tone-analyzer`
├── tone_analyzer/
│   ├── __init__.py
│   ├── _common.py analyze.py compare.py eq_match.py make_correction_ir.py
│   └── cli.py                # subcommands: analyze | compare | eq-match | correction-ir
├── tests/                    # test_analyze test_compare test_eq_match test_common
│                             # test_determinism test_no_network test_fingerprint_match_target
│                             # conftest.py + fixtures/*.wav + fixtures/generate.py
├── .claude-plugin/plugin.json      # name tone-analyzer, version 0.1.0
├── .claude-plugin/marketplace.json # marketplace `tone-analyzer`, one plugin, source "./"
├── skills/tone-analyzer/SKILL.md   # current SKILL.md, renamed; no OpenRig/tone-builder refs
├── bootstrap.sh              # idempotent venv + `pip install -e .`; stamp = sha256(pyproject.toml)
├── .github/workflows/ci.yml  # pytest on 3.11 and 3.12
├── README.md LICENSE .gitignore
```

- Runtime deps pinned exactly as today's `requirements.txt` (numpy, scipy, librosa,
  soundfile, matplotlib, pyloudnorm). pytest under `[project.optional-dependencies] dev`.
  pyyaml is NOT a dependency of the analyzer (only `build_preset`/`catalog` use it).
- Imports change from `from scripts import _common` to `from tone_analyzer import _common`.
- Each module keeps its `main(argv)`; `cli.py` dispatches to them. Output contract
  (`--out-dir`, JSON schema, PNG names, last stdout line = out-dir) is unchanged.
- SKILL.md tells the agent to run `${CLAUDE_PLUGIN_ROOT}/bootstrap.sh` then
  `${CLAUDE_PLUGIN_ROOT}/.venv/bin/tone-analyzer <subcommand> …`. The iron rules stay,
  minus the OpenRig-specific wording (no MCP → "no side effects outside --out-dir").
- Repo created public via `gh repo create`, pushed, tagged `v0.1.0` (annotated).

## Section 2 — OpenRig-claude

- `git rm -r skills/openrig-tone-analyzer`.
- `skills/openrig-tone-builder/` gains:
  - `scripts/`: `__init__.py`, `build_preset.py`, `resolve_gear.py`, `catalog.py`,
    `lint_chain.py`, `validate_chain.py`, `native_models.yaml`.
  - `tests/`: `conftest.py`, `test_build_preset.py`, `test_resolve_gear.py`,
    `test_catalog.py`, `test_lint_chain.py`, `test_validate_chain.py`, `fixtures/catalog/`.
    Tests that need a WAV generate it on the fly or use the `tone_analyzer` package's
    own fixture generator if importable; otherwise they mock the reference measurement.
  - `requirements.txt`: `tone-analyzer @ git+https://github.com/jpfaria/tone-analyzer@v0.1.0`,
    `pyyaml==6.0.3`, `pytest==8.3.3`.
  - `bootstrap.sh`: same idempotent venv script as today.
  - `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`.
- `build_preset.py` imports `from tone_analyzer import _common` and
  `from tone_analyzer.eq_match import next_band_gains, next_highpass_hz`.
- `openrig-tone-builder/SKILL.md`:
  - new "Prerequisites" block near the top: `/plugin marketplace add jpfaria/tone-analyzer`
    + `/plugin install tone-analyzer@tone-analyzer`; `./bootstrap.sh` in the tone-builder dir.
  - every `openrig:openrig-tone-analyzer` → `tone-analyzer:tone-analyzer`.
  - every `skills/openrig-tone-analyzer/…` path → `skills/openrig-tone-builder/…`.
- README.md / README.pt-BR.md / README.es-ES.md: drop the analyzer skill from the list,
  add the prerequisite.
- `.claude-plugin/plugin.json`: `1.0.0` (a skill was removed → major per CLAUDE.md).
  Commit, push, annotated tag `v1.0.0`, push tag.

## Section 3 — verification

- `tone-analyzer`: `pytest` green; from a clean venv `pip install -e . && tone-analyzer analyze tests/fixtures/clean_di.wav` prints an out-dir with `fingerprint.json`.
- OpenRig-claude: `skills/openrig-tone-builder/bootstrap.sh` installs from git;
  `.venv/bin/pytest skills/openrig-tone-builder/tests` green;
  `.venv/bin/python scripts/build_preset.py --help` exits 0.
- `grep -rn openrig-tone-analyzer` in OpenRig-claude returns only `docs/superpowers/**` history.
- `git ls-remote --tags origin` shows `v0.1.0` (tone-analyzer) and `v1.0.0` (OpenRig-claude).

## Out of scope

- Publishing `tone-analyzer` to PyPI.
- Changing analyzer behaviour or output schema.
- Rewriting `build_preset.py` beyond the import change.
