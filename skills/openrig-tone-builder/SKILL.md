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

> "Procurar pelo preset, não pela chain." Your job is to write a
> **preset**. The chain is just the rig slot it lives in.

This skill **only ever creates or updates presets**. Crucially, it
**adds a NEW slot to the chain's bank** for the preset — it does **NOT**
edit the chain's currently-loaded blocks (that would destroy the user's
existing active preset). See Step 3.

**Before doing anything else, check whether a preset for this song already
exists.** Overwriting tone work the user spent time on is the worst-case
failure mode for this skill. See Step 0 of the workflow.

## ⛔ HARD GATE — render+compare BEFORE declaring done (read this first)

The render→compare loop in **Step 6 is MANDATORY** when the user
provides any reference audio (an isolated guitar stem, a WAV of the
song, anything). It is **not** a closing nicety; it is the only
objective signal this skill produces. **Saving a preset without
rendering+comparing is saving a guess** — exactly the failure mode that
produced the Clocks v1 the user threw away.

You may NOT declare the preset done — and you SHOULD NOT call
`save_chain_preset` as the "final" save — until you have:

1. **Confirmed the bundled DI exists** at
   `<openrig-source-root>/assets/audio/input.wav` (mono 48 kHz, the
   canonical reamp DI; ships with the OpenRig repo). You do **not** ask
   the user for a DI — only the *wet* reference comes from them.
2. **Rendered** the DI through the just-built preset via the
   `openrig render` CLI.
3. **Compared** the rendered output to the user's reference stem with
   `openrig-tone-analyzer/scripts/compare.py`, read `diff.json`,
   applied **one** recommendation, re-rendered, re-compared.
4. **Iterated** until `diff.converged` is true OR `match_score`
   plateaus across two consecutive iterations — at which point you
   report the gap and the score to the user, not "done".

If the user explicitly says they have no reference, declare that
**out loud in the chat** before Step 8 (`save_chain_preset`) — "no
reference stem provided, this preset is a research-only guess; I
cannot validate it" — so the user can decide whether to provide one
or accept the limitation. Silent skipping = failure of the skill.

The DI path is `<openrig-source-root>/assets/audio/input.wav`. Not
`assets/sound/`, not `~/Music/`, not a fresh user-supplied DI. This
one file. If it is missing from the OpenRig repo, that is a bug in
the repo — stop and tell the user, do not improvise.

## Step −1 — Ask the user: MCP live or YAML file only?

Before touching anything, ask **once** which persistence path the user
wants. Both paths are valid; the right choice depends on whether
OpenRig is running:

> "Pra esse preset, vou: **(a) via MCP no rig ao vivo** (slot novo na
> bank, audível na hora — requer OpenRig com `--mcp`), ou **(b) só
> arquivo YAML** (escrevo em `<openrig-user-data-root>/presets/<name>.yaml`, sem
> tocar no rig)?"

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
| iter | match_score | RMS Δ | centroid Δ | mudança chave |
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
The fingerprint is the **primary input** that shapes every subsequent
decision; research only fills in what the signal cannot reveal
(specific amp model/era, brand of pedal). Going straight to research
is the most common failure mode of this skill — it biases the preset
toward what "sounds right on paper" rather than what the recording
actually contains.

How:

1. For each reference WAV the user mentioned, invoke
   `openrig:openrig-tone-analyzer` with the file path. The skill writes
   a JSON fingerprint plus spectrogram PNGs to disk and returns the
   paths. The JSON carries `centroid`, `rolloff`, `band_energy`,
   `gain_character`, `time_fx` (delay/reverb estimates) and `source.kind`
   (rhythm/lead/solo/clean — often inferred from filename).
2. **Read every fingerprint JSON before opening any research URL.** The
   fingerprint tells you:
   - EQ curve to target (centroid + band_energy → parametric EQ shape)
   - Gain stage (gain_character → clean / crunch / high gain)
   - Time effects (time_fx → delay time, feedback, reverb size)
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

