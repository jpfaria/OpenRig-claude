---
name: openrig-plugin-author
description: "Use when the user has local NAM captures or WAV IRs on disk and wants to package them as an OpenRig plugin folder (\"create a plugin from these .nam files\", \"scaffold an IR plugin\", \"gera plugin nam para …\", \"monta a pasta do plugin\"). Validates inputs, copies files into the correct OpenRig-plugins layout, runs parameter-axis inference on filenames, and writes a draft manifest.yaml. Stays out of git, issues, PRs, and the qa_audit/pack_plugins gate — the caller owns those."
---

# openrig-plugin-author

Pure scaffolder. Input: a `kind`, some files on disk, minimal metadata.
Output: a folder under a user-supplied `dest` with the files in the right
subdir and a draft `manifest.yaml` matching what the OpenRig-plugins gate
expects.

No git. No issues. No worktrees. No `qa_audit` / `pack_plugins`. The
caller (you, the user; or a future skill that delegates here) wraps this
with the dev-flow LAW.

## Iron rules

1. **One plugin per invocation.** Refuse bulk input.
2. **Never overwrite an existing destination.** If `${dest}/${slug}/`
   exists, abort and tell the user.
3. **Never compute `output_gain_db`.** Always write `0.0000000` as a
   placeholder — `loudness-audit` overwrites later. Guessing the value
   is a methodology defect (OpenRig-plugins LAW: "validating audio by
   ear is forbidden").
4. **Never infer `type`** from filename or display_name. The user passes
   it; you validate it against the enum.
5. **On inference miss, emit `# TODO:`** in the manifest. Do not fall
   back to a generic `preset: 01,02,…` axis — that hides the gap from
   the gate.
6. **English everywhere** in the generated `manifest.yaml`, in every
   `# TODO:` comment, and in the summary printed to the user. Live chat
   stays in the user's language.

## Supported kinds (v1)

- `nam` — NAM captures (`.nam`). Files go under `${target}/captures/`.
  Manifest carries top-level `output_gain_db: 0.0000000`.
- `ir`  — WAV impulse responses (`.wav`). Files go under `${target}/ir/`.
  Manifest carries `output_gain_db: 0.0000000` **per capture**, not
  top-level.
- `lv2` — **not implemented yet**. Reject immediately with message
  `"lv2 not implemented yet"` and stop. Do NOT improvise an LV2 layout.

## Allowed `type` values

The user MUST pass `type` as one of:

`amp`, `body`, `cab`, `delay`, `dyn`, `filter`, `gain_pedal`, `mod`,
`pitch`, `preamp`, `reverb`, `wah`

Any other value: abort with
`"invalid type '<x>'; expected one of: amp, body, cab, delay, dyn, filter, gain_pedal, mod, pitch, preamp, reverb, wah"`.

## Required inputs (all in the initial prompt)

| field | required | example | notes |
|---|---|---|---|
| `kind` | yes | `nam` or `ir` | else error |
| `dest` | yes | `/abs/path/to/plugins/source` | parent dir; you create `<slug>/` under it |
| `files` | yes | glob or explicit list of paths | extensions must match `kind` |
| `brand` | yes | `ibanez` | lowercased; hyphens allowed (`bc-rich`) |
| `display_name` | yes | `Ibanez TS808 Tube Screamer` | becomes `display_name:` |
| `type` | yes | `gain_pedal` | one of the 12 above |
| `source` | no | `https://www.tone3000.com/tones/66205` | repeatable; emit a `sources:` block only if at least one was passed |
| `slug` | no | `ibanez_ts808` | else derived from `brand + display_name` |

**Missing required fields**: collect ALL violations first (don't bail on
the first one), then print a single grouped message and stop. Do NOT ask
the user follow-up questions — they re-invoke with the full set.

Example error:
```
missing required: brand, display_name
```

## Slug derivation

When `slug` is not provided, build it from `brand` + `display_name`:

1. Concatenate: `<brand>_<display_name>`.
2. Lowercase the whole thing.
3. Replace every run of non-alphanumeric characters with a single `_`.
4. Collapse consecutive `_`.
5. Trim leading/trailing `_`.

Example: `Ibanez` + `TS808 Tube Screamer` → `ibanez_ts808_tube_screamer`.

## Behavior

Execute in order. Validation (1-3) happens BEFORE any write.

1. **Validate inputs**
   - All required fields present? Else group + abort.
   - `kind ∈ {nam, ir}`? `kind=lv2` → abort with the dedicated message.
   - `type` in the allowed enum?
   - Expand `files` (glob → list). Each path exists on disk?
   - Each file's extension matches `kind` (`.nam` for nam, `.wav` for
     ir)?
2. **Derive `slug`** if not provided.
3. **Resolve target** = `${dest}/${slug}/`. If it exists, abort with
   `"destination exists: <path>; pass slug=… or remove the dir"`.
4. **Create the layout subdir**: `mkdir -p ${target}/captures` (nam) or
   `mkdir -p ${target}/ir` (ir).
5. **Copy** every input file into that subdir, keeping its original
   basename. Use `cp`, not `mv` — the originals stay where the user left
   them.
6. **Infer axes per capture** using the dictionary in the next section.
7. **Aggregate `parameters:`**: collect the distinct axes seen across
   all captures, and the distinct values per axis, preserving the order
   in which each value first appeared.
8. **Write `manifest.yaml`** at `${target}/manifest.yaml` using the
   per-kind shape in "Manifest output" below.
