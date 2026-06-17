---
name: openrig-tone-builder
description: "Use when the user asks for a tone, timbre, or preset for a specific song or artist (\"timbre da Duality\", \"preset do Slipknot\", \"tom da [música]\", \"recreate the [song] sound\", \"build a [artist] preset\"). Researches the original signal chain, maps it to OpenRig blocks, and saves it as a NAMED PRESET in the chain's bank — adding a NEW slot via `apply_rig_nav Preset(-1)`, never overwriting existing presets. ALWAYS asks the user once up front whether to commit via the live MCP rig or as a YAML file only."
---

# OpenRig Tone Builder

Build a faithful tone for a real-world song/artist as a **named preset on
a new slot in an existing chain's bank**. Default path drives the OpenRig
MCP server (audible immediately on the live rig); an alternate path
writes a YAML file only. The agent **MUST ask the user which path before
touching anything** — see Step −1.

## Chain vs preset vs slot — read this before anything else

**A chain is a top-level group in the rig** (e.g. "Electric Guitar",
"Acoustic", "Bass"). Owns the I/O wiring and an instrument tag.
**Where this preset lives — which chain, or a brand-new one — is
always the user's call** (see **Step 3.1**). This skill may call
`add_chain` when the user explicitly opts in; it never picks or
creates a chain on its own.

**A chain has a BANK of preset slots.** Each slot holds one named preset
(the FX layout for one tone). Slots are referenced by index, the preset's
*display name* lives in `RigPreset.name`, the bank stores `slot → key`.
The user switches between slots at runtime to swap tones live.

**A preset is the FX layout for ONE tone**, stored in one slot of a
chain's bank. Examples: "Clocks — Coldplay (rhythm)", "Clocks — Coldplay
(lead)", "Gravity — John Mayer (solo)". One chain can hold many presets.

> "Look for the preset, not the chain." Your job is to write a
> **preset**. The chain is just the rig slot it lives in.

This skill **only ever creates or updates presets**. Crucially, it
**adds a NEW slot to the chain's bank** for the preset — it does **NOT**
edit the chain's currently-loaded blocks (that would destroy the user's
existing active preset). See Step 3.

**Before doing anything else, check whether a preset for this song already
exists.** Overwriting tone work the user spent time on is the worst-case
failure mode for this skill. See Step 0 of the workflow.

## ⛔ VALIDATION GATE — decide the validation MODE before you validate (read this first)

**The single most load-bearing decision in this whole skill is what
KIND of reference the user gave you**, because it decides whether the
analyzer's `match_score` measures *timbre* (a real score you can chase)
or *note content* (a number that lies). Get this wrong and you produce
the documented "Gravity" failure — a muffled, quiet preset with a
fabricated 865 ms delay, "validated" by a score that was structurally
incapable of converging. **Answer this question before you render
anything:**

> **Is the reference (a) a REAMP of the SAME bundled DI, or (b) a REAL
> recording?**

**(a) Same-DI reamp** — the reference is OpenRig's bundled DI
(`<openrig-source-root>/assets/audio/input.wav`) re-amped through real
gear: **same notes, same timing, same performance, only the tone
differs.** → `render(bundled DI) → compare → match_score` is a **valid
timbre score**: both signals carry identical note content, so every
delta the analyzer measures IS a tone delta. **Validation Mode A** —
run the render→compare loop (Step 6 Mode A) and chase convergence; the
analyzer is the primary validator.

**(b) Real recording** — an isolated studio/live stem, a commercial
mix, a cover, a different take: **ANY performance that is NOT the
bundled DI re-amped.** → rendering the bundled DI and comparing it to
that recording compares **two different performances**. The analyzer
now scores *note content, dynamics and silence* — different notes,
different timing, gaps where one has sound and the other doesn't — **not
timbre.** `match_score` **cannot converge on tone**, and iterating to
raise it actively breaks the preset (the real "Gravity" stem was sparse
sustained low notes + silence → centroid ~480 Hz → the loop low-passed
to 750 Hz and matched the quiet RMS → muffled and quiet). **Validation
Mode B** — `match_score` is **demoted to a directional hint at most:
never a judge, never a gate, never something to iterate against.** The
**primary validator is the EAR, with the user in the loop** (Step 6
Mode B).

**If you cannot positively establish a same-DI reamp, you are in Mode
B.** The bundled DI is one specific file; a user's "isolated stem of the
song" is, by default, a real recording → Mode B. When you don't know,
**ask once**: *"is this stem a reamp of OpenRig's bundled DI, or a real
recording of the song? It changes how I validate."* Default to Mode B if
they don't know. *(render in the user's language at runtime)*

**Either way the render+compare is still MANDATORY when a reference
exists** — it is never a closing nicety, and saving a preset with no
validation pass at all is saving a blind guess (the Clocks v1 failure).
What changes between modes is **who the judge is**: the analyzer
(Mode A) or the ear + user (Mode B, with the analyzer's *normalized
spectral shape* as a directional guide — see Step 6 Mode B). You may NOT
declare the preset done until you have run the mode-appropriate loop and
either converged (Mode A) or gotten the user's ear sign-off (Mode B).

If the user explicitly says they have **no reference at all**, declare
that **out loud in the chat** before Step 8 (`save_chain_preset`) — "no
reference provided, this preset is a research-only guess; I cannot
validate it" — so the user can decide whether to provide one or accept
the limitation. Silent skipping = failure of the skill.

The DI path is `<openrig-source-root>/assets/audio/input.wav`. Not
`assets/sound/`, not `~/Music/`, not a fresh user-supplied DI. This
one file. You never ask the user for a DI; only the *wet reference*
comes from them. If it is missing from the OpenRig repo, that is a bug
in the repo — stop and tell the user, do not improvise.

### Level is NOT timbre — never match the reference's RMS

In **both** modes, the preset's **output level is always maximized for
the stage** (the loudness law, Step 7) — it is **never** matched to the
reference's RMS. A real reference is often quiet (soft playing, gaps,
mastering headroom); matching its RMS ships a broken-feeling quiet
preset. Loudness is decided by Step 7's maximize-without-clipping pass
on the output-trim block alone, **independently of the reference**. Any
`match_score`/`diff.json` recommendation about RMS or level is a
**level** recommendation and is **ignored** for tone purposes — Step 7
owns level. (This resolves the only apparent conflict between Step 6 and
Step 7: Step 6 never touches level, Step 7 always maximizes it.)

## Step −1 — Ask the user: MCP live or YAML file only?

Before touching anything, ask **once** which persistence path the user
wants. Both paths are valid; the right choice depends on whether
OpenRig is running:

> "For this preset, I'll go: **(a) via MCP on the live rig** (new slot
> in the bank, audible immediately — requires OpenRig with `--mcp`), or
> **(b) YAML file only** (I'll write to
> `<openrig-user-data-root>/presets/<name>.yaml`, without touching the
> rig)?" *(render in the user's language at runtime — this English
> template documents the structure, not the literal words to ship)*

* If **(a) MCP** — confirm the MCP tools are wired (precondition below)
  and follow the **MCP workflow**.
* If **(b) file** — skip the MCP precondition and follow the **File-only
  workflow** at the bottom. On this path the **ONLY MCP calls allowed
  are reads of the resources `openrig://plugins`, `openrig://project`,
  and `openrig://plugins/{id}/params`** (used by **Step 1b** for
  installedness + schema lookup without mutating the rig). **Every
  other MCP call is forbidden** — that includes mutations (`add_block`,
  `save_chain_preset`, `apply_rig_nav`, `set_block_parameter_*`, etc.)
  AND non-mutating tools (e.g. `reload_plugin_catalog`,
  `register_recent_project`, `start_midi_learn`, `set_language`,
  `set_compact_view_enabled`). Allowlist, not blocklist.
* If the user does not answer, default to **(a) MCP** but only after the
  precondition check passes; if the MCP server is offline, fall back to
  asking again rather than silently writing a file.

## Step 0a — Persistent evaluation directory (BEFORE Step 0)

Everything this skill produces during a build — the analyzer
fingerprints, the renders, the compare diffs, the per-iteration preset
snapshots, the iteration log — must land under a **per-song persistent
directory** so it survives a `/tmp/` wipe, a reboot, a machine
migration, or simply "let me re-validate this preset next month
against the same reference".

### Resolve the evaluations directory via MCP, once, at the top of Step 0a

Read the OpenRig MCP resource `openrig://paths` (added in #582). It
returns the user's effective resolved system paths as JSON:

```jsonc
{
  "data_root": "/Users/.../Library/Application Support/OpenRig",
  "presets_path": "/Users/.../presets",
  "plugins_path": "/Users/.../plugins",
  "evaluations_path": "/Users/.../evaluations"
}
```

Use `evaluations_path` as the root for every artifact this skill
writes — that field already honours the user's override from
`Settings → System → Paths` (or the OS default when no override is
set). Treat it as `<openrig-evaluations-root>` everywhere below. Do
NOT hardcode any per-OS path here; `openrig://paths` is the single
source of truth.

`/tmp/openrig-analyzer/<ts>/` and `/tmp/openrig-render/` are volatile
working directories used by the underlying analyzer and render
binaries — they are NOT the home of the evaluation. Pass
`--out-dir <openrig-evaluations-root>/<song-slug>/` when invoking
them so outputs land where they belong from the start; never let
results sit in `/tmp/` after the call returns. Saving a preset to
`<openrig-user-data-root>/presets/<name>.yaml` while the matching
fingerprint, ref WAV, render, and diff sit in `/tmp/` is an
evaluation with no context — there's no way to re-compare an old
preset version, to see score evolution across iterations, or to A/B
a tweak against the same historic reference.

### Compute the `<song-slug>` and create the directory

`<song-slug>` is derived deterministically from `"<song> - <artist>"`
(or `"<song> - <artist> (<role-group>)"` when the user clearly groups
multiple roles into one build):

- Lowercase.
- Strip accents (`é → e`, `ã → a`, `ü → u`, etc.).
- Replace any run of non-`[a-z0-9]` with a single `-`.
- Trim leading/trailing `-`.

The result is a kebab-case filesystem-safe slug. Keep it stable across
re-builds of the same song — the slug is the directory key.

Create (or reuse) `<openrig-evaluations-root>/<song-slug>/` with this
structure (placeholders only — substitute the actual `<song-slug>`,
`<role>`, and iteration number `<N>` at build time, never echo a
literal song/artist from this skill text):

```text
<openrig-evaluations-root>/<song-slug>/
├── eval.md                       # human-readable iteration log
├── refs/
│   ├── <role>.wav                # copy of user's reference WAV (sha256 verified)
│   └── <role>.wav                # one per role provided
├── fingerprints/
│   └── ref-<role>.json           # one per role
├── renders/
│   ├── <role>-v1.wav             # one per iteration
│   └── <role>-v2.wav
├── diffs/
│   ├── <role>-v1.json            # compare.py output per iteration
│   └── <role>-v2.json
└── presets/
    ├── <role>-v1.yaml            # snapshot per iteration
    ├── <role>-v2.yaml
    └── <role>-final.yaml         # the version the user accepted
```

### Reuse vs first-build

- **If `<openrig-evaluations-root>/<song-slug>/` already exists**, READ
  `eval.md` before doing anything else. It tells you: prior iteration
  count, last `match_score`, prior status (`done` / `iterating` /
  `abandoned`), the gear mapping that was used, and any methodology
  notes. Continue iteration numbering from the last `<role>-v<N>` in
  `presets/` — never overwrite an existing `<role>-v<N>.yaml`.
- **If it does not exist**, create it fresh. Initialise `eval.md` from
  the template below.
- **Never `rm -rf` an existing `<song-slug>/` to "start clean"** — the
  prior renders, diffs, and per-iter YAML snapshots are the user's
  audit trail. If something is genuinely corrupted, ask the user
  before deleting; otherwise continue iteration numbering after the
  last existing `<role>-v<N>`.

The `refs/` subdir specifically exists so **Step 8 (re-evaluation)
remains possible months later** — the persistent ref is the only
thing that makes "compare this preset to the same reference next
year" tractable. Skipping `refs/` on a fresh build amputates Step 8
for that song; do not.

### Copy the user's reference WAVs (do NOT symlink)

For every reference WAV the user provided:

1. Compute the source file's sha256.
2. `cp` (do NOT `ln -s`) it to
   `<openrig-evaluations-root>/<song-slug>/refs/<role>.wav`. Symlinks
   break under `/tmp/` cleanup, external-drive unplug, and machine
   migration — the entire point of this directory is portability.
3. Re-compute the destination sha256 and verify it matches the source.
   If it doesn't, STOP — surface the mismatch to the user instead of
   continuing with a corrupted reference.
4. If `refs/<role>.wav` already exists from a prior build, compare
   sha256s first. **Same hash** → reuse, log "ref unchanged" in
   `eval.md`. **Different hash** → ask the user once whether this is
   a deliberate ref swap (rare — e.g. they got a cleaner stem) or a
   mistake (path collision with a different song's `<role>`). Never
   silently overwrite a reference the prior iterations were compared
   against.

### `eval.md` template

Initialise on first build by **substituting** every `<placeholder>`
with the live build value (the literal song title, artist, slug,
chain id, etc. from the user's actual request and the rig's actual
state). The skeleton below uses placeholders because **this skill
text** doesn't know the song; **your eval.md** must end up with real
values, never the literal string `<Song>` or `<Artist>` or
`<chain id>`:

```markdown
# <Song> — <Artist>
**Status:** iterating
**Date:** <YYYY-MM-DD>
**Chain:** <chain display name> (<chain id>)
**Slots:** <role>=<slot index>, <role>=<slot index>

## Gear research
- <bullet list of researched gear + era + sources>

## Mapping
| Real | OpenRig |
| ---- | ------- |
| <real-gear> | <model_id> |

## Iteration log
### <role>
| iter | match_score | RMS Δ | centroid Δ | key change    |
| ---- | ----------- | ----- | ---------- | ------------- |
| v1   | <score>     | <dB>  | <Hz>       | baseline      |
| v2   | <score>     | <dB>  | <Hz>       | <key change>  |

## Methodology notes
- <session-specific notes>

## Sources
- <URLs>
```

Update `Status:` to `done` when the user accepts the preset, or
`abandoned` if the user walks away. Leave at `iterating` between
iterations.

### Optional: `<openrig-evaluations-root>/INDEX.md`

If a global index doesn't exist, create one on first add. Append a
row whenever you finish (or re-evaluate) an evaluation. Columns:
`<song-slug>`, `<song>`, `<artist>`, best `match_score`, last date,
status. The index is a navigation aid; do not duplicate `eval.md`
content in it.

## Step 0 — Fingerprint the reference audio FIRST (when WAVs are provided)

If the user provided ANY reference WAV (isolated stem, full mix,
multiple stems), invoke the **`openrig:openrig-tone-analyzer` skill on
each WAV before research, before gear mapping, before any MCP call**.
The fingerprint is a **primary input for tonal SHAPE** (where the energy
sits across the band) — it shapes the EQ direction; research fills in
what the signal cannot reveal (specific amp model/era, brand of pedal)
**and** the delay/reverb the fingerprint cannot measure reliably. Going
straight to research is a common failure mode — it biases the preset
toward what "sounds right on paper". But the **opposite** failure is
just as real: **over-trusting fragile fingerprint fields** (`centroid`,
`RMS`, `time_fx`) on a sparse or separated stem. Read the caveat below
before you treat any single number as truth.

How:

1. For each reference WAV the user mentioned, invoke
   `openrig:openrig-tone-analyzer` with the file path. The skill writes
   a JSON fingerprint plus spectrogram PNGs to disk and returns the
   paths. The JSON carries `centroid`, `rolloff`, `band_energy`,
   `gain_character`, `time_fx` (delay/reverb estimates) and `source.kind`
   (rhythm/lead/solo/clean — often inferred from filename).
2. **Read every fingerprint JSON before opening any research URL.** The
   fingerprint tells you:
   - EQ **shape** to lean toward (centroid + band_energy → parametric EQ
     direction — a hint cross-checked against the spectrogram + ear, not
     a hard target; see reliability caveat below)
   - Gain stage (gain_character → clean / crunch / high gain)
   - Time effects — **low-confidence, do NOT set blocks from these**;
     `time_fx` (delay time/feedback, reverb type) is artifact-prone, so
     delay/reverb come from research + ear (Step 2, Step 6 Mode B)
   - Role hint (source.kind → which preset name to use, and whether
     to split into multiple presets)
3. If multiple stems were provided (rhythm + lead, or several solos),
   fingerprint **each one separately** — they produce different presets
   and the analyzer captures that.
4. **Persist each fingerprint into the per-song evaluation directory.**
   After the analyzer skill writes its JSON to its scratch dir (today
   `/tmp/openrig-analyzer/<unix_ts>/`), `cp` the JSON to
   `<openrig-evaluations-root>/<song-slug>/fingerprints/ref-<role>.json`.
   The scratch path is volatile; the persistent copy is what every
   later iteration (and any future re-evaluation per Step 8) compares
   against. If `ref-<role>.json` already exists from a prior build,
   overwrite **only when the ref WAV's sha256 also matches** (Step 0a
   already gated the ref-WAV swap question — same gate covers the
   fingerprint).

If the user provided **no** reference audio, skip Step 0 and declare
out loud in the chat: "no reference WAV provided — Step 0 (analyzer
fingerprint) skipped, this preset will be research-only and cannot be
validated objectively". The user can then choose to provide a WAV or
accept the limitation.