Pick candidate `MODEL_ID`s by reading `openrig://plugins` (the **discovery** source from the Iron Rule) and matching `block_type` + `brand` + `display_name` to the gear you researched. Use [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) **only** for *recipes* — which amp family pairs with which cab, suggested knob ranges per style, per-song settings. Always prefer NAM amps over Native amps when the song has a real amp model. The param schema for whichever IDs you pick comes from `openrig://plugins/{id}/params` in **Step 2.6**, not from this step.

**The Step 0 fingerprint is your primary input here.** Walk each
field against the `blocks-reference.md` *recipes*:

- `centroid` + `band_energy` → parametric EQ band gains
- `gain_character` → amp model class (clean / crunch / high-gain) and
  whether a boost block is needed
- `time_fx.delay` → delay block model, time_ms, feedback, mix
- `time_fx.reverb` → reverb block (room vs hall), room_size, mix
- `source.kind` → preset name role and whether to build multiple
  presets

Research only fills in what the fingerprint cannot reveal (the exact
amp model the player used, brand of overdrive, era of cab).

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

2. **For every `MODEL_ID` in the plan, check it's in that set.** "Every" = literally every one, including stock blocks like `compressor_studio_clean`, `gate_basic`, `eq_eight_band_parametric`, `limiter_brickwall`, `volume`, `native_guitar_eq`. The runtime hard-matches on the `id` string regardless of `backend`; narrowing the check to "only NAM/IR captures" is forbidden. For every miss, the user gets ONE clear choice — never make it for them:

   > "Pro [bloco/papel] o capture canônico é `<MODEL_ID>` (do `<amp/cab/...>`), mas ele não está instalado nesta rig.
   > Como prossigo?
   > **(a) importar via `openrig:openrig-tone3000-fetch <query>`** — capture autêntico do tone3000.com, mas dispara o fluxo issue → PR → qa_audit/pack_plugins (pesado).
   > **(b) substituir** por `<closest_installed_MODEL_ID>` (`<display_name>`, mesmo `block_type`) — rápido, mas é um *palpite no timbre*, não O timbre.
   > Default sugerido: **(a)** quando você pediu um amp/música específico; **(b)** quando você está só esboçando."

   The "Default sugerido" line is what you **recommend TO the user inside the ask message** — it is NOT a self-applied default. You always wait for the user's explicit answer. Auto-classifying the request as "just sketching" and applying (b) without sending the ask is the silent substitution this step forbids. If the user does not answer, ask once more or stop; never decide for them.

3. **Apply the user's choice before resuming the build:**
   - **(a) import** → invoke `openrig:openrig-tone3000-fetch` with the relevant search term (artist, amp model, capture name). After the fetch skill lands the file under `OpenRig-plugins` AND clears the qa_audit/pack_plugins gate, the user's OpenRig instance must reload its catalog (`reload_plugin_catalog` MCP tool) before the new `MODEL_ID` appears in `openrig://plugins`. Re-read `openrig://plugins` to confirm presence before calling `add_block`.
   - **(b) substitute** → record the substitution explicitly in the Step 5 provenance ("substituted `<wanted>` → `<used>` per user OK"). The substitution is authorized by THIS step, not by the Step 5 disclosure.
   - **(c) user wants to abort** → stop, do not save anything.

4. **One ask per missing capture.** If four blocks miss four different captures, you ask four times — or batch them in one message listing all four with (a)/(b) per row. Do NOT collapse "I'll substitute all of them" into a single unilateral decision.

5. Do not proceed to Step 2.6 until every `MODEL_ID` in the plan is either present in `openrig://plugins` OR explicitly substituted with the user's OK in (3b).

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

