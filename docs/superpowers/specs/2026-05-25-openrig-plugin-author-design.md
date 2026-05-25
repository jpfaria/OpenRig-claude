# openrig-plugin-author — design spec

**Repo:** `OpenRig-claude` (plugin `openrig`)
**New artifact:** `skills/openrig-plugin-author/SKILL.md`
**Status:** approved through brainstorming on 2026-05-25; ready for implementation plan.

## Problem

There is no canonical way to scaffold an OpenRig plugin folder + `manifest.yaml`
from arbitrary local input files (NAM captures the user produced themselves,
WAV IRs they bought, etc.). Today the only path is to hand-author the manifest
or to use `openrig-tone3000-fetch` — which is tightly coupled to the tone3000
API as the source of truth.

We need a pure scaffolder that:

- Accepts files from anywhere on disk.
- Writes the OpenRig-plugins layout exactly as the gate expects.
- Stays out of git / issue / PR concerns (those are the user's, or another
  skill's, responsibility).

A follow-up ticket will refactor `openrig-tone3000-fetch` to delegate its
scaffolding step to this skill, eliminating duplicated manifest-writing logic.

## Scope (v1)

**In:**

- Kinds `nam` and `ir`.
- One plugin per invocation.
- Parameter-axis inference from filenames, mirroring the dictionary already
  documented in `openrig-tone3000-fetch`.
- Explicit `# TODO:` comments in the generated manifest when inference can't
  classify a capture's filename.
- Validation that fails before any write (extension matches kind, files exist,
  destination does not exist, `type` is in the allowed set).

**Out (explicit non-goals):**

- LV2. Skill rejects `kind=lv2` with `"lv2 not implemented yet"`. Follow-up
  ticket.
- Git, issues, branches, worktrees, PRs.
- Running the OpenRig-plugins gate (`qa_audit` / `pack_plugins`).
- Sonic verification ("does it sound right?") — forbidden by OpenRig-plugins
  LAW.
- Bulk import (>1 plugin per invocation).
- Computing `output_gain_db` — that is `loudness-audit`'s job; skill writes
  `0.0000000` placeholders.

## Input contract

All arguments arrive in the user's initial prompt. The skill does NOT run an
interactive Q&A loop. If required fields are missing, the skill prints a single
list of what's missing and stops; the user re-invokes with the full set.

| field | required | example | notes |
|---|---|---|---|
| `kind` | yes | `nam` \| `ir` | else error |
| `dest` | yes | `/abs/path/to/plugins/source` | parent dir; skill creates `<slug>/` under it |
| `files` | yes | glob or explicit list | extensions must match kind |
| `brand` | yes | `ibanez` | lowercased; hyphens allowed (`bc-rich`) |
| `display_name` | yes | `Ibanez TS808 Tube Screamer` | becomes `display_name:` |
| `type` | yes | `gain_pedal` | one of: `amp`, `body`, `cab`, `delay`, `dyn`, `filter`, `gain_pedal`, `mod`, `pitch`, `preamp`, `reverb`, `wah` |
| `source` | no | `https://www.tone3000.com/tones/66205` | repeatable; becomes `sources:` list |
| `slug` | no | `ibanez_ts808` | else derived from `brand + display_name` |

**Slug derivation** (when `slug` is omitted):

`<brand>_<display_name>` → lowercased → non-alphanumeric runs replaced with
`_` → collapsed consecutive `_` → trimmed. Example: `Ibanez` + `TS808 Tube
Screamer` → `ibanez_ts808_tube_screamer`.

## Behavior (step by step)

1. **Validate inputs.** Check required fields, `kind`, `type`, expand `files`,
   confirm each file exists, confirm extension matches kind (`.nam` for nam,
   `.wav` for ir). Collect ALL violations first (don't fail-fast on the first
   one); report them grouped by class in a single message. **No writes happen
   yet.**
2. **Derive `slug`** if not provided.
3. **Resolve target path** = `${dest}/${slug}/`. **If it exists, abort** with
   `"destination exists: <path>; pass slug=… or remove the dir"`. Refuses to
   overwrite.
4. **Create layout:**
   - `kind=nam` → `${target}/captures/`
   - `kind=ir`  → `${target}/ir/`
5. **Copy files** into that subdir, preserving original basenames. (Copy, not
   move — original lives on.)
6. **Infer parameter axes per file** using the dictionary below.
7. **Aggregate `parameters:`** — distinct axes seen across all captures, with
   the set of distinct values per axis (preserve order of first appearance).
8. **Write `manifest.yaml`** using the exact format in "Manifest output" below.
9. **Print summary** — target path, count of files copied, list of remaining
   `# TODO:` comments the user needs to resolve.

## Parameter-axis inference dictionary

Identical to the dictionary documented in `openrig-tone3000-fetch`. Applied
to each capture's filename (basename minus extension, lowercased,
token-split on `_`, `-`, space, `.`):

- **mic**: `sm57`, `sm7b`, `md421`, `re20`, `beta52`, `c414`, `r121`, `r10`,
  `m160`, `u87`
- **position**: `cap edge` → `cap_edge`, `cone edge` → `cone_edge`, `cap`,
  `cone`, `distant`, `12 inch`/`12in` → `12_inch`, `24in` → `24_inch`
