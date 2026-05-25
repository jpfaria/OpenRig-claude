# openrig-plugin-author Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new skill `openrig-plugin-author` that scaffolds an OpenRig plugin folder + `manifest.yaml` from local NAM or IR input files, following the dev-flow used by previous skills in this repo (issue → worktree → PR).

**Architecture:** The deliverable is a single Markdown file: `skills/openrig-plugin-author/SKILL.md`. It instructs Claude how to validate inputs, derive a slug, copy files into the correct subdir, run the parameter-axis inference dictionary, and write the per-kind `manifest.yaml`. No executable code. Git/issue/PR concerns are out of scope for the skill itself — the user (or a future caller skill) owns them.

**Tech Stack:** Markdown (SKILL.md), GitHub CLI (`gh`) for issue/PR, Git worktrees for isolation, the user's OpenRig-plugins checkout at `~/Projetos/github.com/jpfaria/OpenRig-plugins` as the smoke-validation target.

**Spec:** `docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md`

**Out of scope here** (explicit, do NOT do):
- LV2 kind — skill must reject with "not implemented yet".
- Refactoring `openrig-tone3000-fetch` to delegate scaffolding — separate follow-up issue.
- Bumping `plugin.json` manually — the `auto-bump.yml` workflow handles version bumps after merge.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `skills/openrig-plugin-author/SKILL.md` | Create | The skill itself. Frontmatter (name + description) + body matching the spec. |
| `docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md` | (already exists, committed) | Source of truth for behavior. |

No other files. No code, no tests on disk — verification is smoke-driven in Task 4.

---

## Task 1: Open issue + isolated worktree

**Files:**
- None modified locally yet (issue lives on GitHub).

- [ ] **Step 1.1: Open the tracking issue on GitHub**

Run:
```bash
gh issue create \
  --title "skill: openrig-plugin-author — scaffold OpenRig plugin folder + manifest from local NAM/IR files" \
  --body "$(cat <<'EOF'
Adds `skills/openrig-plugin-author/SKILL.md` — a pure scaffolder that turns local NAM or IR files (+ minimal metadata: brand, display_name, type) into a valid OpenRig-plugins folder layout with a draft `manifest.yaml`.

Distinct from `openrig-tone3000-fetch`: source is local; no network, no tone3000 API. A follow-up will refactor `openrig-tone3000-fetch` so its scaffolding step delegates to this skill.

## Scope (v1)
- Kinds: `nam`, `ir`. `lv2` deferred.
- One plugin per invocation.
- Parameter-axis inference from filenames; unrecognised names emit `# TODO:` comments in the manifest.
- Zero git/issue/PR concerns inside the skill — pure scaffolder.

Spec: `docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md`
EOF
)"
```

Expected: `gh` prints the issue URL and number. Capture the number into a shell variable for the next steps:
```bash
ISSUE=<the number printed above>
```

- [ ] **Step 1.2: Comment the implementation plan on the issue**

Run:
```bash
gh issue comment "$ISSUE" --body "Worktree: .solvers/issue-$ISSUE on feature/issue-$ISSUE. Plan: docs/superpowers/plans/2026-05-25-openrig-plugin-author.md. Executing now."
```

Expected: comment URL printed.

- [ ] **Step 1.3: Create an isolated worktree using the using-git-worktrees skill**

Invoke `superpowers:using-git-worktrees` to create:
- Worktree path: `.solvers/issue-$ISSUE`
- Branch: `feature/issue-$ISSUE`
- Base: `main`

Falling back to native git if the skill is not available:
```bash
git worktree add ".solvers/issue-$ISSUE" -b "feature/issue-$ISSUE" main
cd ".solvers/issue-$ISSUE"
```

Expected: worktree directory exists; `git status` inside it reports `On branch feature/issue-$ISSUE`. All remaining steps run **inside that worktree**.

---

## Task 2: Author `SKILL.md`

**Files:**
- Create: `skills/openrig-plugin-author/SKILL.md`

- [ ] **Step 2.1: Create the skill directory**

Run (from inside the worktree):
```bash
mkdir -p skills/openrig-plugin-author
```

- [ ] **Step 2.2: Write the SKILL.md with the exact content below**

Create `skills/openrig-plugin-author/SKILL.md` containing:

````markdown
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
````

- [ ] **Step 2.3: Commit the skill**

Run:
```bash
git add skills/openrig-plugin-author/SKILL.md
git commit -m "feat(skill): openrig-plugin-author — scaffold OpenRig plugin folder from local NAM/IR files

Pure scaffolder. Input: kind (nam|ir), local files, brand, display_name,
type, dest. Output: folder under dest with files in the right subdir and
a draft manifest.yaml. lv2 deferred to a follow-up.