1. **Read `openrig://project` and ALWAYS ask the user where to put this preset.** List every chain in the project with its id, display name, `instrument`, and a short summary of its current blocks. Build a numbered menu — **including when only one chain matches the song's instrument** — and add a final "criar chain nova" option. Do NOT auto-pick. The shape (replace with real chains from the project read; do NOT echo example chain names from this skill text):

   > "Onde quer colocar o preset?
   > **(1)** chain `<id>` ('<display name>', instrument `<x>`, blocos atuais: `<short summary>`)
   > **(2)** chain `<id>` ('<display name>', instrument `<y>`, ...)
   > ...
   > **(N+1) criar chain nova** — eu pergunto nome + instrumento e chamo `add_chain`."

   You MAY recommend one option in the ask message (e.g. "sugiro **(1)** porque o `instrument` bate com o estilo da música"), but you **MUST wait for the user's explicit pick**. Auto-selecting because "só uma chain bate com o instrumento" is forbidden — that is the deterministic "marreta" behaviour this step exists to prevent.

   **If the user picks `(N+1) criar chain nova`**, sub-flow:
   - Ask the user the **chain name** (free text, e.g. "Lead Solos", "Rhythm — Drop D", "Clean Acoustic") **AND** the **`instrument`** tag (`electric_guitar` / `acoustic_guitar` / `bass_guitar` / etc.) in the same ask, OR one after the other if you must.
   - If the user answers only one of the two (e.g. name but not instrument), **re-ask the missing one explicitly**. Never infer the instrument from the song or from the chain name. The user picked "criar chain nova" and must answer both prompts; checklist requires it.
   - Call `add_chain { name, instrument, ... }` and capture the returned chain id. If `add_chain` errors (duplicate name, invalid instrument, etc.), **STOP and surface the exact error to the user** — do not retry with a mutated name, do not silently switch to one of the existing chains. Ask the user to either correct the input or pick a different option from the menu.
   - Once you have the new chain id, continue the preset build into it.

   **If `openrig://project` returns ZERO chains**, you may go straight to the create-new sub-flow (still asking name + instrument), but say out loud "sua rig não tem chains ainda — vou criar uma" so the user knows. Don't render an empty menu.

   **If `openrig://project` returns exactly ONE chain**, you still render the menu (option 1 = that chain, option 2 = criar nova). The "menu always" rule has no carve-out for project size.

   **If the user does not answer**, ask once more or stop. Never decide for them.

   **Forbidden short-form ask:** rendering a single-line "use `<chain>`? (y/n)" instead of the full numbered menu is the same anti-pattern as auto-picking — it pre-selects the option you wanted and hides the alternatives (other chains + criar nova). Always render the full menu; the "y/n shortcut" is forbidden even when only one chain matches the instrument.

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
10. gain    / <volume_model_id>            enabled:true   intent: per-preset output trim
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

### 6. Render and A/B compare (MANDATORY validation loop — runs BEFORE you report "done")

> ⛔ **This is the hard gate from the top of the file.** If the user
> provided a reference WAV — or if you can reasonably infer they expect
> the preset to match a real recording — this loop is NOT optional and
> NOT post-hoc. Without it, your preset is a research-grade guess and
> the user has no way to tell. Run it BEFORE declaring done; iterate
> until convergence; only then report.

1. Render the **canonical bundled DI** through the just-saved preset
   via `openrig-render` (headless DSP renderer). Write directly to the
   persistent evaluation dir created in **Step 0a** — NOT to
   `/tmp/openrig-render/`:
   `openrig render --preset "<Song> — <Artist> (<role>)" --input
   <openrig-source-root>/assets/audio/input.wav --output
   <openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav`. `<N>`
   is the current iteration index — start at `1` for a fresh build,
   continue from `last_existing_N + 1` when reusing an existing
   `<song-slug>/` directory (see Step 0a "Reuse vs first-build"). The
   DI ships with OpenRig (the NAM-standardized reamp input — covers
   the dynamic range and frequency content needed to characterize a
   chain). You never ask the user for a DI; only the reference *wet*
   stem comes from them.