### ⛔ Fingerprint reliability caveat — which fields lie, and when

Not every fingerprint field is equally trustworthy. **A sparse stem**
(mostly silence + a few sustained notes), a **source-separated stem**
(bleed, artifacts from the separation), or a **leaky/full mix** distorts
the scalar fields. Treat them by tier:

| Field | Trust | How to use it |
|---|---|---|
| `band_energy` / normalized **LTAS shape** over signal-bearing windows | **Usable as SHAPE** | Directional EQ guide ("more energy 2–4 kHz") — cross-check against spectrogram + ear. Never a hard target. |
| `centroid` | **Fragile** | On a sparse/separated stem it tracks *which notes were held*, not timbre. Do not low-pass off a low centroid; confirm against the spectrogram + ear. |
| `RMS` / loudness | **Never a target** | Reflects performance dynamics + mastering, not tone. Level is maximized in Step 7, never matched to the ref. |
| `time_fx` (delay/reverb) | **Low-confidence** | Artifact-prone (reverb tail → "long delay"; hall → "spring"). Delay/reverb come from research + ear (Step 2, Step 6 Mode B), not from this field. |
| `gain_character` / `tone_profile` | Usable | Clean/crunch/high-gain class is robust. |

**The cross-check is always: spectrogram PNG + your ear, not the scalar
alone.** When a number and the spectrogram/ear disagree, the
spectrogram + ear win. This is the structural reason Mode B (real
recording) validates by ear: the scalars that *would* let a machine
judge are exactly the ones a real, sparse, or separated reference
corrupts.

### ⛔ HARD RULE — no suppositions about what the reference contains

> Every claim about what is IN the user's reference WAV must cite a
> **fingerprint field** (or a directly readable artefact: spectrogram
> PNG, `analysis.pdf`, the raw waveform). **Cultural priors about the
> song / artist / era / genre are NOT evidence about THIS specific
> WAV.** If the fingerprint doesn't measure something, you don't know
> it — say so explicitly.