Spec: docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md"
```

Expected: one commit on `feature/issue-$ISSUE`. `git log --oneline -1` shows the message.

---

## Task 3: Comment progress on the issue

**Files:**
- None.

- [ ] **Step 3.1: Comment the push on the issue**

Run:
```bash
SHA=$(git rev-parse --short HEAD)
gh issue comment "$ISSUE" --body "Push $SHA: SKILL.md authored at skills/openrig-plugin-author/SKILL.md. Smoke validation next."
```

Expected: comment URL printed.

---

## Task 4: Smoke-validate against the user's checkout

The skill is markdown, so "running" it means: invoke it in a fresh
Claude session with concrete arguments, observe the on-disk result, and
diff against expectation. This is a manual end-to-end test the engineer
runs from a Claude session that has the updated `openrig` plugin loaded
(after `/reload-plugins`).

For each scenario below, the engineer prepares the fixture under
`/tmp/plugin-author-smoke/`, invokes the skill, and confirms the
on-disk effects match expectations. Each scenario gets a comment on the
issue with the result.

**Common setup:**
```bash
rm -rf /tmp/plugin-author-smoke
mkdir -p /tmp/plugin-author-smoke/inputs
mkdir -p /tmp/plugin-author-smoke/dest
```

`dest` for every scenario below is `/tmp/plugin-author-smoke/dest`.

- [ ] **Step 4.1: NAM happy path — full inference**

Prep three real NAM files with names that fully match the dictionary
(any real `.nam` from the user's existing
`OpenRig-plugins/plugins/source/nam/*/captures/` works — just copy):
```bash
cp ~/Projetos/github.com/jpfaria/OpenRig-plugins/plugins/source/nam/fuzz_face/captures/dunlop_eric_johnson_fuzz_01.nam \
   /tmp/plugin-author-smoke/inputs/ts808_g5_mids5.nam
cp ~/Projetos/github.com/jpfaria/OpenRig-plugins/plugins/source/nam/fuzz_face/captures/dunlop_eric_johnson_fuzz_02.nam \
   /tmp/plugin-author-smoke/inputs/ts808_g10_mids5.nam
cp ~/Projetos/github.com/jpfaria/OpenRig-plugins/plugins/source/nam/fuzz_face/captures/dunlop_eric_johnson_fuzz_03.nam \
   /tmp/plugin-author-smoke/inputs/ts808_g0_mids5.nam
```

(Renaming on copy is intentional — gives the skill recognisable axis
tokens.)

Invoke the skill (in the fresh Claude session) with the natural-language
prompt:
> "Use openrig-plugin-author: kind=nam, dest=/tmp/plugin-author-smoke/dest, files=/tmp/plugin-author-smoke/inputs/*.nam, brand=ibanez, display_name='Ibanez TS808 Tube Screamer', type=gain_pedal"

Expected on-disk:
```
/tmp/plugin-author-smoke/dest/ibanez_ts808_tube_screamer/
├── captures/
│   ├── ts808_g0_mids5.nam
│   ├── ts808_g10_mids5.nam
│   └── ts808_g5_mids5.nam
└── manifest.yaml
```

Expected `manifest.yaml` properties (verify by reading it):
- `id: nam_ibanez_ts808_tube_screamer`
- `display_name: Ibanez TS808 Tube Screamer`
- `brand: ibanez`
- `output_gain_db: 0.0000000` at top level
- `type: gain_pedal`
- `backend: nam`
- `parameters:` lists `gain` and `mids` axes
- `captures:` has 3 entries, each with `values: { gain: '<n>', mids: '<n>' }` and `file: captures/<basename>`
- ZERO `# TODO:` comments

Verify:
```bash
cat /tmp/plugin-author-smoke/dest/ibanez_ts808_tube_screamer/manifest.yaml
grep -c '# TODO' /tmp/plugin-author-smoke/dest/ibanez_ts808_tube_screamer/manifest.yaml
# Expected: 0
```

If any expectation fails, edit `skills/openrig-plugin-author/SKILL.md`
to fix the instruction that caused the drift, commit, push, and re-run
this step before moving on.

- [ ] **Step 4.2: NAM with one unrecognised filename → TODO comment**

```bash
rm -rf /tmp/plugin-author-smoke/dest/ibanez_ts808_take_a
cp ~/Projetos/github.com/jpfaria/OpenRig-plugins/plugins/source/nam/fuzz_face/captures/dunlop_eric_johnson_fuzz_01.nam \
   /tmp/plugin-author-smoke/inputs/take_a.nam
```

Invoke:
> "openrig-plugin-author: kind=nam, dest=/tmp/plugin-author-smoke/dest, files=/tmp/plugin-author-smoke/inputs/take_a.nam /tmp/plugin-author-smoke/inputs/ts808_g5_mids5.nam, brand=ibanez, display_name='Ibanez TS808 Take A', type=gain_pedal"

Expected: manifest contains the `ts808_g5_mids5.nam` capture with axes
inferred, AND the `take_a.nam` capture with a `# TODO: could not infer
parameter axes for "take_a"` line.

Verify:
```bash
TARGET=/tmp/plugin-author-smoke/dest/ibanez_ts808_take_a
grep -q '# TODO: could not infer parameter axes for "take_a"' "$TARGET/manifest.yaml"
echo $?  # Expected: 0
```

- [ ] **Step 4.3: IR happy path**

```bash
rm -rf /tmp/plugin-author-smoke/dest/bc_rich_plywood_top
cp ~/Projetos/github.com/jpfaria/OpenRig-plugins/plugins/source/ir/plywood_top_bc_rich_grand_auditorium/ir/*.wav \
   /tmp/plugin-author-smoke/inputs/
```

Invoke:
> "openrig-plugin-author: kind=ir, dest=/tmp/plugin-author-smoke/dest, files=/tmp/plugin-author-smoke/inputs/*.wav, brand=bc-rich, display_name='Plywood Top BC Rich Grand Auditorium', type=body"

Expected on-disk:
```
/tmp/plugin-author-smoke/dest/bc-rich_plywood_top_bc_rich_grand_auditorium/
├── ir/
│   └── *.wav (4 files)
└── manifest.yaml
```

Note: slug includes `bc-rich_` because hyphens in brand are preserved.

Expected manifest properties:
- `backend: ir`
- NO top-level `output_gain_db`
- Each capture has `output_gain_db: 0.0000000` inline
- `file:` paths start with `ir/`

Verify:
```bash
TARGET=/tmp/plugin-author-smoke/dest/bc-rich_plywood_top_bc_rich_grand_auditorium
grep -c '^output_gain_db:' "$TARGET/manifest.yaml"  # Expected: 0 (no top-level)
grep -c 'output_gain_db: 0.0000000' "$TARGET/manifest.yaml"  # Expected: 4 (one per capture)
```

- [ ] **Step 4.4: Destination conflict refusal**

Without removing the dir from Step 4.3, re-invoke the same prompt.

Expected: skill aborts with a message containing `destination exists:`
and does not modify any file under
`/tmp/plugin-author-smoke/dest/bc-rich_plywood_top_bc_rich_grand_auditorium/`.

Verify: file mtimes inside the target dir are unchanged from Step 4.3
(`stat` them before and after, or trust the visible behaviour in the
chat).

- [ ] **Step 4.5: `kind=lv2` rejection**

Invoke:
> "openrig-plugin-author: kind=lv2, dest=/tmp/plugin-author-smoke/dest, files=/tmp/plugin-author-smoke/inputs/*.nam, brand=foo, display_name='Foo', type=gain_pedal"

Expected: skill prints `lv2 not implemented yet` and stops. No directory
created.

Verify:
```bash
ls /tmp/plugin-author-smoke/dest/ | grep -c foo
# Expected: 0
```

- [ ] **Step 4.6: Missing required field**

Invoke (deliberately omit `brand` and `display_name`):
> "openrig-plugin-author: kind=nam, dest=/tmp/plugin-author-smoke/dest, files=/tmp/plugin-author-smoke/inputs/*.nam, type=gain_pedal"

Expected: skill prints a single line like
`missing required: brand, display_name` and stops. No directory created.

- [ ] **Step 4.7: Comment smoke results on the issue**

Run:
```bash
gh issue comment "$ISSUE" --body "$(cat <<EOF
Smoke results vs /tmp/plugin-author-smoke/:

- 4.1 NAM happy path → PASS / FAIL (note: …)
- 4.2 NAM unrecognised → TODO comment present → PASS / FAIL
- 4.3 IR happy path → PASS / FAIL
- 4.4 Destination conflict → refused as expected → PASS / FAIL
- 4.5 kind=lv2 → rejected → PASS / FAIL
- 4.6 missing required → grouped error → PASS / FAIL

Any skill edits during this step were committed and pushed before opening the PR.
EOF
)"
```

Fill in PASS/FAIL accurately. If any scenario was FAIL, fix the skill,
commit, push, then re-run the affected scenarios before continuing.

---

## Task 5: Push, open PR

**Files:**
- None.

- [ ] **Step 5.1: Push the branch**

Run:
```bash
git push -u origin "feature/issue-$ISSUE"
```

Expected: branch pushed; `gh` prints the new branch URL.

- [ ] **Step 5.2: Open the PR**

Run:
```bash
gh pr create --base main --head "feature/issue-$ISSUE" \
  --title "skill: openrig-plugin-author" \
  --body "$(cat <<EOF
## Summary

Adds the \`openrig-plugin-author\` skill — scaffolds an OpenRig plugin
folder (\`plugins/source/<kind>/<slug>/\`) with a draft \`manifest.yaml\`
from local NAM captures or WAV IRs.

Pure scaffolder. No git, no issues, no PRs, no \`qa_audit\` /
\`pack_plugins\` inside the skill. The caller (user, or a future skill
that delegates here) handles the dev-flow wrapper.

## Scope

- Kinds: \`nam\`, \`ir\`. \`lv2\` deferred — skill rejects with a clear
  message and a pointer to the follow-up.
- One plugin per invocation; refuses bulk.
- Parameter-axis inference via the dictionary already documented in
  \`openrig-tone3000-fetch\` (mic / position / speaker / voicing /
  numeric \`g5\` / \`mids 5\` / etc.).
- Inference misses are emitted as explicit \`# TODO:\` YAML comments
  the user must resolve before running the gate.
- Validation collects ALL violations and aborts BEFORE any write — no
  partial output on disk.

## Smoke

Validated end-to-end against the user's OpenRig-plugins checkout:

- NAM happy path: 3 captures, full inference, 0 TODOs.
- NAM with one unrecognised filename: explicit \`# TODO:\` comment
  emitted; other captures classified normally.
- IR happy path: per-capture \`output_gain_db: 0.0000000\` (not
  top-level), files under \`ir/\`.
- Destination conflict: refused with clear message, no overwrite.
- \`kind=lv2\`: rejected; nothing written.
- Missing required field: grouped error; nothing written.

## Out of scope, captured as follow-ups

- LV2 kind: structurally different (binaries per slot + TTLs +
  assets). Separate ticket.
- Refactor \`openrig-tone3000-fetch\` to delegate its scaffolding step
  to this skill. Separate ticket; will eliminate duplicated
  manifest-writing logic.

Closes #$ISSUE.

Spec: \`docs/superpowers/specs/2026-05-25-openrig-plugin-author-design.md\`
Plan: \`docs/superpowers/plans/2026-05-25-openrig-plugin-author.md\`
EOF
)"
```

Expected: `gh` prints the PR URL.

- [ ] **Step 5.3: Comment the PR URL on the issue and close the loop**

Run:
```bash
PR_URL=$(gh pr view --json url -q .url)
gh issue comment "$ISSUE" --body "PR opened: $PR_URL"
```

Expected: comment URL printed; the PR is now waiting for the user's review/merge.

---

## Self-Review

**1. Spec coverage:**

- Input contract (kind, dest, files, brand, display_name, type, source, slug) → Step 2.2 (skill body table).
- Slug derivation rules → Step 2.2 ("Slug derivation" section).
- Behavior steps 1-9 → Step 2.2 ("Behavior" section), mirrored from the spec.
- Parameter-axis inference dictionary → Step 2.2 ("Parameter-axis inference dictionary" section).
- Manifest output per kind (top-level vs per-capture `output_gain_db`) → Step 2.2 ("Manifest output" section); smoke-verified in Steps 4.1 and 4.3.
- Error table (missing/lv2/invalid/files-missing/ext-mismatch/dest-exists) → Step 2.2 ("Error handling" section); smoke-verified in Steps 4.4, 4.5, 4.6.
- Anti-patterns → Step 2.2 ("Anti-patterns" section).
- Verification plan (6 scenarios in the spec) → 6 sub-steps under Task 4.

No spec section is uncovered.

**2. Placeholder scan:** No TBD/TODO/"fill in details"/"add error handling" left in the plan. The `# TODO:` strings inside Step 2.2's skill content are part of the literal SKILL.md text, not plan-level placeholders — those are intentional.

**3. Type / name consistency:**
- Skill name `openrig-plugin-author` used uniformly across header, file paths, issue title, commit message, PR title.
- Manifest field names match what the spec dictates (`manifest_version`, `id`, `display_name`, `brand`, `type`, `backend`, `sources`, `parameters`, `captures`, `output_gain_db`).
- Allowed `type` enum is identical in skill body, error message, and spec.
- Issue number variable is `$ISSUE` throughout; branch is `feature/issue-$ISSUE`; worktree is `.solvers/issue-$ISSUE` throughout.

No drift to fix.