9. **Print a summary** to the user:
   ```
   Wrote ${target}.
   Copied N files into ${subdir}.
   Parameters: <axis>=[<values>], …
   TODOs left for you: <count>  (resolve before running the gate)
   ```

## Parameter-axis inference dictionary

**REQUIRED METHOD:** derive the `parameters:`/`captures:` block per
`openrig-manifest-parameters` (decompose each filename into the exact
controls it encodes; knobs numeric, enums string; never a flat `model`
of raw filenames, never an invented `low/mid/high` over real numeric
settings). The dictionary below only seeds token matching.

Same dictionary as `openrig-tone3000-fetch`. For each capture:

- Take the basename (no extension), lowercase it, token-split on `_`,
  `-`, space, and `.`.
- Match tokens against the classes below; a capture can match more than
  one axis.

Classes:

- **mic**: `sm57`, `sm7b`, `md421`, `re20`, `beta52`, `c414`, `r121`,
  `r10`, `m160`, `u87`
- **position**: `cap edge` → `cap_edge`, `cone edge` → `cone_edge`,
  `cap`, `cone`, `distant`, `12 inch`/`12in` → `12_inch`,
  `24in` → `24_inch`
- **speaker**: `upper`, `lower`
- **voicing**: `hgt`, `hg`, `normal`, `clean`, `crunch`, `lead`
- **numeric axes (regex)**: `gain`, `mids`/`mid`, `bass`, `treble`
  followed by a digit — e.g. `5g`, `g5`, `mids 5`, `mids:5`. Capture the
  numeric value as a string.

If a capture matches ZERO tokens, do not invent axes for it. Instead,
in the manifest emit:

```yaml
- values: {}
  # TODO: could not infer parameter axes for "<basename-without-ext>"
  file: <subdir>/<basename>
```

The capture is still in the manifest; the user fills the axes by hand
before running the gate.

## Manifest output

### `kind=nam`

```yaml
manifest_version: 1
id: nam_<slug>
display_name: <display_name>
brand: <brand>
output_gain_db: 0.0000000
type: <type>
backend: nam
sources:           # emit this block only if at least one source URL was passed
- <url>
parameters:
- name: <axis>
  display_name: <Title Case of axis>
  values:
  - <v1>
  - <v2>
captures:
- values:
    <axis>: <value>
  file: captures/<basename>
```

### `kind=ir`

```yaml
manifest_version: 1
id: ir_<slug>
display_name: <display_name>
brand: <brand>
type: <type>
backend: ir
sources:           # emit this block only if at least one source URL was passed
- <url>
parameters:
- name: <axis>
  display_name: <Title Case of axis>
  values:
  - <v1>
captures:
- values:
    <axis>: <value>
  file: ir/<basename>
  output_gain_db: 0.0000000
```

**`display_name` of each parameter** = the axis name in Title Case
(`gain` → `Gain`, `cap_edge` → `Cap Edge`).

**Quoting numeric-looking values** (e.g. `'01'`, `'5'`): wrap them in
single quotes inside YAML so they stay strings, matching the existing
manifests in `OpenRig-plugins` (see `nam/fuzz_face/manifest.yaml` for
the canonical example).

## Error handling

All errors abort BEFORE any file write. Single grouped message per
failure class. No partial output left on disk.

| condition | message |
|---|---|
| missing required field(s) | `missing required: <field1>, <field2>` |
| `kind=lv2` | `lv2 not implemented yet` |
| invalid `kind` | `invalid kind '<x>'; expected one of: nam, ir` |
| invalid `type` | `invalid type '<x>'; expected one of: amp, body, cab, delay, dyn, filter, gain_pedal, mod, pitch, preamp, reverb, wah` |
| files don't exist | `files not found: <list>` |
| extension mismatch | `kind=<k> expects .<ext> files; got: <list>` |
| destination exists | `destination exists: <path>; pass slug=… or remove the dir` |

## Anti-patterns

- ❌ Writing into the user's main OpenRig-plugins checkout when they
  asked for a worktree path. Use exactly the `dest` they passed.
- ❌ Overwriting an existing destination dir.
- ❌ Computing or estimating `output_gain_db`. Always `0.0000000`.
- ❌ Inferring `type` — the user owns that decision.
- ❌ Silent fallback to a generic `preset: 01,02,…` when inference
  misses. The `# TODO:` comment is the contract.
- ❌ Running `qa_audit`, `pack_plugins`, `git`, or `gh` inside this
  skill. That's the caller's job.
- ❌ Asking "does it sound right?" — sonic verification belongs to the
  gate (`tools/loudness_audit/src/qa.rs` in OpenRig-plugins).
- ❌ Portuguese (or any non-English) in `manifest.yaml`, in `# TODO:`
  comments, or in the summary printed to the user. Live chat stays in
  the user's language.
- ❌ More than one plugin per invocation. Refuse with
  `"one plugin per invocation"`.

## Related

- Spec: `docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md` (in this repo).
- Sibling skill: `openrig-tone3000-fetch` — discovers and downloads from
  tone3000.com. A follow-up will refactor it to delegate the
  manifest-writing step here.
- Data repo: `jpfaria/OpenRig-plugins` — holds `tools/loudness_audit`
  and `tools/pack_plugins` (the gate the manifest you scaffold must
  pass), and the canonical reference manifests under
  `plugins/source/{nam,ir}/`.
- Repo discipline for OpenRig-plugins: the `openrig-code-quality` skill
  in OpenRig-plugins (`.claude/skills/openrig-code-quality/SKILL.md`) —
  isolated `.solvers` workflow, slot invariant, English everywhere.