**Always forbidden** (even in chat narration, even in casual asides,
even when explaining why the wet doesn't match the ref):

- Claiming a **playing technique** that no fingerprint field measures.
  The fingerprint exposes `tone_profile` (clean / crunch / distortion /
  high_gain), `dynamics_profile` (sparse / rhythmic / sustained),
  `presence`, `loudness`, `spectrum`, `distortion`, `time_fx`. It does
  **not** measure palm-mute, fingerpicking, alternate picking, sweep
  picking, tapping, hybrid picking, arpeggios, chugging, or strumming
  pattern. Saying "heavy palm-mute" / "clean fingerpicking" /
  "typical Edge arpeggios" about the user's WAV is **fabrication**
  unless you can point at a specific waveform or spectrogram detail
  that supports it (and even then, label it "consistent with X", not
  "the WAV is X").
- Inferring content from the **song title** ("the Metallica riff
  obviously has palm-mute"), the **artist** ("Edge uses dotted-eighth
  delay"), the **album/era** ("that U2 phase was clean arpeggios"),
  or **memory of how the song sounds in your head**. The user's WAV is
  what the user's WAV is — it might be a cover, a stem isolated
  imperfectly, a different section than you expect, a live take, or a
  remix. Cultural priors belong in **research** (Step 1, which fills
  *gaps* the fingerprint cannot reveal — gear models, era, recording
  context), NOT in claims about what the reference WAV contains.
- Inventing differences between the bundled DI and the user's
  reference to explain a low match_score ("the DI is clean
  fingerpicking and Moisés played palm-mute, so the difference is
  technique"). That shifts blame to fabricated technique mismatch
  instead of admitting the preset's tone gap. If you observe a real
  gap, name it via fingerprint deltas (`centroid Δ`, `band_energy Δ`,
  `THD Δ`, `time_fx`) — never via guessed performance differences.

**How to phrase claims correctly** — pair every observation with its
fingerprint citation:

- ✅ "section 2 of the ref has `tone_profile: high_gain` (conf 0.88)
  and `dynamics_profile: rhythmic` — my render came out `crunch` in
  the same window, THD deficit ~7%."
- ✅ "I cannot assert the player's technique from the fingerprint —
  the analyzer does not measure palm-mute or fingerpicking. What I
  can see is `dynamics_profile: rhythmic` and a high onset rate."
- ❌ "Moisés is probably playing heavy palm-mute, that's why the
  sound is more compressed." (Fabricated technique + attributed cause
  without evidence.)
- ❌ "the Metallica riff needs palm-mute, so the gap is because of
  that." (Cultural prior about Metallica + technique fabrication.)

**Red Flag self-check before sending any chat message about the
reference**: "I'm claiming that the user's WAV CONTAINS X. Can I paste
the fingerprint field that shows X? If not, REWRITE — replace with
'the fingerprint shows Y, so X is speculation' OR cut the sentence."

**Stem vs mix caveat:** an isolated stem's centroid describes the
guitar; a full-mix centroid is dominated by drums/bass/keys and is
only an upper bound on what the guitar contributes. When the WAV is a
full mix, treat the fingerprint's centroid as a ceiling, look at the
spectrogram of guitar-only sections, and ask the user for an isolated
stem before committing.

## Precondition (MCP path only) — the MCP server must be connected

If the user picked the MCP path:

1. Confirm the OpenRig MCP tools are available (e.g. `apply_rig_nav`,
   `add_block`, `set_block_parameter_number`, `rename_rig_preset`,
   `save_chain_preset`) and the resource `openrig://project` reads. The
   OpenRig plugin wires this automatically when OpenRig runs with
   `--mcp` (`openrig --mcp`, GUI or console).
2. If the tools/resource are **not** available, STOP. Tell the user to
   start OpenRig with `--mcp` and install the OpenRig plugin
   (`docs/mcp.md`). Offer the file-only path as an explicit alternative.
   Do NOT silently fall back to writing a YAML file — confirm with the
   user first.

The rig is shared: changes you make via MCP are reflected in the open
GUI in real time, and vice-versa.

## Iron rule -- three sources of truth, do not confuse them

Catalog work has THREE orthogonal questions, and each has exactly ONE authoritative source:

1. **"Which `MODEL_ID`s exist AND are installed on this rig RIGHT NOW?"** → the MCP resource `openrig://plugins` (returns every plugin loaded by THIS instance, with `id`, `display_name`, `brand`, `block_type`, `backend`). This is the **discovery / installedness** source. See **Step 2.5**.

2. **"For a chosen `MODEL_ID`, what are its parameter paths, types, ranges, defaults, and enum options?"** → the MCP resource `openrig://plugins/{id}/params` (returns `{params: {effect_type, model, display_name, audio_mode, parameters: [{path, label, group, widget, unit, domain, default_value, ...}]}}`). The `domain` field decides which typed param tool you call:
   - `FloatRange` / `IntRange` → `set_block_parameter_number`
   - `Bool` (string literal) → `set_block_parameter_bool`
   - `Enum` (`{options: [{value, label}, ...]}`) → `select_block_parameter_option` (pass `value`, NOT `label`)
   - anything else (text, etc.) → `set_block_parameter_text`

   This is the **schema** source. See **Step 2.6**. For an already-placed block you can also read `openrig://chains/{chain}/blocks/{block}/params` — same shape with `current_value` added per parameter (useful for "tweak this preset" flows).

3. **"What knob *values* do real players use for this style or song? Which amp/cab pairings are canonical? Where should a metal rhythm EQ start?"** → [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) in the `jpfaria/OpenRig-plugins` repo. This is the **patterns / recipes** source — it answers "good starting points", NOT "what's a valid param". Use it for tone recipes per style, per-song knob settings, and per-amp signature patterns. WebFetch the URL if the repo isn't checked out locally.

The three cooperate: **discovery** (`openrig://plugins`) tells you the `MODEL_ID` exists on the rig; **schema** (`openrig://plugins/{id}/params`) tells you the path is `eq.bass` not `bass` and the range is 0–10 not 0–100; **recipes** (`blocks-reference.md`) tells you metal rhythm wants ~7.5 in that range.

You MUST NOT:

- Open or grep any file under `crates/block-*/src/` to discover model IDs or parameters. Ever. Not for "double-checking", not for "the schema might be stale", not for "just one quick lookup". The MCP schema IS the runtime — it cannot be stale.
- Read existing presets to copy their `MODEL_ID` strings or parameter shapes. They drift; the MCP schema does not.
- Guess or invent model IDs OR param paths based on what "sounds right" / what you "remember from a similar amp". Every ID and every path is a string the runtime hard-matches. Dotted paths (`eq.bass`, `noise_gate.threshold_db`) and bare paths (`bass`, `gain`) BOTH occur depending on the plugin — and `bass` ≠ `eq.bass` to the runtime. Always read the live schema.
- Trust `blocks-reference.md` for **schema** questions (path/type/range/enum). The doc is the **recipes** source; the runtime is the schema source. The doc lags or drifts; the MCP schema does not.
- Trust the older heuristics this skill used to carry ("NAM amps expose only `character`/`cabinet`+`gain`"). Those were guesses written before the schema resource existed — the schema replaces them.

If a model you need is not in `openrig://plugins`, that is a **missing-capture case** — go to **Step 2.5**. Do NOT silently substitute.

If `openrig://plugins/{id}/params` returns `parameters: []` for a model, the block has no exposed params — just `add_block` and move on. This is normal for some fixed-processor blocks.

If [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) has no recipe for the gear you're chasing, that is a **doc gap but NOT a blocker** — design the tone from the analyzer fingerprint + the MCP schema defaults, optionally suggest the user open a doc issue.

## Mandatory inputs

- `<artist>` -- band/artist name
- `<song>` -- song title (optional but strongly preferred -- gear varies between eras)
- `<role>` -- `rhythm` / `lead` / `solo` / `clean`. Rhythm and lead
  almost always need DIFFERENT presets (different drive, different
  delay/reverb mix, different volume). Ask the user once if not given.
- *(optional)* `<reference-audio>` — a WAV stem of the guitar (ideally
  isolated, not the full mix). Lets you run the render→compare loop at
  the end (Step 6). Without it, you cannot validate the preset
  objectively; flag this to the user.

If only `<artist>` is given, ask once for the song and role. Era-less,
role-less presets drift toward generic and the user notices.

## Workflow (MCP path)

### 1. Research the signal chain

**The Step 0 fingerprint comes first.** Research is here to fill gaps
the analyzer cannot resolve (specific amp model/era, brand of pedal,
recording context) — not to drive the build. If you have not yet
fingerprinted every reference WAV the user provided, go back to Step 0.

Hit sources **in order**, stopping when you have a confident gear list (instrument → pedals → amp → cab → mic). Always cite which sources you used.

| Priority | Source | Why |
|---|---|---|
| 1 | `https://www.tonedb.co/` (search by song or artist) | Crowdsourced, song-specific, often has signal chain explicit. JS-heavy -- if WebFetch returns 404 or empty, fall back to the Playwright MCP (see fallback ladder below). |
| 2 | `https://www.groundguitar.com/tone-breakdown/` (per-album breakdowns) | Detailed per-song gear listings with chain order. |
| 3 | `https://killerrig.com/` (e.g. `killerrig.com/<artist>-amp-settings-and-tone-guide/`) | Numeric knob settings per song. |
| 4 | `https://musicstrive.com/<artist>-amp-settings/` | Often splits settings per song and per guitarist (rhythm vs lead). |
| 5 | `https://www.guitarchalk.com/<player>-amp-settings/` | Player-focused (Jim Root, Synyster Gates, etc.). |
| 6 | `https://prosoundhq.com/how-to-sound-like-<artist>-amp-settings-guide/` | Generic recipes; useful for fallback EQ. |
| 7 | `https://blog.andertons.co.uk/sound-like/sound-like-<artist>` | Gear context (which amps/cabs/strings the player ran in that era). |
| 8 | Premier Guitar / Guitar World rig rundowns | Authoritative for era and recording context. |

When two sources disagree on knob values, prefer the one that names the song explicitly. If they all give general guidance, weight them equally and pick the median.

**Fallback ladder when `WebFetch` fails or returns empty (common on JS-heavy sources like tonedb.co):** Playwright MCP → WebSearch → ask the user to paste page text. Playwright is a research aid; the *recipes* still come from [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md), `MODEL_ID` discovery from `openrig://plugins`, and **param schema from `openrig://plugins/{id}/params`** — never from web research.

### 2. Map gear to OpenRig models — and respect stem vs mix evidence

> ⛔ **HARD ORDER GATE — do these THREE things, IN ORDER, before touching `blocks-reference.md`:**
>
> 1. **Read `openrig://plugins`** this turn (the **discovery** source from the Iron Rule). Cache the `id` set.
> 2. **Shortlist candidate `MODEL_ID`s** by matching the gear you researched against the catalog's `block_type` + `brand` + `display_name` + `backend` fields. This is the moment `Vox AC30` → `nam_vox_ac30_*` (or whatever the catalog actually carries) happens. Discovery is ALWAYS this resource, never the doc.
> 3. **ONLY THEN** look up `blocks-reference.md` — by `MODEL_ID`, to find recipe values (knob ranges per style, amp/cab pairings, per-song knob recipes). The doc is consulted **after** you have the IDs, never **to find** them.
>
> **FORBIDDEN at this step (and anywhere in the skill):**
>
> - `Read` / `grep` / `WebFetch` / `cat` on `blocks-reference.md` before step 1 is done in this turn.
> - Greping the doc for amp brands (`vox`, `marshall`, `mesa`, `diezel`), song/artist names (`streets`, `u2`, `slipknot`), gear keywords (`dotted-eighth delay`, `boost`), or anything that looks like a discovery query. Discovery is `openrig://plugins`. The doc is a recipe lookup keyed by `MODEL_ID`.
> - "I'll grep the doc first because it's faster" — no. The doc may not even list the plugin the user has installed; `openrig://plugins` is authoritative.
> - "The doc has an Edge / U2 section so I'll start there" — no. The doc's per-song sections are recipe content, used only after the IDs are known.

Always prefer NAM amps over Native amps when the song has a real amp model. The param schema for whichever IDs you pick comes from `openrig://plugins/{id}/params` in **Step 2.6**, not from this step.

> ⛔ **AMP vs PREAMP vs CAB pairing rule (user law, 2026-06-12):**
> a block whose schema says `effect_type: amp` is a **full-rig capture**
> (head + cab baked in) — it NEVER takes a `cab` block after it. A `cab`
> block (IR) pairs ONLY with `effect_type: preamp` captures. Decide by
> reading `effect_type` from `openrig://plugins/{id}/params` in Step 2.6,
> never by "era-correct cab pairing" intuition. The user's own chains
> model the convention (full amp capture with no cab block; preamp
> capture + cab IR). Pairing `amp` + `cab` double-cabinets the chain —
> exactly the guess that wrecked the Your Love v1 build.

**The Step 0 fingerprint is your primary input here.** Walk each
field against the `blocks-reference.md` *recipes*:

- `centroid` + `band_energy` → parametric EQ band gains — **but as
  *shape*, not absolutes; see the reliability caveat below and in Step 0**
- `gain_character` → amp model class (clean / crunch / high-gain) and
  whether a boost block is needed
- `source.kind` → preset name role and whether to build multiple
  presets

> ⛔ **`time_fx` (delay/reverb) is LOW-CONFIDENCE — do NOT set the
> delay/reverb blocks from it.** The analyzer's `time_fx.delay_time_ms`,
> `delay_feedback`, and `reverb` type are **artifact-prone estimates**:
> a reverb tail gets read as a long delay (the documented "Gravity"
> failure read a hall tail as "delay 865 ms / 39%"), and a smooth hall
> gets labelled "spring". **Derive delay and reverb from research +
> knowledge of the song instead** (Step 1 — e.g. dotted-eighth at the
> song BPM for a delay-driven part, hall vs room from the recording
> context) and refine **by ear** (Step 6 Mode B). Treat `time_fx` as a
> *weak corroborating signal* only — if research says no delay and
> `time_fx` claims one, trust research and your ear.

> ⛔ **`centroid` / `RMS` are unreliable on a sparse, separated, or
> leaky stem.** A stem that is mostly sustained low notes + silence (or
> an imperfect source-separation with bleed) yields a `centroid` that
> reflects *which notes were held*, not the guitar's timbre — chasing it
> low-passes a bright tone into mud (the "Gravity" 750 Hz low-pass).
> Read `centroid`/`band_energy` as **directional EQ shape over the
> signal-bearing windows**, cross-checked against the spectrogram PNG
> and your ear — never as a hard EQ target. `RMS` is **never** an EQ or
> level target (level is maximized in Step 7, not matched). See Step 0's
> reliability caveat.

Research only fills in what the fingerprint cannot reveal (the exact
amp model the player used, brand of overdrive, era of cab) **and** the
time-based FX the fingerprint cannot measure reliably (delay/reverb).

**Stem vs mix reminder** (also covered in Step 0):

- **Isolated guitar stem** — every fingerprint field describes the
  guitar. Trust them.
- **Full mix** — the centroid is an upper bound dominated by
  drums/bass/keys. Do NOT EQ-darken just because the mix's centroid is
  low. Prefer asking the user for an isolated stem.

### 2.5. Verify each `MODEL_ID` is installed; route missing captures (BEFORE any `add_block`)

The plan you just produced names specific `MODEL_ID` strings (NAM amp
captures, IR cabs, gain pedals, etc.). Some of those names come from
[`blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) — the **schema** source — and the doc lists what the project knows how to load, NOT what THIS rig has installed. Before calling `add_block`, you MUST cross-check every one against the **installedness** source.

How:

1. **Read `openrig://plugins` once** at the start of build, **BEFORE the first `add_block`** (it returns every installed plugin with `id`, `display_name`, `brand`, `block_type`, `backend`). Cache the `id` set in memory. **Discovering a missing capture via `add_block` failure is forbidden** — the gate runs upfront, not as recovery. If the resource read itself errors, STOP and ask the user before continuing; do NOT proceed optimistically.

2. **For every `MODEL_ID` in the plan, check it's in that set.** "Every" = literally every one, including stock blocks like `compressor_studio_clean`, `gate_basic`, `eq_eight_band_parametric`, `limiter_brickwall`, `volume`, `native_guitar_eq`. The runtime hard-matches on the `id` string regardless of `backend`; narrowing the check to "only NAM/IR captures" is forbidden.

   **For every miss, the default proposal is `openrig:openrig-tone3000-fetch`.** Substitution with a different installed plugin is NOT a peer option — it is a last-resort fallback, allowed only after the import path has been attempted and failed OR the user has explicitly refused to import. The ask template:

   > "For the [block/role] the canonical capture is `<MODEL_ID>` (from `<amp/cab/...>`), but it is not installed on this rig. I will attempt to import it from tone3000 via `openrig:openrig-tone3000-fetch <query>` — this gets you the authentic capture, though it triggers the issue → PR → qa_audit/pack_plugins flow. Confirm to proceed, or tell me to stop and pick a different path."
   > *(render in the user's language at runtime — this English template documents the structure, not the literal words to ship)*

   The user's response branches into one of three paths in sub-step 3 below. **You may NOT propose substitution as a first-pass option** — present `tone3000-fetch` as the path, and only fall back to substitution when the import path is genuinely closed.

3. **Apply the user's response:**

   - **(a) Confirm import.** Invoke `openrig:openrig-tone3000-fetch` with the relevant search term (artist, amp model, capture name).
     - If the fetch **succeeds**: after the skill lands the file under `OpenRig-plugins` AND clears the qa_audit/pack_plugins gate, the user's OpenRig instance must reload its catalog (`reload_plugin_catalog` MCP tool) before the new `MODEL_ID` appears in `openrig://plugins`. Re-read `openrig://plugins` to confirm presence before calling `add_block`. Done.
     - If the fetch **fails** (no tone3000 hit, fetch errors, qa_audit blocks, user vetoes the PR mid-flow): you may now go to (b) — but you MUST ask the user explicitly, with the failure mode named ("tone3000 returned no results for `<query>`" / "qa_audit blocked the pack" / etc.) — never silently fall through.

   - **(b) Substitute — only after (a) was attempted and closed.** The user explicitly chose substitution (either upfront, by telling you to skip tone3000-fetch, or after a failed (a)). Ask them WHICH specific substitute from the installed catalog; do NOT auto-pick a "closest match" and do NOT pre-fill the menu with only your favorite. Present three to five candidates from `openrig://plugins` whose `block_type` matches and whose `brand` / `display_name` is plausibly adjacent, and let the user pick. Then record the substitution in the Step 5 provenance as `substituted <wanted> → <used> per user OK in Step 2.5`.

   - **(c) Abort.** User wants neither import nor substitution for this block. Stop the build; do not save anything partial.

   **One ask per missing capture.** If four blocks miss four different captures, you ask four times — or batch them in one message listing all four (each with its own tone3000 query as the primary proposal). Do NOT collapse "I'll substitute all of them" or "I'll import all of them in one shot without per-block confirmation" into a single unilateral decision.

4. Do not proceed to Step 2.6 until every `MODEL_ID` in the plan is either present in `openrig://plugins` OR explicitly substituted via path (3b) with the user's OK on the specific substitute.

### 2.6. Read the parameter schema for every chosen `MODEL_ID` (BEFORE any `set_block_parameter_*`)

For each `MODEL_ID` that survived Step 2.5, read `openrig://plugins/<MODEL_ID>/params` **once per build** and cache the response **for the duration of this build only**. Never reuse a schema from a prior conversation, a prior invocation, your training memory, or another agent's session — every build starts fresh against the live MCP. The schema is the runtime; it cannot be stale, but it can change between binary versions, so a snapshot from before is only safe to discard.

The schema tells you:

- **Which param paths exist** for this exact plugin. Paths are often dotted (`eq.bass`, `noise_gate.threshold_db`); do NOT assume top-level names. Two amps in the same family can expose different paths.
- **Which typed param tool to call**, decided by the `domain` field:
  - `FloatRange` / `IntRange` → `set_block_parameter_number`
  - `Bool` (the string `"Bool"`) → `set_block_parameter_bool`
  - `Enum` → `select_block_parameter_option` — pass the option's `value`, NOT its `label`
  - anything else (text, etc.) → `set_block_parameter_text`
- **Valid numeric range and step** (`domain.FloatRange.{min,max,step}`) so you don't push a value the runtime clamps or rejects.
- **Valid enum options** (`domain.Enum.options[].value`) so you don't pick something that doesn't exist.
- **`default_value`** — the rig's chosen baseline. If you don't have a recipe value from `blocks-reference.md` AND the analyzer fingerprint doesn't constrain it, fall back to the default rather than guessing.

**`parameters: []`** means the block has no exposed params — just `add_block`, do NOT call any `set_block_parameter_*` on it. (Normal for fixed-processor blocks; the schema is the only way to know which ones those are.)

**If the resource read errors** for a given `MODEL_ID`, STOP and tell the user. You may still call `add_block` for that block (Step 2.5 already confirmed installedness), but skip every `set_block_parameter_*` on it — never guess paths from memory.

**Forbidden:**

- Calling `set_block_parameter_*` with a path you didn't read from `openrig://plugins/{id}/params` in this step.
- Picking the typed param tool from memory of "similar" plugins instead of from the live `domain` field.
- Using a `label` instead of the `value` for an `Enum` domain.
- Pushing a numeric value outside `domain.min` / `domain.max`.
- Re-reading `openrig://plugins/{id}/params` mid-build to "see if it changed". The schema is stable per binary version; one read at the start is enough. (If the build changes underneath you, you have bigger problems.)

The schema and the recipes are **complementary, not redundant**: `blocks-reference.md` says "metal rhythm wants gain around 7.5 on this amp family"; `openrig://plugins/{id}/params` says "the path is `eq.gain` and the range is 0–10". Use both.

### 3. Build the preset on the live rig (MCP) — new slot, never overwrite

The plan below is the **FX layout** the preset will carry. Realise it by
calling tools, never by writing a file.

Steps:

0. **Check first whether a preset for this song already exists.** Read
   the project's preset banks across all chains (per-chain preset
   listings via `openrig://chains/<chain_id>/presets`, and the
   project-level pool via `openrig://presets`). Search for any preset
   whose name mentions the song, the artist, or a clear synonym
   (case- and accent-insensitive). If a candidate exists, STOP and ask
   the user once whether to **replace**, **save alongside** with a
   different name (e.g. append ` (v2)` / the date), or **show plan
   only**. Never overwrite without confirmation.

1. **Read `openrig://project` and ALWAYS ask the user where to put this preset.** List every chain in the project with its id, display name, `instrument`, and a short summary of its current blocks. Build a numbered menu — **including when only one chain matches the song's instrument** — and add a final "create new chain" option. Do NOT auto-pick. The shape (replace with real chains from the project read; do NOT echo example chain names from this skill text):

   > "Where do you want to put this preset?
   > **(1)** chain `<id>` ('<display name>', instrument `<x>`, current blocks: `<short summary>`)
   > **(2)** chain `<id>` ('<display name>', instrument `<y>`, ...)
   > ...
   > **(N+1) create new chain** — I'll ask for name + instrument + I/O devices and call `add_chain`."
   > *(render in the user's language at runtime — this English template documents the structure, not the literal words to ship)*

   You MAY recommend one option in the ask message (e.g. "I recommend **(1)** because the `instrument` matches the song's style"), but you **MUST wait for the user's explicit pick**. Auto-selecting because "only one chain matches the instrument" is forbidden — that is the deterministic auto-pick behaviour this step exists to prevent.

   **If the user picks `(N+1) create new chain`**, sub-flow:

   1. **Name + instrument prompts.** Ask the user the **chain name** (free text, e.g. "Lead Solos", "Rhythm — Drop D", "Clean Acoustic") **AND** the **`instrument`** tag (`electric_guitar` / `acoustic_guitar` / `bass_guitar` / etc.) in the same ask, OR one after the other if you must. If the user answers only one of the two, **re-ask the missing one explicitly**. Never infer the instrument from the song or from the chain name.

   2. **Read `openrig://devices` and present I/O menus.** A chain without an Input block and an Output block is unusable (the `add_chain` schema's `Chain.blocks` requires at least one of each for the audio graph to wire). Read the resource ONCE, **immediately before** the menus — not minutes earlier and not in a prior turn. The device list is a snapshot at read time; if the user mentions replugging an interface between the menu and the `add_chain` call, re-read `openrig://devices` and restart this sub-step. Render TWO numbered menus — one for input, one for output — using the actual `<label>` + `device_id` strings the resource returned (do NOT echo example device names from this skill text or memory of a prior conversation):

      > "Input device for this chain?
      > **(1)** `<input label 1>` (`<device_id 1>`)
      > **(2)** `<input label 2>` (`<device_id 2>`)
      > ...
      >
      > Output device?
      > **(1)** `<output label 1>` (`<device_id 1>`)
      > **(2)** `<output label 2>` (`<device_id 2>`)
      > ..."
      > *(render in the user's language at runtime — this English template documents the structure, not the literal words to ship)*

      You MAY recommend one input (e.g. "I recommend the Scarlett because it looks like the main interface") and one output, but you MUST wait for the user's explicit pick on each. Even when the rig has only one input or one output device, render the menu — same rule as the chain pick. Y/n shortcut is forbidden.

   3. **Channels + mode prompts.** For each chosen device, ask the user the **channel list** (e.g. `[1]` for mono guitar input on channel 1, `[1, 2]` for stereo L/R) AND the **mode** (`mono` / `stereo` / `dual_mono` for inputs; `mono` / `stereo` for outputs). You MAY suggest a sensible default per `instrument` tag (e.g. mono guitar input usually = single channel + `mono`; stereo output usually = channels 1,2 + `stereo`), but the suggestion goes IN the ask, not as a self-applied default. If the user does not answer all four (in-device, in-channels+mode, out-device, out-channels+mode), re-ask the missing ones explicitly.

   4. **Build the Chain payload and call `add_chain`.** Construct:

      ```json
      {
        "chain": {
          "enabled": true,
          "instrument": "<from step 1>",
          "blocks": [
            { "id": "rig:input", "kind": { "Input":  { "entries": [{ "device_id": "<from step 2>", "channels": [<from step 3>], "mode": "<from step 3>" }] } } },
            { "id": "rig:output", "kind": { "Output": { "entries": [{ "device_id": "<from step 2>", "channels": [<from step 3>], "mode": "<from step 3>" }] } } }
          ]
        }
      }
      ```

      The `description` field is optional — set it to the chain name from step 1 if the user wants the label persisted that way (note: chain `label` vs `description` may differ across OpenRig versions; if a future release adds a first-class `name`/`label` field to the `add_chain` schema, prefer it). Capture the returned chain id.

      **Multi-entry case (rare):** `Input.entries[]` and `Output.entries[]` are arrays — a chain CAN carry more than one device per side (e.g. two guitars sharing one chain via `dual_mono`, or output mirrored to two outputs). The standard create-new flow above assumes ONE device per side. If the user explicitly asks for a multi-device chain, repeat step 3 per additional device and append to the `entries[]` array. Don't assume multi-device by default.

      If `add_chain` errors (invalid device_id, channel out of range for the device, schema mismatch, etc.), **STOP and surface the exact error to the user** — do not retry with mutated values, do not silently fall back to a different device, do not switch to an existing chain. Ask the user to correct the input or pick a different option from the original Step 3.1 menu.

   5. **Continue the preset build into the new chain id.**

   **If `openrig://project` returns ZERO chains**, you may go straight to the create-new sub-flow (still asking name + instrument + I/O devices + channels/mode), but say out loud "your rig has no chains yet — I'll create one" so the user knows. Don't render an empty menu.

   **If `openrig://project` returns exactly ONE chain**, you still render the menu (option 1 = that chain, option 2 = create new). The "menu always" rule has no carve-out for project size.

   **If the user does not answer**, ask once more or stop. Never decide for them.

   **Forbidden short-form ask:** rendering a single-line "use `<chain>`? (y/n)" instead of the full numbered menu is the same anti-pattern as auto-picking — it pre-selects the option you wanted and hides the alternatives (other chains + create new). Always render the full menu; the "y/n shortcut" is forbidden even when only one chain matches the instrument.

2. **Decide the preset name** as
   `"<Song> — <Artist> (<role>)"` (e.g. `"Clocks — Coldplay (rhythm)"`,
   `"Gravity — John Mayer (solo)"`). This is what shows up in the
   chain's preset bank dropdown.

3. **Add a NEW empty preset slot to the chain's bank.** Call
   `apply_rig_nav { chain: <chain_id>, kind: { Preset: -1 } }`. The
   `-1` is the sentinel for "add a new slot"; the engine adds an
   **empty** slot to the chain's bank, makes it the active slot, and
   the chain's current blocks reset to just `input` + `output` (no FX).
   This is the safe path — it does **NOT** touch any existing preset's
   blocks in the bank. From here on, you build into a clean empty
   chain.

   > **Why this matters:** removing the chain's current FX blocks
   > directly (e.g. `remove_block` on every non-I/O block while the
   > active preset is still the user's existing preset) would
   > destructively edit that preset's content. `apply_rig_nav Preset(-1)`
   > sidesteps the active preset entirely by switching to a new slot
   > before you touch anything.

4. **For each block in the plan, in order**, call
   `add_block { chain, kind, model_id, position }`. Position is
   counted **after** the input block(s) and **before** the output
   block(s); the engine inserts processing in between the I/O
   automatically. The result is `BlockAdded { chain, block }` — capture
   the new block id.

5. **Set parameters** using the schema you read in **Step 2.6**. For each
   parameter you want to set, the schema entry tells you which tool to
   call based on `domain`:
   - `FloatRange` / `IntRange` → `set_block_parameter_number { chain, block, path, value }` — value clamped to `domain.min`/`domain.max`
   - `Bool` → `set_block_parameter_bool { chain, block, path, value }`
   - `Enum` → `select_block_parameter_option { chain, block, path, value }` — pass the option's `value`, NOT its `label`
   - text → `set_block_parameter_text { chain, block, path, value }`

   `path` always comes from the schema's `parameters[].path` — never
   from memory, never from `blocks-reference.md`. If the schema's
   `parameters: []` for this `MODEL_ID`, skip this sub-step for this
   block entirely.

6. **Disabled-by-default blocks**: after `add_block`, call
   `toggle_block_enabled { chain, block }`.

7. **Set the preset's display name** with
   `rename_rig_preset { chain, name: "<Song> — <Artist> (<role>)" }`.
   This sets the `RigPreset.name` field that the GUI and the preset
   combobox show. Without this, the new slot is labelled
   `"New Preset N"` (the auto-generated pool key) which the user
   cannot recognise.

8. **Commit the preset** with
   `save_chain_preset { chain, name: "<Song> — <Artist> (<role>)" }`.
   This writes the YAML file under the configured `presets_path` so
   the preset survives a reload. **Do not also call `save_project`** —
   the preset itself is the unit of work.

### Plan (electric guitar, rock/metal/clean default — adjust per song style)

```text
1.  dynamics/ <compressor_model_id>       enabled:true   intent: parallel-style clean compression (~20-40% mix for clean rhythm/lead)
2.  filter  / <guitar_eq_model_id>        enabled:true   intent: start flat, tilt ±2 dB max
3.  dynamics/ <gate_model_id>              enabled:true   intent: fast attack, release tuned to playing dynamics, threshold above noise floor
4.  gain    / <gain_model_id>              enabled:<bool> intent: only if the song uses a boost/drive (recipe in blocks-reference.md per style)
5.  amp     / <amp_model_id>              enabled:true   intent: NAM amp for songs with a real amp model; recipe in blocks-reference.md
6.  filter  / <parametric_eq_model_id>    enabled:true   intent: mimic real bass/mid/treble/presence shape (see Step 4)
7.  delay   / <delay_model_id>            enabled:<bool> intent: time from BPM math (recipe in blocks-reference.md per style)
8.  reverb  / <reverb_model_id>           enabled:true   intent: room for rhythm, hall for lead; size + mix per analyzer RT60
9.  dynamics/ <limiter_model_id>          enabled:true   intent: brick-wall safety on the bus
10. gain    / <volume_model_id>            enabled:true   intent: per-preset output trim — MAXIMIZED in Step 7 (measured peak ≈ -1.0 dBFS), never left at a timid default
```

The **`intent:`** column is the recipe-class hint (what this block is *for*). The actual `MODEL_ID`s are picked in Step 2 (from `openrig://plugins` + recipes in `blocks-reference.md`); the actual param **paths, types, ranges, and enum options** come from `openrig://plugins/{id}/params` in **Step 2.6** — never from this template. Do NOT read names like "mix", "attack_ms", "threshold", "feedback" from this table and assume they are the schema paths for the chosen plugin; they are the *concepts* you'll set, and the actual path/type for each concept comes from Step 2.6 only.

**Tuner and spectrum analyzer are NOT in this plan.** `tuner_chromatic`
and `spectrum_analyzer` are NOT valid `add_block` kinds — the runtime
rejects them with "unknown utility model". They are **rig-wide
utilities** controlled by separate Commands (`set_tuner_enabled`,
`set_spectrum_enabled`) and live outside the per-chain block
processor. The preset has no business toggling them.

Adjust per song style:

All numeric *values* below are recipe-class targets (what you're aiming for); the actual param **paths** to set them via come from each block's Step 2.6 schema.

- **Clean / acoustic**: drop the boost (skip block 4), drop the gate, switch to a clean amp, add a body IR for acoustic.
- **Funk / clean rhythm**: keep the compressor paralleled with a high wet-mix value. Lower amp gain.
- **Lead solo**: bump the volume block's output to ~85-90% of its range, raise delay mix to ~12-25%, switch reverb to a hall, larger room size, higher mix.
- **Delay-driven (Edge/Buckland/Mayer rhythm)**: time = dotted-eighth at the song BPM (`60000 / bpm * 1.5 / 2`), feedback ~25-35%, mix ~30-40% so the delay pattern is clearly audible.
- **Doom / drone**: drop boost, raise reverb mix to 25%+, swap delay model for a tape-style one.

### 4. Knob translation rule

NAM amp captures have **knobs baked into the capture**, but what knobs
the *block* exposes varies per plugin — there is no universal NAM
control surface. Read each block's actual param set from
`openrig://plugins/{id}/params` at build time (Step 2.6); do NOT
assume from the family, the brand, or memory of "similar" amps. The
schema is the runtime, it cannot be stale.

Three patterns you'll encounter in the schema (decide per-amp, never
assume):

- **Structural-only**: enum/select for character or preset, plus I/O
  level and maybe a built-in noise gate / EQ. No continuous
  bass/mid/treble at the amp level — shape EQ with the parametric EQ
  block **after** the amp (block 6).
- **Full continuous knobs**: bass/middle/treble/master directly on the
  amp. Set them on the amp block; skip the parametric EQ unless the
  analyzer fingerprint needs more shaping than the amp exposes.
- **`parameters: []`**: the block is a fixed processor — just
  `add_block`, no `set_block_parameter_*` calls at all.

Which pattern any given `MODEL_ID` falls into is **only** knowable by
reading its schema. This skill does NOT enumerate per-plugin examples
on purpose — they would lock the skill to a snapshot in time and
recreate the staleness problem the MCP schema source exists to solve.

### 5. Provenance comment in the chat reply + `eval.md` update

After `save_chain_preset` succeeds **and** the matching iteration's
render + diff are written to the persistent directory (Step 6), update
two surfaces:

**A. `eval.md` in the persistent directory** — for every iteration:

1. Append a new row to the `## Iteration log` table under the matching
   `### <role>` sub-heading: `| v<N> | <match_score> | <RMS Δ dB> |
   <centroid Δ Hz> | <key change applied this iter> |`. The values
   come from `diffs/<role>-v<N>.json`; the "key change" is the
   recommendation you applied this iteration (e.g. "raised eq.gain
   by 1.5", "swapped delay model", "baseline" on v1).
2. On the first build, populate the `## Gear research`,
   `## Mapping`, `## Methodology notes`, and `## Sources` sections
   from the actual research you did. Use the live values from
   `openrig://project` and `openrig://plugins`, never echo example
   names from this skill's text.
3. Set `Status:` according to outcome:
   - `iterating` between iterations (default while the render+compare
     loop is still running).
   - `done` once the user accepts the preset AND
     `presets/<role>-final.yaml` is written.
   - `abandoned` if the user explicitly walks away — record one line
     in `## Methodology notes` saying why.
4. Update `**Date:**` only on first build; subsequent iterations leave
   it alone so the original build date is preserved (use a per-row
   timestamp in the iteration log if dates matter per iter).
5. If a global `<openrig-evaluations-root>/INDEX.md` exists (Step 0a
   optional), update the row for this `<song-slug>` with the latest
   `match_score`, date, and status. If it doesn't exist, optionally
   create one.

**B. Chat reply provenance summary** — every save:

1. **Chain + slot + preset name**: which chain (display name + id),
   which slot index, and the preset name. Use the **actual** values
   from the rig the user is working with — do NOT echo any example
   chain or preset name from this skill's text.
2. **Mapping table**: real gear → OpenRig model. Mark fallbacks explicitly.
3. **Cite sources** you actually fetched.
4. **Note uncertainty** explicitly. For any substitution that came out
   of **Step 2.5**, name BOTH the wanted `MODEL_ID` and the installed
   substitute (e.g. `nam_diezel_vh4` → `nam_diezel_herbert`, per user
   OK in Step 2.5). Silent substitutions are forbidden — see Red Flags.
5. **Tunings** mentioned as a playing hint, optionally in the preset name.
6. **Point at the persistent evaluation dir**: tell the user
   `<openrig-evaluations-root>/<song-slug>/` holds the full audit trail
   (refs, fingerprints, renders, diffs, per-iteration preset
   snapshots, `eval.md`) — so they know where to find it for re-eval,
   backup, or sharing.

### 6. Render and validate (MANDATORY before "done") — pick the mode from the VALIDATION GATE

> ⛔ **The mode comes from the VALIDATION GATE at the top of the file.**
> **Mode A** (same-DI reamp) → the analyzer is the judge; chase
> convergence. **Mode B** (real recording) → the **ear + user** is the
> judge; the analyzer is a directional shape-guide only. The render
> itself is mandatory in both modes — what differs is who decides
> "close enough". Run it BEFORE declaring done.

Steps 6.0–6.2 (render + write artifacts) are **identical** in both
modes; the judging in 6.3+ diverges.

**6.0 — Render the bundled DI through the just-saved preset.** Write
directly to the persistent eval dir from **Step 0a**, NOT `/tmp/`:
`openrig render --preset "<Song> — <Artist> (<role>)" --input
<openrig-source-root>/assets/audio/input.wav --output
<openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav`. `<N>`
starts at `1`, or `last_existing_N + 1` when reusing a dir. You never
ask for a DI; only the wet reference comes from the user.

**6.1 — Run the analyzer over the render and the ref.** Compare against
the **persistent** `refs/<role>.wav` (copied in Step 0a — never the
user's original path): `.venv/bin/python scripts/compare.py
<openrig-evaluations-root>/<song-slug>/refs/<role>.wav
<openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav --output
<openrig-evaluations-root>/<song-slug>/diffs/<role>-v<N>.json`. If
`compare.py` lacks `--output`, capture stdout and write the JSON to the
persistent `diffs/<role>-v<N>.json` yourself. **Also generate the
spectrogram PNGs** for render and ref (the analyzer writes them) — in
Mode B the spectrogram and your ear, not the score, are what you read.

**6.2 — Snapshot the preset YAML** after every `save_chain_preset` in
the loop: `cp <openrig-user-data-root>/presets/"<Song> — <Artist>
(<role>)".yaml
<openrig-evaluations-root>/<song-slug>/presets/<role>-v<N>.yaml`. The
live YAML carries only the latest version; the snapshot is the only way
to re-render a historic iteration. On accept, also `cp` to
`presets/<role>-final.yaml`.

#### Mode A — same-DI reamp: chase `match_score`

The ref and the render carry identical note content, so the analyzer
measures pure tone difference. Here `match_score`/`diff.json` IS the
judge.

**6.3A** Read `diffs/<role>-v<N>.json`. The top 2-3 priority-sorted
`recommendations` are concrete tone moves ("raise EQ band 4 gain by
3 dB", "delay time wrong by 80 ms", "needs more high-shelf").

**6.4A** **Apply ONE recommendation at a time** (the relevant
`set_block_parameter_*`), re-render (bump `<N>`), re-compare. Iterate
until `diff.converged` is true OR `match_score` plateaus across two
consecutive iterations — then report the gap and score to the user.
**Ignore any RMS/level recommendation** — level is Step 7's job, never
matched to the ref.

#### Mode B — real recording: the EAR is the judge, the analyzer is a shape-guide

The ref is a different performance, so `match_score` scores *what notes
were played and when*, not *how the rig sounds*. **Do NOT iterate to
raise `match_score`. Do NOT treat any single `match_score` number as
pass/fail.** Instead:

**6.3B — Use the analyzer for SHAPE, not score.** The one analyzer
output that survives a performance mismatch is the **normalized
long-term average spectrum (LTAS) over the signal-bearing windows**
(silence trimmed) — it describes the *tonal balance* (where the energy
sits across the band) independent of which notes were played and how
loud. Read the LTAS **shape** of the render vs the ref (and the
spectrograms from 6.1) as a **directional EQ hint** — "the ref has more
energy around 2–4 kHz, mine is darker there" → a candidate parametric-EQ
move. It is a hint, **not** a target to converge on, and you confirm
every move by ear in 6.4B. **Do not** read `centroid`, raw `RMS`, or
`time_fx` as truth here — see the reliability caveat in Step 0 and the
`time_fx` rule in Step 2; a sparse/separated/leaky stem distorts all
three.

**6.4B — Validate by ear, with the user in the loop.** Render, listen,
and present the result to the user for a verdict — playing the
render and/or describing what you changed, and asking a *specific*
question ("does the delay feel right now, or still too long?" / "is it
still muddy in the low-mids?"). The **user's ear is the primary
validator in Mode B** — when the user says "muffled", "too dark", "delay
too long", that is the authoritative signal; act on it directly. You may
pair it with the LTAS shape hint ("you're right it's dark — the ref has
more 3 kHz, I'll lift the presence band"), but the ear leads and the
number never overrides it. Iterate ear-move → render → user check until
the **user signs off**, then report.

**6.5B — Derive time-based FX from research, not from `time_fx`.** Set
delay time/feedback and reverb type/size from **research + knowledge of
the song** (Step 1) — e.g. dotted-eighth at the song BPM — and refine by
ear. The fingerprint's `time_fx` is **low-confidence** (a reverb tail
reads as a long delay; a smooth hall reads as "spring") and must not
drive these blocks. See Step 2.

Without running the mode-appropriate loop, you are shipping research +
fingerprint alone — an **educated guess**, not a validated preset. Say
so in the chat reply if you could not complete it.

### 7. Output level maximization — as loud as possible without clipping (MANDATORY before done)

> ⛔ **Loudness law (user correction, 2026-06-12):** every preset
> leaves the chain **as loud as possible without clipping**. Presets
> shipped with a timid output trim are the documented failure mode —
> the user has to crank everything downstream and the preset feels
> broken next to the rig's other tones.

Runs **after** the Step 6 tone loop completes (converged in Mode A, or
user ear sign-off in Mode B) — so level moves never pollute the tone
work — and **before** the final `save_chain_preset` + "done" report.
Level is **always** maximized here regardless of mode, and **never**
matched to the reference's RMS (a real reference is often quiet):

1. **Measure the latest render's peak** — deterministically, never by
   guess. Use the analyzer fingerprint's loudness/peak field if it
   exposes one, or any deterministic peak readout on the WAV (e.g.
   `sox <wav> -n stat`, or a two-line soundfile/numpy max-abs in the
   analyzer venv). Record the value in dBFS.
2. **Target: peak in [-2.0, -0.5] dBFS, aim ≈ -1.0 dBFS.** Below
   -3 dBFS is too quiet — raise the trim. At or above -0.3 dBFS is
   clipping territory (intersample peaks) — back off.
3. **Move ONLY the final volume/output-trim block (plan block 10).**
   Compute the delta (`target_dB - measured_dB`), convert to the
   block's scale, apply via `set_block_parameter_number`. Never touch
   amp gain/master, boost level, or the limiter to fix loudness —
   those are tone, and changing them invalidates the converged
   match_score.
4. **Re-render and re-measure to confirm.** The trim block sits AFTER
   the brickwall limiter, so it absolutely can clip the output — the
   confirmation render is the only proof the new peak landed in the
   window. Iterate trim → render → measure until it does. These
   confirmation renders reuse the current `<N>` artifacts' naming with
   a `-level` suffix (`renders/<role>-v<N>-level.wav`); they are level
   housekeeping, not tone iterations, and don't bump `<N>`.

   **If the trim hits its schema maximum and the confirmed peak is
   still below -3 dBFS**, the gap can't be closed at the trim — STOP
   and report the measured numbers to the user ("trim at max, peak
   still -X dBFS — upstream gain staging is eating the headroom").
   Do NOT silently start raising amp master / boost level to
   compensate: that re-opens the converged tone. Let the user decide
   between accepting the level or re-entering the Step 6 loop with
   level as an explicit constraint.
5. **Save with the maximized trim** (`save_chain_preset`) and report
   the final measured peak in the chat reply alongside the
   match_score (e.g. "output peak -1.1 dBFS").

**There is no "-18 dBFS standard target" in this skill.** -18 dBFS
(and similar K-system / broadcast alignment levels) are mixing
conventions for headroom inside a DAW session — a live rig preset is
a finished sound, and the law here is maximize-without-clipping. If
the converged render already peaks inside the window, leave the trim
alone and just report the measured value.

**File-only path:** without the runtime there is no render to
measure, so level maximization is impossible. Set the trim to the
recipe/default value and flag explicitly in the chat reply: "output
level unverified — file-only build; on first MCP session run the
Step 7 level pass, the preset may load quiet until then".

## Step 8 — Re-evaluation of an existing preset

Use when the user asks to re-validate a preset that already exists
("compara de novo X com a ref", "rerun the compare for <song>",
"how does my current <song> preset score today against the same
ref?"). This is NOT a fresh build — there's no research, no
`add_block`, no `save_chain_preset` rebuild. It's strictly a
**render-current-YAML → compare → log** cycle that exercises the
persistence laid down by Step 0a, Step 0(4), and Step 6.

Preconditions:

1. **MCP path only.** `openrig-render` requires the runtime; the
   file-only workflow has no way to produce a fresh render. If the
   user asks for re-eval on the file-only path, tell them to start
   OpenRig with `--mcp` and offer to switch.
2. `<openrig-evaluations-root>/<song-slug>/refs/<role>.wav` exists —
   otherwise there's nothing to compare against. If missing, this
   evaluation predates Step 0a; ask the user for the original ref WAV
   and run Step 0a + Step 0 first to backfill.
3. `<openrig-user-data-root>/presets/"<Song> — <Artist> (<role>)".yaml` exists (the
   live preset YAML) OR `presets/<role>-final.yaml` in the eval dir
   exists. Ask the user which one to evaluate if both diverge — the
   live YAML might have been tweaked outside this skill.

Flow:

1. **Read `eval.md`** to recover prior chain, gear mapping, and last
   iteration index. Pick the re-eval index: `<role>-vREEVAL-<YYYY-MM-DD>`
   (date suffix instead of a numeric bump — re-evals are not part of
   the build's iteration sequence and shouldn't shift `<N>`).
2. **Render the current preset YAML through the bundled DI**:
   `openrig render --chain <preset-path> --input
   <openrig-source-root>/assets/audio/input.wav --output
   <openrig-evaluations-root>/<song-slug>/renders/<role>-vREEVAL-<YYYY-MM-DD>.wav`.
   Use `--chain <yaml-path>` (or whatever the equivalent
   load-from-file flag is) to render the YAML directly without
   needing to push it into a slot. The DI path stays the canonical
   bundled file from `<openrig-source-root>/assets/audio/input.wav`
   — same as Step 6, same dynamic-range guarantees.
3. **Compare against the persistent reference**:
   `.venv/bin/python scripts/compare.py
   <openrig-evaluations-root>/<song-slug>/refs/<role>.wav
   <openrig-evaluations-root>/<song-slug>/renders/<role>-vREEVAL-<YYYY-MM-DD>.wav
   --output
   <openrig-evaluations-root>/<song-slug>/diffs/<role>-vREEVAL-<YYYY-MM-DD>.json`.
   Same compare.py the iteration loop uses; same caveat about
   `--output` fallback to stdout-capture.
4. **Append a re-eval row to `eval.md`**: under the matching
   `### <role>` iteration table, add `| vREEVAL-<YYYY-MM-DD> |
   <match_score> | <RMS Δ> | <centroid Δ> | re-eval against unchanged
   ref |`. Do NOT change `Status:` from `done` back to `iterating`
   just because you re-ran a compare — this is a checkup, not a new
   iteration. If the user actually wants to tune the preset from the
   re-eval result, that flips to a fresh Step 6 iteration sequence
   (continue numbering at `<N+1>`, not at `vREEVAL`).
5. **Chat reply**: report the new `match_score`, diff against the
   prior best score (read from `eval.md`'s last non-REEVAL row), and
   point at the persistent diff file path so the user can inspect.

Re-eval does NOT mutate the live rig, does NOT call
`save_chain_preset`, does NOT touch the chain's bank. It's pure
read-render-compare over persistent artifacts.

## Validation before declaring done

- [ ] You checked for a pre-existing preset for this song before
      touching the rig, and either got the user's explicit OK or saved
      to a different name.
- [ ] You added a NEW slot via `apply_rig_nav Preset(-1)` — you did NOT
      destructively edit the chain's currently-active preset blocks.
- [ ] The new slot's display name was set via `rename_rig_preset`.
- [ ] `save_chain_preset` returned without error and the preset name
      shows up in the bank when you re-read
      `openrig://chains/<chain>/presets`.
- [ ] Every `MODEL_ID` actually passed to `add_block` is present in
      `openrig://plugins` — verified by reading the resource in
      **Step 2.5**.
- [ ] Any missing captures were resolved through **Step 2.5** with
      `openrig:openrig-tone3000-fetch` as the primary proposal.
      Substitution (path 3b) was offered ONLY after the import path
      was attempted and closed (no tone3000 result, fetch error,
      qa_audit block, or user veto). For each substituted block, the
      user explicitly picked the specific substitute from a list of
      candidates — never your auto-pick — and the substitution is
      recorded in the Step 5 provenance.
- [ ] Every `path` passed to `set_block_parameter_*` came from
      `openrig://plugins/<MODEL_ID>/params` read in **Step 2.6** —
      never from memory, never from `blocks-reference.md`, never
      copied from another preset.
- [ ] The typed param tool (`_number` / `_bool` / `_text` /
      `select_..._option`) was chosen by the schema's `domain` field
      (`FloatRange`/`IntRange` → `_number`, `Bool` → `_bool`, `Enum` →
      `select_..._option`), not by guessing from the param's name.
- [ ] For any block whose schema returned `parameters: []`, no
      `set_block_parameter_*` was called on it.
- [ ] If you called `add_chain`, it was BECAUSE the user explicitly
      picked the "create new chain" option in Step 3.1 AND answered
      all FOUR prompt blocks: (1) name + instrument, (2) input device
      (from the `openrig://devices` menu) + input channels + input
      mode, (3) output device (from the menu) + output channels +
      output mode, (4) explicit confirmation to call `add_chain`.
      You did NOT call `add_chain` for any other reason.
- [ ] Before calling `add_chain`, you read `openrig://devices` and
      built the `chain.blocks` array with explicit Input and Output
      blocks using the device_id/channels/mode the user picked. You
      did NOT call `add_chain` with `blocks: []` (the resulting chain
      has no I/O wiring and is unusable).
- [ ] You did NOT auto-pick a chain in Step 3.1 just because its
      `instrument` matched. You rendered the menu and waited for the
      user's explicit pick, even when only one chain matched.
- [ ] You did NOT call `save_project` (the preset is the unit of work).
- [ ] You did NOT add `tuner_chromatic` or `spectrum_analyzer` via
      `add_block` (they are rig-wide commands, not chain blocks).
- [ ] You did NOT touch any `input`, `output`, or `insert` block on
      the chain — those are the user's rig wiring.
- [ ] You classified the reference at the VALIDATION GATE: same-DI
      reamp (Mode A) or real recording (Mode B). When unsure you asked
      the user once and defaulted to Mode B.
- [ ] If a reference was provided, you ran the mode-appropriate Step 6
      loop: **Mode A** — chased `match_score` to `diff.converged` or a
      reported plateau; **Mode B** — judged by ear with the user in the
      loop (LTAS shape as a hint only), got the user's sign-off, and did
      NOT iterate on `match_score`.
- [ ] You did NOT set the delay/reverb blocks from the fingerprint's
      `time_fx`, did NOT EQ-darken off a raw `centroid`, and did NOT
      match the reference's RMS. Delay/reverb came from research + ear;
      EQ shape was cross-checked against spectrogram + ear; level was
      maximized in Step 7.
- [ ] After tone convergence you ran the **Step 7 level pass**: the
      final render's measured peak lands in [-2.0, -0.5] dBFS, only
      the output-trim block was moved, a confirmation render proved
      the value, and the chat reply reports the measured peak. (MCP
      path; on file-only you flagged "output level unverified".)
- [ ] The render command pointed `--input` at the bundled
      `<openrig-source-root>/assets/audio/input.wav` — NOT a
      user-supplied DI path, NOT a random clean WAV.
- [ ] You resolved `<openrig-user-data-root>` for your OS at the start
      of **Step 0a** (macOS → `~/Library/Application Support/OpenRig/`,
      Linux → `${XDG_CONFIG_HOME:-~/.config}/OpenRig/`, Windows →
      `%APPDATA%\OpenRig\`) and used that resolved value in EVERY path
      below. You did NOT write `~/.openrig/` literal anywhere in your
      build output.
- [ ] You computed `<song-slug>` deterministically (lowercase,
      accent-stripped, kebab-case) and created
      `<openrig-evaluations-root>/<song-slug>/` with the full subtree
      (`refs/`, `fingerprints/`, `renders/`, `diffs/`, `presets/`,
      `eval.md`) per **Step 0a**.
- [ ] Every user-provided reference WAV was `cp`'d (NOT symlinked)
      into `refs/<role>.wav` and sha256-verified against the source.
- [ ] Every analyzer fingerprint was `cp`'d into
      `fingerprints/ref-<role>.json` — not left only in
      `/tmp/openrig-analyzer/<ts>/`.
- [ ] The render command's `--output` pointed at
      `<openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav`
      — not at `/tmp/openrig-render/`.
- [ ] Every `compare.py` invocation read the ref from
      `refs/<role>.wav` and wrote `diff.json` to
      `diffs/<role>-v<N>.json` — not left only in the analyzer's
      scratch `/tmp/` dir.
- [ ] After every `save_chain_preset`, the live YAML was snapshotted
      to `presets/<role>-v<N>.yaml`, and on user-accept also to
      `presets/<role>-final.yaml`.
- [ ] `eval.md` was updated with a new iteration row per iteration,
      and `Status:` was set per outcome (`iterating` /
      `done` / `abandoned`).

## Red flags -- STOP

- Running `find crates/` or `grep MODEL_ID` or `Read` on any `.rs` file.
- Saying "I'll persist this rule in memory" / "I'll save this so I
  don't repeat it" / "I'll remember this for next time" / proposing
  any write to `~/.claude/projects/*/memory/` to capture a user
  correction. **Corrections never go to local memory.** Local memory
  is per-machine, per-user, doesn't ship with the plugin, isn't
  reviewed, isn't versioned — the next contributor / next install /
  next session on a different laptop sees nothing. Corrections go
  into the **SKILL** (this file) or the project's **`CLAUDE.md`**.
  If you find yourself wanting to "save a lesson", stop and edit
  the relevant `SKILL.md` instead — that's the durable artefact the
  next agent will load. See the project's `CLAUDE.md` ("Persistence:
  skill / CLAUDE.md over local memory") for the full rule.
- Writing chat output that **claims a playing technique** (palm-mute,
  fingerpicking, alternate picking, sweep, tapping, arpeggio,
  chugging, strumming pattern) about the user's reference WAV. The
  analyzer fingerprint does NOT measure technique. Stating it = pure
  fabrication, even when the song or artist makes it "obvious". See
  **Step 0 HARD RULE — no suppositions**.
- Inventing a difference between the bundled DI and the user's
  reference to explain a low match_score ("the DI is clean
  fingerpicking, Moisés played palm-mute"). Name real fingerprint
  deltas (`centroid Δ`, `band_energy Δ`, `THD Δ`, `time_fx`), never
  guessed performance differences. The gap is in the **preset**, not
  in invented technique.
- Using song-title / artist / era / genre knowledge as evidence about
  what's in THIS WAV. The user may have sent a cover, a different
  section, a live take, a remix, or a stem isolated imperfectly.
  Cultural priors feed **research** (Step 1), never claims about the
  audio.
- `Read` / `grep` / `Bash cat` / `WebFetch` on `blocks-reference.md`
  WITHOUT having read `openrig://plugins` in this turn first. The doc
  is a **recipe lookup keyed by `MODEL_ID`**, not a discovery channel.
  Greping it for amp brands (`vox ac30`, `marshall plexi`), song
  titles (`streets`, `clocks`), or artist names (`u2`, `slipknot`) to
  shortcut discovery is exactly the failure mode the user has
  corrected repeatedly. Discovery is `openrig://plugins`, always.
- Calling `add_chain` without first reading `openrig://devices` AND
  presenting the user the input/output menus AND capturing their
  explicit device + channels + mode picks for BOTH sides. A chain
  created without `Input` + `Output` blocks wired to real
  `device_id`s is unusable — the audio graph has no edges.
- Calling `remove_block` on the chain's current FX blocks while the
  user's active preset is still that chain's content (you're about to
  destroy their tone — switch to a new slot via `apply_rig_nav
  Preset(-1)` first).
- Calling `add_block` with `kind: utility` for `tuner_chromatic` or
  `spectrum_analyzer` — those are not chain blocks.
- Calling `save_project` to "persist" the preset (use
  `save_chain_preset`).
- Writing a YAML preset file to disk *without* the user having picked
  the file-only path in Step −1.
- Reporting "preset saved" / "done" to the user WITHOUT having run the
  mode-appropriate validation loop (Step 6) when any reference exists.
  **This is the failure mode the user called out explicitly**: "you're
  missing the most important thing. you should run the render". The
  render is mandatory in BOTH modes; if you reach `save_chain_preset`
  and have not yet rendered + judged (analyzer in Mode A, ear+user in
  Mode B), you have saved a guess. Restart from Step 6.
- **Treating a REAL recording as if `match_score` judged its timbre.**
  If the reference is not a same-DI reamp, iterating to raise
  `match_score` is chasing note-content/silence, not tone — it produced
  the documented "Gravity" disaster (low-pass to 750 Hz, quiet output,
  fabricated 865 ms delay, "converged" gap 166→131 dB that never
  meant anything). In Mode B the ear + user is the judge; `match_score`
  is a directional hint at most. Check the VALIDATION GATE before you
  iterate on any number.
- **Forbidding or dismissing the user's ear in Mode B.** When the
  reference is a real recording and the user says "it sounds muffled" /
  "too dark" / "the delay is too long", that is the **authoritative**
  validation signal — act on it. Replying "the match_score says it's
  fine" / "I can't judge by ear, the methodology decides objectively"
  is the exact inversion this rewrite fixed. The number that "decides
  objectively" only decides for a same-DI reamp.
- **Setting the delay/reverb blocks from `time_fx`.** The fingerprint's
  `time_fx.delay_time_ms` / `delay_feedback` / `reverb` are
  artifact-prone (a reverb tail reads as an 865 ms delay; a smooth hall
  reads as "spring"). Delay/reverb come from research + the song + ear
  (Step 2, Step 6 Mode B). `time_fx` is a weak corroborator, never the
  source of truth.
- **Low-passing / EQ-darkening off a low `centroid` on a sparse or
  separated stem.** A stem of sustained low notes + silence has a low
  centroid because of *which notes were held*, not because the guitar is
  dark. Read `centroid`/`band_energy` as directional shape cross-checked
  against the spectrogram + ear — never as a hard EQ target.
- **Matching the reference's RMS / level.** A real reference is often
  quiet; matching its RMS ships a quiet preset. Level is ALWAYS
  maximized in Step 7, never matched. Any `diff.json` RMS/level
  recommendation is ignored for tone.
- Declaring "done" with a render that peaks below -3 dBFS, or leaving
  the output trim at its default because "the tone converged". Tone
  convergence ≠ level done. **Step 7 is mandatory**: measure the peak,
  maximize the trim into [-2.0, -0.5] dBFS, confirm with a re-render.
  Quiet presets are the failure mode the user explicitly corrected
  ("you're building the tones way too quiet", 2026-06-12).
- Targeting -18 dBFS (or any K-system / broadcast alignment level) for
  the preset's output, or LOWERING the trim of an already-quiet render
  "to hit the standard". There is no -18 dBFS standard in this skill —
  the law is maximize-without-clipping (Step 7).
- Fixing loudness by raising amp gain/master, boost level, or limiter
  params after tone convergence. Loudness moves live on the final
  output-trim block ONLY; everything upstream is tone.
- Asking the user for a DI WAV file. **You don't.** The DI is bundled
  at `<openrig-source-root>/assets/audio/input.wav`. Only the *wet
  reference stem* comes from the user.
- Calling `add_block` with a `MODEL_ID` you have not cross-checked
  against `openrig://plugins` in **Step 2.5**. The runtime hard-matches
  IDs; an absent capture either crashes the call or silently selects
  nothing, and the user has no way to know you guessed.
- Silently substituting a missing capture for "the closest installed"
  amp/cab instead of proposing `openrig:openrig-tone3000-fetch` as
  the primary path in **Step 2.5**. Substitution is a last-resort
  fallback, not a peer option — propose `tone3000-fetch` first, and
  only ask about substitution after the import path is genuinely
  closed (no tone3000 result, fetch error, user veto). Even then,
  substitution requires asking the user to pick the specific
  substitute from a candidate list — never your auto-pick.
  Documenting it in Step 5 provenance after the fact does not
  retroactively authorize a unilateral decision.
- Presenting the **Step 2.5** ask as a peer (a)/(b) menu where
  `tone3000-fetch` and "substitute with `<your favorite>`" sit side
  by side as equivalent options. The user's stated rule: missing
  plugin → propose import first; substitution is only when there is
  no other solution AND still requires asking. The ask must lead
  with import; substitution surfaces only after import is closed.
- Calling `add_block` to "discover" which captures are missing instead
  of reading `openrig://plugins` upfront in **Step 2.5**. The error
  path is not a substitute for the gate — it pollutes the rig with
  partial state and routes the agent through a recovery flow the
  skill never validated.
- Narrowing the **Step 2.5** check to "just the NAM/IR captures" on
  the assumption that stock/native blocks are obviously installed.
  Every `MODEL_ID` gets checked — the cost is one resource read.
- Calling `set_block_parameter_*` with a `path` you didn't read from
  `openrig://plugins/{id}/params` in **Step 2.6**. The runtime
  hard-matches the string; `bass` and `eq.bass` are different params,
  and one of them silently does nothing. Trust the schema, not your
  memory of "similar amps".
- Picking the typed param tool (`_number` vs `_bool` vs `_text` vs
  `select_..._option`) from the param's *name* instead of from the
  schema's `domain` field. A param called `bias` could be a knob
  (FloatRange) on one plugin and a switch (Bool) on another — the
  schema decides.
- Reading the param schema from `blocks-reference.md` instead of from
  the MCP resource. The doc is the *recipes* source (which value to
  use); the **schema** (which path/type/range/enums exist) lives only
  in `openrig://plugins/{id}/params`.
- Opening any research URL, calling any MCP tool, or planning the FX
  layout **before** invoking `openrig:openrig-tone-analyzer` on every
  reference WAV the user provided. Step 0 comes first. No exceptions.
- Hardcoding `~/.openrig/` anywhere in your build output (Step 0a,
  Step 6, Step 8, eval.md path templates). The user-data root resolves
  per OS via `<openrig-user-data-root>` — detect once at the top of
  Step 0a, use everywhere. Hardcoding the legacy macOS path silently
  breaks every non-macOS user (Linux and Windows) AND breaks any macOS
  user on a fresh install who never had a `~/.openrig/` project root.
- Building a preset without creating `<openrig-evaluations-root>/<song-slug>/`
  per **Step 0a**. The persistent dir is the audit trail, the re-eval
  source, the portable backup. Skipping it ships the user a guess
  with no way to verify it later.
- Leaving renders or diffs in `/tmp/openrig-render/` or
  `/tmp/openrig-analyzer/<ts>/` and "planning to copy them at the
  end". `/tmp/` gets wiped, the agent forgets, the evidence is gone.
  Write directly to `<openrig-evaluations-root>/<song-slug>/renders/` and
  `…/diffs/` from the first iteration.
- Passing the user's original `/Users/.../refs/rhythm.wav` path to
  `compare.py` instead of the persistent copy in
  `<openrig-evaluations-root>/<song-slug>/refs/<role>.wav`. The original
  path can move, get deleted, or be on an unmounted drive — and the
  persistent copy is what every later iteration / re-eval is
  benchmarked against, so all scores must trace to the same file.
- Symlinking the user's WAV instead of copying it into `refs/`.
  Symlinks defeat portability — the whole `<song-slug>/` tree must be
  `tar`-portable to another machine.
- Batching all `eval.md` updates into one write at the end of the
  build instead of per-iteration. The interim rows are the score
  evolution; without them the user cannot see why iteration 4 beat
  iteration 2. Update per iteration.
- Reusing `<song-slug>/` from a prior build by `rm -rf`-ing it. Prior
  iterations are the user's audit trail; continue numbering, do not
  erase.

## Common rationalizations -- forbidden

| Rationalization | Reality |
|---|---|
| "The doc might be out of date" | Then file an issue. Don't read source. |
| "Just one quick grep to verify" | One grep is one violation. |
| "MCP isn't connected, I'll just write the YAML" | Stop and ask the user explicitly (see Step −1). Silent fallback violates user trust. |
| "I know this MODEL_ID from training" | Verify against the Quick Reference before using. |
| "It's faster to remove the existing FX blocks and replace them" | Faster, yes, and destructive to the active preset. Use `apply_rig_nav Preset(-1)` to switch to a new empty slot first. |
| "The user's `tuner_chromatic` mention means I should add it as a block" | Tuner is a rig-wide utility; it has its own enable command. The preset doesn't own it. |
| "The mix's centroid says the guitar is dark, so I'll EQ-darken" | The mix's centroid is dominated by bass/drums/keys. Look at an isolated stem before darkening — or you will produce a muddy preset (real Clocks rebuild failed for exactly this reason). |
| "I built it from research, no need to render" | Research = educated guess. The render is mandatory both modes; the only validated preset is one you rendered and judged (analyzer Mode A, ear+user Mode B). If the user has a reference, run it. |
| "I'll render+judge AFTER saving, that's the natural order" | The save IS part of the loop, not a terminator. Save → render → judge → adjust → … until done (converged in Mode A, user sign-off in Mode B). Reporting "done" after the FIRST save is reporting on a guess. |
| "The reference is a stem of the song, so render→compare→match_score will validate the timbre" | Only if the stem is a reamp of the bundled DI. A real recording is a different performance → `match_score` measures note content + silence, not tone. That is Mode B: the ear + user judges, `match_score` is a hint at most. Chasing it produced the "Gravity" muffled-and-quiet failure. Check the VALIDATION GATE first. |
| "`match_score` is low after several iterations — I'll keep applying recommendations until it converges" | In Mode B it will NOT converge — it's scoring different notes, not tone (the real case plateaued at a 131 dB gap that meant nothing). Stop iterating on the number; switch to ear + user verdict. Endless match_score chasing IS the failure. |
| "The user says it sounds muffled, but the match_score is fine — I'll trust the number" | In Mode B the user's ear is the authoritative validator and the number is not measuring tone. "Muffled / too dark / delay too long" is a direct instruction — act on it. Trusting the number over the ear is the exact inversion this skill was rewritten to kill. |
| "The fingerprint says delay 865 ms / 39% — I'll set the delay block to that" | `time_fx` is artifact-prone: that 865 ms was a *reverb tail* misread as delay, and the "spring" was a smooth hall. Delay/reverb come from research + the song + ear, never from `time_fx`. It is a weak corroborator only. |
| "The stem's centroid is ~480 Hz, so the tone is dark — I'll low-pass / EQ-darken" | On a sparse or separated stem the centroid tracks *which notes were held* (sustained low notes + silence), not timbre. Low-passing off it muffled the real "Gravity" build to 750 Hz. Read centroid as directional shape, cross-check the spectrogram + ear, never low-pass off the scalar. |
| "The reference RMS is quiet, so I'll match it / leave the preset quiet" | Level is never matched to the ref — a real reference is often quiet by performance or mastering. Step 7 always maximizes the output trim without clipping, independently of the reference. Matching RMS ships the broken-quiet preset the loudness law exists to prevent. |
| "I'll render the bundled DI and compare it to the real stem to get an objective timbre number" | The bundled DI is a *different performance* from the real stem. Comparing them measures note/silence content, not tone — structurally it cannot converge on timbre. That comparison is Mode B's *shape hint* (normalized LTAS over signal windows) at most; the ear + user is the judge. |
| "The standard output target is -18 dBFS, I'll trim to that" | Fabricated standard. -18 dBFS is a DAW/broadcast headroom convention, not a rig preset law. This skill's law is **maximize without clipping**: peak in [-2.0, -0.5] dBFS, aim ≈ -1.0 (Step 7). Trimming an already-quiet render DOWN to "-18 standard" is the exact baseline failure this rule exists to block. |
| "Tone converged, the level is a matter of taste — I'll leave the trim at default" | Level is not taste, it's Step 7: measure the render's peak, raise the trim until the peak lands in the window, confirm with a re-render. A converged-but-quiet preset feels broken next to the rig's other tones. |
| "I'll leave generous headroom (peak -10 dBFS) to be safe — the user can always turn it up" | The user CAN'T always turn it up — the preset competes with other bank slots at performance time, and "turn everything else up" is not a fix. The brickwall limiter is the safety; the trim's job is loudness. Maximize per Step 7. |
| "The limiter protects the output, so I can push the trim as high as I want without measuring" | The trim block sits AFTER the limiter — it can clip regardless. The confirmation re-render + peak measurement in Step 7 is the only proof. Measured, never assumed. |
| "The previous version of this preset worked without rendering, so I can skip this time" | Whoever told you that lied. **Every preset built without render+compare in this skill's history has been thrown away by the user.** Clocks v1 is the canonical example. No exceptions. |
| "There's no `openrig render` available, I'll skip" | If `openrig render` is genuinely missing from PATH, STOP and tell the user — do not silently skip the gate. The CLI ships with OpenRig; check `which openrig` and `openrig --help` for the `render` subcommand. |
| "The user didn't give me a DI, I can't render" | The user **never** gives you a DI. The canonical DI ships at `<openrig-source-root>/assets/audio/input.wav`. Reading the skill for the path is on you. |
| "I'll research first to know what to look for, then fingerprint" | Wrong order. Research without the fingerprint is theater — you bias toward what "sounds right on paper". Step 0 (fingerprint) comes before Step 1 (research). |
| "The user gave me WAVs but I already know the song, fingerprint is redundant" | The WAVs are the user's reference take, not the song you remember. Era, mix, performance and the user's playing all shift the fingerprint. Run Step 0. |
| "I'll fingerprint just one stem and reuse it for the other role" | Rhythm and lead have different gain stages, different time effects, different EQs. Fingerprint **each** WAV — that's what produces the role-specific presets the skill promises. |
| "`tone3000-fetch` is heavy (issue → PR → qa_audit gate), I'll just substitute" | Cost is the user's decision, not yours. **Step 2.5 leads with `tone3000-fetch` as the primary proposal — substitution is a fallback, not a peer.** Propose import; if the user vetoes that path explicitly, then ask which specific substitute. Deciding for them = deciding that the tone doesn't matter — but they asked for THE tone, not A tone. |
| "The closest already-installed capture is 'close enough'" | "Close enough" is the user's judgment, not yours. Ask in **Step 2.5** — and only after the `tone3000-fetch` import path is closed. Step 5 provenance documents authorized substitutions; it does not retroactively authorize yours. |
| "The record used a 4x12, so I'll add the era-correct cab IR after the NAM amp" | If the capture's `effect_type` is `amp`, the cabinet is already IN the capture — an IR on top is a double cabinet (muffled v1, thrown away). Cab IRs pair only with `effect_type: preamp`. Read `effect_type` in Step 2.6; the real rig's cab list is research color, not a block to add. |
| "I'll present `tone3000-fetch` and substitute side-by-side as (a)/(b) — let the user pick whichever" | NO. The two are not peers. The user has stated the rule: missing plugin → propose import first; substitution only when no other solution; even then ask. The ask leads with `tone3000-fetch`; substitution surfaces only if (a) is closed (no tone3000 result, fetch error, or user veto). |
| "I'll auto-pick the closest substitute and just confirm with the user (y/n)" | The y/n shortcut collapses the candidate list to one option of your choosing. When substitution is genuinely the path forward (after `tone3000-fetch` is closed), present 3–5 candidates from `openrig://plugins` with matching `block_type` and adjacent `brand` / `display_name` — let the user pick. Auto-picking + asking confirmation is the same anti-pattern as auto-picking. |
| "`blocks-reference.md` lists this `MODEL_ID`, so I can call `add_block`" | The doc lists what the project KNOWS how to load. `openrig://plugins` lists what THIS rig actually has loaded. The two diverge — always check the second one in **Step 2.5**. |
| "I'll grep `blocks-reference.md` for `vox ac30` / `streets` / `u2` to find the `MODEL_ID` faster" | NO. That's discovery. Discovery is `openrig://plugins` ALWAYS. The doc is consulted AFTER, by `MODEL_ID`, for recipe (knob values, pairings). Greping the doc by amp brand, song or artist = wrong use. Behaviour already corrected several times in this conversation — do not repeat. |
| "The doc has a section about U2 / Edge / Coldplay, I'll start there" | The section is recipe (knob settings, pairings) — useful AFTER you have the `MODEL_ID` via `openrig://plugins`. Starting from the doc inverts the order and silently ignores installed plugins that are not in the doc. Step 2 HARD GATE: plugins first, doc after. |
| "I have a strong prior on the tone, I'll go straight to the doc to confirm" | "Strong prior" does not replace reading `openrig://plugins`. The user may have an installed plugin that matches the prior better than what's documented. Step 2 sub-step 1 (read `openrig://plugins`) is unconditional. |
| "Moisés is playing palm-mute on Metallica, so the ref will have heavy palm-mute" | NO. You don't know what's in the ref before reading the fingerprint. Cultural prior (song/artist/era) is NOT evidence about THIS specific WAV. The analyzer does not measure palm-mute. Say "the fingerprint shows `dynamics_profile: rhythmic` and `tone_profile: high_gain`" — don't fabricate technique. |
| "I'll explain the gap between wet and ref as 'the performance is different' (DI fingerpicking vs Moisés palm-mute)" | Inventing a performance difference to justify a low match_score = moving the blame from the preset onto a fabrication. The real gap is what the diff's `Δ` fields show (centroid, band_energy, THD, time_fx). Cite the deltas — don't invent technique. |
| "Edge uses dotted-eighth delay, so the Streets ref will have delay with high mix" | "Edge uses" is a cultural prior for Step 1 (research that maps gear). About THIS WAV, only the fingerprint speaks: look at `time_fx.delay_present` / `delay_time_ms_estimate` / `delay_feedback_estimate_pct`. If the fingerprint shows no delay, the ref has no delay in that section — regardless of what Edge does. |
| "The song is Metallica, so the tone is obviously high_gain — I'll skip the fingerprint" | Step 0 is unconditional. The WAV could be a cover, a different take, a clean mix, or a take before the dist was switched on. You READ the fingerprint, always. "Obvious" + cultural prior = exactly the failure this skill exists to block. |
| "The user corrected me — I'll save this lesson to memory so I don't repeat it" | NO. Local memory (`~/.claude/projects/*/memory/`) is per-machine, per-user, doesn't travel with the plugin. A correction becomes an edit in `SKILL.md` (this skill) OR in the project's `CLAUDE.md`. If the user corrects a skill behavior, the fix is literally THIS sentence here — add a Red Flag, a Rationalization, or a sub-step that blocks the behavior. Memory ≠ persistence. |
| "I'll suggest to the user that they save this in their memory for next session" | Even worse — you outsource to the user a decision that is the skill's responsibility. If the correction is valid, it's already part of the skill's contract — it goes into `SKILL.md`. No pushing maintenance onto the user's local storage. |
| "The user asked for the preset, fetching a capture is out of scope for tone-builder" | Out of scope would be direct dispatch; Step 2.5 only OFFERS the fetch as (a) and delegates to `openrig-tone3000-fetch` when the user accepts. Not offering = silently deciding for (b). |
| "I'll let `add_block` fail and then run Step 2.5 when I discover the error" | Wrong order. 2.5 is a **precondition** for Step 3, not recovery. The error path pollutes the log, leaves partial state in the chain, and bypasses the (a)/(b) question. Read `openrig://plugins` FIRST. |
| "Stock blocks (`compressor_*`, `gate_basic`, `limiter_brickwall`) are built-in, obviously installed — I'll only check the NAM/IR ones" | Step 2.5 says **for every `MODEL_ID`**. Stock can be disabled in custom builds, renamed across versions, or absent in forks. The cost of the cross-check is one resource read — not worth saving. |
| "I remember the path of this param from a similar amp (`bass`, `gain`, etc.) — I don't need to read `openrig://plugins/{id}/params`" | Memory kills. Different plugins in the same family use different paths (dotted vs flat, distinct prefixes, missing knobs). `set_block_parameter_number` with the wrong path fails silently. Read the dynamic schema — one resource read per `MODEL_ID`. |
| "`blocks-reference.md` lists this amp's params, so that's schema enough" | The doc is the *recipes* source (which value to pick within the valid range), not the schema. Authoritative schema is `openrig://plugins/{id}/params` — runtime, cannot be stale. The doc can drift. |
| "I'll infer the tool (`_number` vs `_bool`) from the param's name" | The schema's `domain` decides, not the name. The same param called `bias` could be `FloatRange` (knob) on one plugin and `Bool` (switch) on another. Read `domain`. |
| "I'll cache the schema for this amp family and reuse it for similar ones" | Each `MODEL_ID` has its own schema. Cache ONE read per MODEL_ID per build — don't share across families. Cost is minimal (one resource read), benefit is zero path errors. |
| "The `domain.Enum` gives me `value` AND `label`; I'll pass the `label` which is more readable" | No. `select_block_parameter_option` takes the `value`. Passing the `label` fails. |
| "Only one chain matches the song's `instrument`, I'll go straight to it without asking" | Step 3.1 always renders the menu, even when only one chain matches. You MAY suggest the obvious option in the message, but wait for the user's pick. "Convenience" = deciding for the user = exactly the auto-pick the user reported. |
| "I'll use the chain/preset name from the skill's examples" | Names in the skill text's examples are FORMAT illustrations, not real chains or presets. Read `openrig://project` and use the actual values from there. (If your rig happens to have a chain with the same name as an example, that's coincidence — you still present the Step 3.1 menu and wait for the pick.) |
| "User pre-confirmed the chain in the args / in the invocation / in the initial context — I'll go straight in" | Stop. You're about to invent a user message that doesn't exist. Re-read EXACTLY what the user sent this turn. If you cannot paste a verbatim sentence from the user saying "use chain X" or "put it in <id>" / "put it in <name>", the user did NOT pre-confirm. Present the Step 3.1 menu and wait. "Pre-confirmed in args" without verbatim quote = fabrication. |
| "The project name / the skill invocation already signals which chain to use" | No. Project name, skill name, system prompt, MCP context — none of that is the user's choice about where to put the preset. Only explicit user messages in chat count. Present the menu. |
| "The user already told me the chain in another conversation / in a previous chat" | Another conversation doesn't count. Every build of the skill starts fresh at Step 3.1; the menu always runs in the current turn. Cross-session memory is forbidden (same rule as cross-session schema). |
| "The rig has no chain for the instrument of this song, I'll stop and ask the user to create one in the GUI" | Old behavior. Now: in Step 3.1, offer the `(N+1) create new chain` option, ask for name + instrument + I/O devices, and call `add_chain` when the user accepts. Stop and push to the GUI only if the user explicitly refuses to create through the skill. |
| "I'll call `add_chain` with just `instrument` and the engine resolves the rest" | It doesn't resolve. `Chain.blocks` arrives empty → chain with no Input or Output → audio graph with nowhere to read/write → useless chain. Read `openrig://devices`, offer menus, build `blocks: [Input, Output]` before calling. |
| "The user already mentioned the `Scarlett 2i2` earlier in this conversation, I'll use that" | Conversational memory does not replace the current ask. Read `openrig://devices` now; render the menus; wait for the pick. The user may have swapped interfaces between turns. |
| "I'm clever, I'll infer the input from the `instrument` (mono for guitar) and default channels=[1] mode=mono" | A reasonable convention is mono input = 1 channel, stereo output = 1,2. Use that as a **suggestion in the message** (`"I recommend [1] mono for guitar input"`). Auto-applying without the user confirming = deciding their cabling. Always ask. |
| "I invented a plausible `device_id` because the `openrig://devices` read failed" | Forbidden. If the read fails, STOP and show the error to the user; don't guess. `device_id` is a hard-matched string in the runtime — a guess = `add_chain` errors and partial state in the rig. |
| "I can pass `blocks: []` and add Input/Output later with `add_block`" | No. The skill's design creates the chain ALREADY wired (`Chain.blocks` with Input + Output) in a single `add_chain`. Trying I/O via `add_block` conflicts with the "input/output are user wiring, don't touch" rule from Step 3.5/anti-patterns. Build everything in the `add_chain` payload. |
| "Step 0a is bookkeeping, the user wants the tone, not a folder structure" | Step 0a IS part of delivering the tone. Without `<song-slug>/`, the next time the user asks to re-validate against the same ref, you can't (Step 8 becomes impossible). Bookkeeping is what makes "the tone" auditable, portable, and re-comparable — skipping = delivering a guess with no evidence. |
| "I'm on a Mac, I can use `~/.openrig/` directly — it's shorter" | No. The skill is published for all OSes. `~/.openrig/` on Mac is a legacy dev project root path — it is not the user-data root. Use `<openrig-user-data-root>` resolved per OS (macOS → `~/Library/Application Support/OpenRig/`, Linux → `${XDG_CONFIG_HOME:-~/.config}/OpenRig/`, Windows → `%APPDATA%\OpenRig\`). Shorter is not worth silently breaking Linux/Windows users. |
| "I'll render to `/tmp/` which is faster and copy to `evaluations/` at the end" | A hole in your short-term memory = losing the evidence. `/tmp/` is wipeable. "At the end" often doesn't happen (timeout, error, interruption). Write DIRECTLY to `<openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav` from the first iteration — there's no shortcut worth the risk of lost evidence. |
| "Passing the original ref path to `compare.py` is the same as passing the copy in `refs/`" | No. The original path can move, be deleted, or be on an unmounted drive when the user asks for re-eval. The copy in `refs/<role>.wav` is immutable (sha256-verified) and is what ALL iterations + Step 8 compare against — every score must trace to it. Always use the persistent path. |
| "Symlinking instead of `cp` to `refs/` saves disk" | Saves disk, breaks portability. `tar czf backup.tgz <openrig-evaluations-root>/` needs to work and produce a self-contained archive. Symlinks break either at `tar` time (becoming relative links) or at extract time on another machine. Always `cp`. |
| "I'll update `eval.md` only at the end, with all iterations at once" | No. The interim rows are the score evolution — without them you can't show the user why v4 beat v2. Append a row per iteration, at the end of Step 5 of each loop. |
| "`<openrig-evaluations-root>/<song-slug>/` already exists from a previous build — I'll `rm -rf` to start clean" | No. That erases the user's audit trail. Read `eval.md`, continue iteration numbering after the last `<role>-v<N>`, and keep the old YAMLs as history. Only delete if the user explicitly asks. |
| "The placeholders `<Song>` `<Artist>` `<chain id>` in the `eval.md` template are literals — I'll write them as-is" | No. Placeholders in SKILL.md are slot markers — you substitute them with the real build values (real song title, real artist, real chain id read from `openrig://project`). If the final `eval.md` in the user's folder literally contains `<Song>` or `<Artist>`, you didn't do the build, you echoed the template. |

## Workflow (file-only path)

If the user picked the file-only path in Step −1:

1. Do **steps 1, 2** of the MCP workflow (research + map gear). Skip
   the MCP precondition.
1b. **Installedness + schema on the file-only path.** If the OpenRig
   MCP server happens to be reachable in this session anyway (rig
   running with `--mcp`, just not the persistence path the user
   picked), run **Step 2.5** to flag missing captures AND **Step 2.6**
   to read the param schema for every chosen `MODEL_ID`. Without the
   schema you cannot pick valid param paths for the YAML — guessed
   paths fail silently at `Load Preset` time. If MCP is offline, you
   **cannot verify installedness OR read the schema from here** —
   list **every** `MODEL_ID` your plan uses (not only the exotic
   NAM/IR ones — every block including stock processors) in your chat
   reply, label the list explicitly as **"unverified installedness AND
   unverified param paths — your rig may not load this YAML cleanly"**,
   recommend the user run `openrig:openrig-tone3000-fetch` against any
   captures they don't have locally, and recommend they load the YAML
   once in OpenRig and check the GUI for any silently-ignored params
   (an ignored param means the path was wrong). Do NOT silently trust
   the plan; the user is your installedness AND schema oracle when MCP
   is offline.
2. Determine the YAML output path:
   `<openrig-user-data-root>/presets/<Song> — <Artist> (<role>).yaml`
   (resolved per OS as defined in Step 0a — macOS →
   `~/Library/Application Support/OpenRig/presets`, Linux →
   `${XDG_CONFIG_HOME:-~/.config}/OpenRig/presets`, Windows →
   `%APPDATA%\OpenRig\presets`; ask the user once if the rig has a
   non-default `presets_path` configured).
3. Write the YAML in the schema OpenRig's `LoadChainPreset` expects.
   The minimum is the `blocks:` list with one entry per FX block and
   the parameters resolved from the **MCP schema** (`openrig://plugins/{id}/params`,
   read in Step 1b when MCP is reachable). The recipe values come from
   `blocks-reference.md`. The chain's I/O blocks are NOT included (the
   preset only carries FX). If MCP is offline you cannot read the
   schema — flag every param value as "unverified path" in a comment
   at the top of the YAML and recommend the user load it once in
   OpenRig and check the GUI for any silently-ignored params.
4. Print the file path and tell the user: "To hear it, open OpenRig,
   select chain `<chain>`, and use **Load Preset** pointing at this
   file. The in-memory rig was not touched." *(render in the user's
   language at runtime — this English template documents the
   structure, not the literal words to ship)*
5. Skip the render+compare loop unless the user explicitly opts in
   later (would require switching to the MCP path for the render).
6. **Persistent evaluation dir on this path.** Step 0a still applies:
   resolve `<openrig-user-data-root>` for your OS (same per-OS table
   as Step 0a), compute `<song-slug>`, create
   `<openrig-evaluations-root>/<song-slug>/`, `cp` the ref WAVs into
   `refs/<role>.wav` with sha256 verification, persist the
   fingerprints into `fingerprints/ref-<role>.json`, and snapshot the
   YAML you write in step 3 into `presets/<role>-v1.yaml` (and
   `presets/<role>-final.yaml` if the user accepts it as-is). The
   `renders/` and `diffs/` subdirs stay empty until the user later
   switches to the MCP path — re-evaluation via **Step 8** is
   unavailable on the file-only path because `openrig-render`
   requires the live runtime. Initialise `eval.md` with `Status:
   iterating` and a methodology note saying "file-only build, no
   render+compare evidence — score columns will populate on first
   MCP re-eval".

## Anti-patterns (all paths)

- ❌ **Calling `add_chain` WITHOUT the user picking "create new
  chain" in Step 3.1 AND answering ALL FOUR prompt blocks (name +
  instrument; input device + channels + mode; output device +
  channels + mode; explicit go-ahead).** `add_chain` is only
  legitimate as the explicit Step 3.1 sub-flow result — never to
  "make a slot for the tone" (that's `apply_rig_nav Preset(-1)`),
  never to "re-shape" an existing chain, never silently when the user
  said "preset" generically. Chain ≠ slot: a chain is a top-level rig
  group with its own I/O; a slot is one preset position inside a
  chain's bank.
- ❌ **Calling `add_chain` with `blocks: []`, or with only an Input
  but no Output (or vice versa), or with placeholder/inferred
  device_ids.** A chain without both Input and Output blocks is
  unusable — the audio graph has nowhere to read from or write to.
  Always read `openrig://devices` first and use the user's explicit
  pick for device_id, channels, and mode on both sides.
- ❌ **Inferring the input/output device from chat history, from the
  song genre, from the `instrument` tag, or from memory of a prior
  conversation.** "Probably the Scarlett because the user mentioned
  it yesterday" = deciding for the user. Read `openrig://devices`
  this turn and render the menu, regardless of what was said before.
- ❌ **Substituting the I/O menus in Step 3.1 with a narrowed "use
  Scarlett mono 1ch in + Scarlett stereo 1,2 out? (y/n)" ask.** Same
  anti-pattern as the chain-pick y/n shortcut: it pre-selects what
  you wanted and hides the alternatives. Render both menus; let the
  user pick.
- ❌ **Auto-picking a chain in Step 3.1 because its `instrument`
  matches the song (or because it's the only candidate, or because
  it's the only chain in the project).** Step 3.1 always renders the
  full menu and waits for the user's pick — that's the entire point
  of the step. Even "only one obvious match, I'll go straight to it"
  is the auto-pick behaviour the step exists to block.
- ❌ **Substituting the full numbered menu in Step 3.1 with a
  narrowed "use `<chain>`? (y/n)" ask.** Y/n hides the other chains
  AND hides the "create new chain" option. Render the menu, every
  time.
- ❌ **Editing the chain's current blocks directly to write a new
  preset.** That destroys the user's existing active preset. Switch
  slots first.
- ❌ **Calling `save_project` instead of `save_chain_preset`.** The
  preset is the unit of work.
- ❌ **Overwriting an existing preset for the song without asking.**
  Step 0 is non-negotiable.
- ❌ **Including `tuner_chromatic` or `spectrum_analyzer` in the
  plan.** Both fail at `add_block` time.
- ❌ Inventing a model name that "sounds right" -- every model name is
  a hard-matched string in the registry.
- ❌ Using a `preamp` block for a full amp song -- `preamp` is
  preamp-only (no power amp / cab). Songs almost always want `amp`.
- ❌ **Adding a `cab` block after an `effect_type: amp` capture.** Full
  amp captures already contain the cabinet — a cab IR on top is a double
  cabinet. Cab IRs pair only with `preamp` captures. "The G12T-75 is the
  era-correct cab for this amp" is not a reason; `effect_type` is the
  only deciding signal (see the AMP vs PREAMP vs CAB pairing rule in
  Step 2).
- ❌ Silently switching from MCP to file (or vice versa) without the
  user's explicit Step −1 answer.
- ❌ Stopping at "saved" when a reference stem was provided — run the
  render+compare loop before declaring done.