- **speaker**: `upper`, `lower`
- **voicing**: `hgt`, `hg`, `normal`, `clean`, `crunch`, `lead`
- **numeric axes (regex):** `gain`, `mids`/`mid`, `bass`, `treble` followed by
  a digit — e.g. `5g`, `g5`, `mids 5`, `mids:5`

**If a capture's filename matches zero dictionary tokens**, the capture is
emitted in the manifest with a `# TODO:` comment instead of a `values:` block:

```yaml
- values: {}
  # TODO: could not infer parameter axes for "ts808_take_a"
  file: captures/ts808_take_a.nam
```

The capture is still written; the user resolves the TODO before running the
gate.

## Manifest output (per kind)

### `kind=nam`

```yaml
manifest_version: 1
id: nam_<slug>
display_name: <display_name>
brand: <brand>
output_gain_db: 0.0000000
type: <type>
backend: nam
sources:           # only emit the block if at least one source URL was passed
- <url>
parameters:
- name: <axis>
  display_name: <Title Case>
  values:
  - <v1>
  - <v2>
captures:
- values:
    <axis>: <value>
  file: captures/<basename>
```

Top-level `output_gain_db: 0.0000000` placeholder — `loudness-audit`
overwrites later.

### `kind=ir`

```yaml
manifest_version: 1
id: ir_<slug>
display_name: <display_name>
brand: <brand>
type: <type>
backend: ir
sources:           # only emit the block if at least one source URL was passed
- <url>
parameters:
- name: <axis>
  display_name: <Title Case>
  values:
  - <v1>
captures:
- values:
    <axis>: <value>
  file: ir/<basename>
  output_gain_db: 0.0000000
```

Note: for `ir`, `output_gain_db: 0.0000000` is **per capture**, not top-level.
Matches the existing pattern in `plugins/source/ir/plywood_top_bc_rich_grand_auditorium/manifest.yaml`.

### `display_name` for parameters

Each parameter's `display_name` is the axis name in Title Case
(`gain` → `Gain`, `cap_edge` → `Cap Edge`).

## Error handling

All errors abort BEFORE any file write. Single grouped message per failure
class. No partial output left on disk.

| condition | message |
|---|---|
| missing required field | `"missing required: <field1>, <field2>"` |
| `kind=lv2` | `"lv2 not implemented yet"` |
| invalid `kind` / `type` | `"invalid kind '<x>'; expected one of: nam, ir"` (same shape for type) |
| files don't exist | `"files not found: <list>"` |
| extension mismatch | `"kind=nam expects .nam files; got: <list>"` |
| destination exists | `"destination exists: <path>; pass slug=… or remove the dir"` |

## Anti-patterns (encoded in the skill)

- ❌ Writing into the user's main checkout instead of the `dest` they passed.
- ❌ Overwriting an existing destination directory.
- ❌ Computing or guessing `output_gain_db` — always `0.0000000`.
- ❌ Inferring `type` from filename or display_name — user passes it; skill
  validates against the enum.
- ❌ Silent-failure fallback to a generic `preset: 01,02,…` when inference
  misses — must emit `# TODO:` comments instead, so the gate forces the user
  to address them before merge.
- ❌ Portuguese (or any non-English) in `manifest.yaml`, in summary printed to
  user, or in any TODO comment.
- ❌ Bulk-mode (>1 plugin per invocation) — refuse with `"one plugin per
  invocation"`.

## Verification plan

The skill is markdown and runs through Claude; verification is end-to-end on a
real input set.

1. **NAM happy path** — a folder of 6+ `.nam` files with names that fully
   match the dictionary (e.g. `ts808_g0_mids5.nam`, `ts808_g5_mids5.nam`).
   Expected: clean manifest, 0 TODOs, gate runs green on the user's checkout.
2. **NAM with unrecognised filename** — pass one file whose name is opaque
   (`take_a.nam`). Expected: capture appears in manifest with explicit
   `# TODO:` comment, no axes inferred for it; other captures classified
   normally.
3. **IR happy path** — 4 `.wav` files with single-axis names
   (`cab_a.wav`, `cab_b.wav`, …). Expected: `parameters:` block with one axis
   or all TODOs (depending on the dictionary), `output_gain_db: 0.0000000`
   per capture, `ir/` subdir on disk.
4. **Destination conflict** — invoke twice with the same `slug`. Expected:
   second call aborts with the conflict message; first call's output is
   untouched.
5. **`kind=lv2`** — expect explicit "not implemented yet" message, no writes.
6. **Missing required field** — invoke without `brand`. Expected: single
   `"missing required: brand"` message, no writes.

The user's existing OpenRig-plugins checkout
(`~/Projetos/github.com/jpfaria/OpenRig-plugins`, which already has
`target/release/qa_audit` built) is the validation environment for case 1.

## Future work (out of scope here, captured for the follow-up issues)

- `lv2` kind: binaries per slot + TTLs + assets; structurally different from
  nam/ir.
- Refactor `openrig-tone3000-fetch` so its scaffolding step calls
  `openrig-plugin-author` instead of duplicating the manifest writer.
- Round-trip test fixtures (a tiny test corpus checked into this repo) once
  the skill is in steady use, to detect drift in the OpenRig-plugins manifest
  schema.