2. Compare the rendered output against the **persistent** reference
   stem with `openrig-tone-analyzer` in compare mode: `.venv/bin/python
   scripts/compare.py <openrig-evaluations-root>/<song-slug>/refs/<role>.wav
   <openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav --output
   <openrig-evaluations-root>/<song-slug>/diffs/<role>-v<N>.json`. Always
   pass the ref from `refs/<role>.wav` (copied in Step 0a), never the
   user's original path — the persistent copy is what every iteration
   compares against so scores stay comparable across re-builds. If
   `compare.py` does not accept `--output`, capture stdout and `cp` /
   write `diff.json` into the persistent `diffs/<role>-v<N>.json` path
   yourself; the file MUST land in the persistent dir either way.
3. Read the produced `diffs/<role>-v<N>.json`. The top 2-3
   `recommendations` are concrete, priority-sorted instructions (e.g.
   "raise EQ band 4 gain by 3 dB", "delay time wrong by 80 ms",
   "needs more high-shelf").
4. **Apply ONE recommendation at a time** with the relevant
   `set_block_parameter_*` call, re-render, re-compare. Iterate until
   `diff.converged` is true OR `match_score` plateaus. Each iteration
   bumps `<N>` and writes a new `renders/<role>-v<N>.wav` +
   `diffs/<role>-v<N>.json` — never overwrite an existing iteration
   file (the iteration log in `eval.md` references them).
5. **After every `save_chain_preset` in this loop**, snapshot the just-saved
   preset YAML into the evaluation directory:
   `cp <openrig-user-data-root>/presets/"<Song> — <Artist> (<role>)".yaml
   <openrig-evaluations-root>/<song-slug>/presets/<role>-v<N>.yaml`
   (use the OS-appropriate `presets_path` if not the default). The
   snapshot is the only way to re-render a historic iteration — the
   live YAML at `<openrig-user-data-root>/presets/` only carries the latest version
   and gets mutated by every later `save_chain_preset` call. When the
   user accepts the preset (loop converges or user calls done), also
   `cp` the final YAML to `presets/<role>-final.yaml` — that's the
   pointer the Step 8 re-evaluation flow uses.

Without the render→compare loop, you are building from research +
analyzer fingerprint alone — that's an **educated guess**, not a
measured match. Flag this in the chat reply so the user knows.

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
- [ ] Any missing captures were resolved through **Step 2.5** with the
      user's explicit (a) import via `openrig:openrig-tone3000-fetch` /
      (b) substitute choice, and the resulting substitution (if any) is
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
      picked the "criar chain nova" option in Step 3.1 and answered
      both the name and instrument prompts. You did NOT call
      `add_chain` for any other reason.
- [ ] You did NOT auto-pick a chain in Step 3.1 just because its
      `instrument` matched. You rendered the menu and waited for the
      user's explicit pick, even when only one chain matched.
- [ ] You did NOT call `save_project` (the preset is the unit of work).
- [ ] You did NOT add `tuner_chromatic` or `spectrum_analyzer` via
      `add_block` (they are rig-wide commands, not chain blocks).
- [ ] You did NOT touch any `input`, `output`, or `insert` block on
      the chain — those are the user's rig wiring.
- [ ] If a reference stem was provided, you ran the render+compare
      loop and either reached `diff.converged` OR documented the
      remaining gap in the chat reply.
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
- Reporting "preset salvo" / "preset saved" / "done" to the user
  WITHOUT having run at least one render→compare cycle when any
  reference audio exists. **This is the failure mode the user called
  out explicitly**: "ta faltando a coisa mais importante. vc deveria
  rodar o render". If you reach `save_chain_preset` and have not yet
  rendered, you have NOT validated the preset — you have saved a
  guess. Restart from Step 6.
- Asking the user for a DI WAV file. **You don't.** The DI is bundled
  at `<openrig-source-root>/assets/audio/input.wav`. Only the *wet
  reference stem* comes from the user.
- Calling `add_block` with a `MODEL_ID` you have not cross-checked
  against `openrig://plugins` in **Step 2.5**. The runtime hard-matches
  IDs; an absent capture either crashes the call or silently selects
  nothing, and the user has no way to know you guessed.
- Silently substituting a missing capture for "the closest installed"
  amp/cab instead of surfacing the (a) import via
  `openrig:openrig-tone3000-fetch` / (b) substitute choice in
  **Step 2.5**. Close-enough is the user's judgment, not yours — and
  documenting it in Step 5 provenance after the fact does not
  retroactively authorize a unilateral decision.
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
| "I built it from research, no need to render+compare" | Research = educated guess. The render+compare loop is the only objective signal. If the user has a stem, run it. |
| "I'll render+compare AFTER saving, that's the natural order" | The save IS part of the loop, not a terminator. Save → render → compare → adjust → save → render → compare → ... until convergence. Reporting "done" after the FIRST save is reporting on a guess. |
| "The previous version of this preset worked without rendering, so I can skip this time" | Whoever told you that lied. **Every preset built without render+compare in this skill's history has been thrown away by the user.** Clocks v1 is the canonical example. No exceptions. |
| "There's no `openrig render` available, I'll skip" | If `openrig render` is genuinely missing from PATH, STOP and tell the user — do not silently skip the gate. The CLI ships with OpenRig; check `which openrig` and `openrig --help` for the `render` subcommand. |
| "The user didn't give me a DI, I can't render" | The user **never** gives you a DI. The canonical DI ships at `<openrig-source-root>/assets/audio/input.wav`. Reading the skill for the path is on you. |
| "I'll research first to know what to look for, then fingerprint" | Wrong order. Research without the fingerprint is theater — you bias toward what "sounds right on paper". Step 0 (fingerprint) comes before Step 1 (research). |
| "The user gave me WAVs but I already know the song, fingerprint is redundant" | The WAVs are the user's reference take, not the song you remember. Era, mix, performance and the user's playing all shift the fingerprint. Run Step 0. |
| "I'll fingerprint just one stem and reuse it for the other role" | Rhythm and lead have different gain stages, different time effects, different EQs. Fingerprint **each** WAV — that's what produces the role-specific presets the skill promises. |
| "`tone3000-fetch` é pesado (issue → PR → qa_audit gate), vou só substituir" | Custo é decisão do usuário, não sua. Surface o trade (a)/(b) na **Step 2.5** e deixa o user escolher. Decidir por ele = decidir que o timbre não importa — mas ele pediu O timbre, não UM timbre. |
| "O capture mais próximo já instalado é 'close enough'" | "Close enough" é o julgamento do usuário, não seu. Pergunte em **Step 2.5** ANTES de substituir. Step 5 provenance documenta substituições autorizadas; não autoriza retroativamente as suas. |
| "`blocks-reference.md` lista esse `MODEL_ID`, então posso chamar `add_block`" | O doc lista o que o projeto SABE carregar. `openrig://plugins` lista o que ESTA rig tem carregado. Os dois divergem — sempre cheque o segundo na **Step 2.5**. |
| "O usuário pediu o preset, fetchar capture é fora de escopo da tone-builder" | Fora de escopo seria dispatch direto; a Step 2.5 só OFERECE o fetch como (a) e delega à `openrig-tone3000-fetch` quando o user aceita. Não oferecer = decidir pelo (b) escondido. |
| "Vou deixar o `add_block` falhar e aí rodo Step 2.5 quando descobrir o erro" | Wrong order. 2.5 é **precondition** pra Step 3, não recovery. O error path polui o log, deixa estado parcial na chain e contorna a pergunta (a)/(b). Leia `openrig://plugins` PRIMEIRO. |
| "Os blocos stock (`compressor_*`, `gate_basic`, `limiter_brickwall`) são built-in, óbvio que estão instalados — checo só os NAM/IR" | A Step 2.5 diz **for every `MODEL_ID`**. Stock pode estar desabilitado em builds custom, renomeado entre versões, ou ausente em forks. O custo do cross-check é uma leitura de resource — não vale a pena economizar. |
| "Eu lembro o path desse param do amp similar (`bass`, `gain`, etc.) — não preciso ler `openrig://plugins/{id}/params`" | Memória mata. Plugins diferentes na mesma família usam paths diferentes (dotted vs flat, prefixos distintos, knobs ausentes). `set_block_parameter_number` com path errado falha em silêncio. Leia o schema dinâmico — uma leitura de resource por `MODEL_ID`. |
| "`blocks-reference.md` lista os params desse amp, então tá schema suficiente" | O doc é a fonte de *recipes* (qual valor escolher dentro do range válido), não de schema. Schema autoritativo é `openrig://plugins/{id}/params` — runtime, não pode estar stale. O doc pode estar drift. |
| "Vou inferir o tool (`_number` vs `_bool`) pelo nome do param" | O `domain` da schema decide, não o nome. Mesmo param chamado `bias` pode ser `FloatRange` (knob) num plugin e `Bool` (switch) noutro. Leia `domain`. |
| "Vou cachear o schema dessa família de amp e reusar pros similares" | Cada `MODEL_ID` tem schema próprio. Cache UM read por MODEL_ID por build — não compartilha entre famílias. Custo é mínimo (uma leitura de resource), benefício é zero erros de path. |
| "O `domain.Enum` me dá `value` E `label`; vou passar o `label` que é mais legível" | Não. O `select_block_parameter_option` recebe o `value`. Passar o `label` falha. |
| "Só uma chain bate com o `instrument` da música, vou direto pra ela sem perguntar" | Step 3.1 sempre renderiza o menu, inclusive quando só uma chain bate. Você PODE sugerir a opção óbvia na mensagem, mas espera o pick do usuário. "Conveniência" = decidir pelo usuário = exatamente a marreta que o user reportou. |
| "Vou usar o nome de chain/preset que aparece nos exemplos da skill" | Nomes em exemplos do texto da skill são ilustrações de FORMATO, não chains ou presets reais. Leia `openrig://project` e use os valores reais que vêm de lá. (Se a sua rig acaso tiver uma chain com o mesmo nome de um exemplo, isso é coincidência — ainda assim você apresenta o menu da Step 3.1 e espera o pick.) |
| "User pré-confirmou a chain nos args / na invocação / no contexto inicial — vou direto" | Pare. Você está prestes a inventar uma mensagem do usuário que não existe. Re-leia EXATAMENTE o que o user mandou neste turno. Se você não consegue colar uma frase verbatim do user dizendo "use a chain X" ou "coloca em <id>" / "põe em <nome>", o user NÃO pré-confirmou. Apresente o menu da Step 3.1 e espere. "Pré-confirmou nos args" sem citação verbatim = fabricação. |
| "O nome do projeto / da invocação do skill já sinaliza qual chain usar" | Não. Nome do projeto, nome da skill, prompt-de-sistema, contexto MCP — nada disso é uma escolha do usuário sobre onde colocar o preset. Apenas mensagens explícitas do user no chat contam. Apresente o menu. |
| "O user já me disse a chain em outra conversa / no chat anterior" | Outra conversa não conta. Cada build da skill começa zerada na Step 3.1; o menu sempre roda no turno atual. Memória cross-session é proibida (mesma regra da schema cross-session). |
| "A rig não tem chain pro instrumento dessa música, vou parar e pedir pro user criar na GUI" | Antigo comportamento. Agora: na Step 3.1, ofereça a opção `(N+1) criar chain nova`, pergunte nome + instrument, e chame `add_chain` quando o user aceitar. Parar e empurrar pra GUI só se o user explicitamente recusar criar pela skill. |
| "Step 0a é bookkeeping, o usuário quer o timbre, não uma estrutura de pastas" | Step 0a É parte de entregar o timbre. Sem `<song-slug>/`, a próxima vez que o user pedir pra re-validar contra a mesma ref, você não consegue (Step 8 fica impossível). Bookkeeping é o que torna "o timbre" auditável, portável, e re-comparável — pular = entregar um chute sem evidência. |
| "Estou num Mac, posso usar `~/.openrig/` direto — é mais curto" | Não. A skill é publicada para todos OS. `~/.openrig/` no Mac é caminho legacy de um project root dev — não é o user-data root. Use `<openrig-user-data-root>` resolvido per OS (macOS → `~/Library/Application Support/OpenRig/`, Linux → `${XDG_CONFIG_HOME:-~/.config}/OpenRig/`, Windows → `%APPDATA%\OpenRig\`). Curto não vale silently quebrar Linux/Windows users. |
| "Vou renderizar pra `/tmp/` que é mais rápido e copio pra `evaluations/` no final" | Hole na sua memória de curto prazo = perder a evidência. `/tmp/` é wipável. "No final" frequentemente não acontece (timeout, erro, interrupção). Escreva DIRETO em `<openrig-evaluations-root>/<song-slug>/renders/<role>-v<N>.wav` desde a primeira iteração — não há atalho que valha o risco de evidência perdida. |
| "Passar o path original do ref pro `compare.py` é o mesmo que passar a cópia em `refs/`" | Não. O path original pode mover, ser deletado, ou estar num drive desmontado quando o user pedir re-eval. A cópia em `refs/<role>.wav` é imutável (sha256-verificada) e é o que TODAS as iterações + Step 8 comparam — todos os scores precisam tracear pra ela. Sempre use o path persistente. |
| "Symlink em vez de `cp` pro `refs/` economiza disco" | Economiza disco, quebra portabilidade. `tar czf backup.tgz <openrig-evaluations-root>/` precisa funcionar e produzir um arquivo auto-contido. Symlink quebra na hora do `tar` (vira link relativo) ou na hora do extract em outra máquina. Sempre `cp`. |
| "Vou updatar `eval.md` só no final, com todas as iterações de uma vez" | Não. As linhas interim são a evolução do score — sem elas você não consegue mostrar pro user por que a v4 ganhou da v2. Append linha por iteração, no final do Step 5 de cada loop. |
| "Já existe `<openrig-evaluations-root>/<song-slug>/` de um build anterior — vou `rm -rf` pra começar limpo" | Não. Isso apaga a auditoria do user. Leia `eval.md`, continue a numeração de iteração depois do último `<role>-v<N>`, e mantenha os YAMLs antigos como histórico. Só apague se o user explicitamente pedir. |
| "Os placeholders `<Song>` `<Artist>` `<chain id>` no template do `eval.md` são literais — escrevo como estão" | Não. Placeholders na SKILL.md são marcadores de slot — você substitui pelos valores reais do build (título da música real, artista real, chain id real lido de `openrig://project`). Se o `eval.md` final na pasta do user contém literalmente `<Song>` ou `<Artist>`, você não fez o build, você ecoou o template. |

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
4. Print the file path and tell the user: "Pra ouvir, abre OpenRig,
   seleciona a chain `<chain>`, e usa **Load Preset** apontando pra
   esse arquivo. Não tocou no rig em memória."
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

- ❌ **Calling `add_chain` WITHOUT the user picking "criar chain
  nova" in Step 3.1 AND answering both name + instrument prompts.**
  `add_chain` is only legitimate as the explicit Step 3.1 sub-flow
  result — never to "make a slot for the tone" (that's
  `apply_rig_nav Preset(-1)`), never to "re-shape" an existing chain,
  never silently when the user said "preset" generically. Chain ≠
  slot: a chain is a top-level rig group with its own I/O; a slot is
  one preset position inside a chain's bank.
- ❌ **Auto-picking a chain in Step 3.1 because its `instrument`
  matches the song (or because it's the only candidate, or because
  it's the only chain in the project).** Step 3.1 always renders the
  full menu and waits for the user's pick — that's the entire point
  of the step. Even "óbvia uma só, vou direto" is the marreta
  behaviour the step exists to block.
- ❌ **Substituting the full numbered menu in Step 3.1 with a
  narrowed "use `<chain>`? (y/n)" ask.** Y/n hides the other chains
  AND hides the "criar chain nova" option. Render the menu, every
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
- ❌ Silently switching from MCP to file (or vice versa) without the
  user's explicit Step −1 answer.
- ❌ Stopping at "saved" when a reference stem was provided — run the
  render+compare loop before declaring done.
