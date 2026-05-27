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

**A chain is a slot/group in the rig** (e.g. "Electric Guitar",
"Acoustic", "Bass"). Owns the I/O wiring and an instrument tag. **The
user creates chains.** This skill never calls `add_chain`.

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
> arquivo YAML** (escrevo em `~/.openrig/presets/<name>.yaml`, sem
> tocar no rig)?"

* If **(a) MCP** — confirm the MCP tools are wired (precondition below)
  and follow the **MCP workflow**.
* If **(b) file** — skip the MCP precondition and follow the **File-only
  workflow** at the bottom. On this path the **ONLY MCP calls allowed
  are reads of the resources `openrig://plugins` and `openrig://project`**
  (used by **Step 1b** for an installedness check without mutating the
  rig). **Every other MCP call is forbidden** — that includes mutations
  (`add_block`, `save_chain_preset`, `apply_rig_nav`,
  `set_block_parameter_*`, etc.) AND non-mutating tools (e.g.
  `reload_plugin_catalog`, `register_recent_project`, `start_midi_learn`,
  `set_language`, `set_compact_view_enabled`). Allowlist, not blocklist.
* If the user does not answer, default to **(a) MCP** but only after the
  precondition check passes; if the MCP server is offline, fall back to
  asking again rather than silently writing a file.

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

## Iron rule -- two sources of truth, do not confuse them

Catalog work has TWO orthogonal questions, and each has exactly ONE authoritative source:

1. **"Does this `MODEL_ID` exist and what are its parameter paths / ranges / NAM-vs-native patterns?"** → [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) in the `jpfaria/OpenRig-plugins` repo. Use the **Model ID Quick Reference** near the top and the per-section catalogs further down. WebFetch the URL if the repo isn't checked out locally. This doc is the **schema** source.

2. **"Is this `MODEL_ID` actually installed on the user's rig RIGHT NOW?"** → the MCP resource `openrig://plugins` (returns every plugin loaded by THIS instance, with `id`, `display_name`, `brand`, `block_type`, `backend`). A model present in `blocks-reference.md` but absent from `openrig://plugins` will fail `add_block` at runtime. You MUST consult this before every `add_block` call on the MCP path — see **Step 2.5**.

You MUST NOT:

- Open or grep any file under `crates/block-*/src/` to discover model IDs or parameters. Ever. Not for "double-checking", not for "the doc might be stale", not for "just one quick lookup".
- Read existing presets to copy their `MODEL_ID` strings or parameter shapes. They drift from the registry; the doc does not.
- Guess or invent model IDs based on what "sounds right". Every ID is a string the runtime hard-matches.
- Assume "doc lists it → it's installed". The two sources diverge constantly (NAM/IR packs are user-installed; the doc lags the rig in either direction). Always cross-check.

If a model you need is not in [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md), that is a **doc bug** -- stop, tell the user, suggest opening an issue against the doc. Do not work around it by reading source.

If a model IS in [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) but **not in `openrig://plugins`**, that is a **missing-capture case** — go to **Step 2.5**. Do NOT silently substitute.

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

**Fallback ladder when `WebFetch` fails or returns empty (common on JS-heavy sources like tonedb.co):** Playwright MCP → WebSearch → ask the user to paste page text. Playwright is a research aid; `MODEL_ID`s and parameter paths still come exclusively from [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md).

### 2. Map gear to OpenRig models — and respect stem vs mix evidence

Open [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) and do the lookup yourself for **every** piece of gear in the chain. Always prefer NAM amps over Native amps when the song has a real amp model.

**The Step 0 fingerprint is your primary input here.** Walk each
field against the `blocks-reference.md` catalog:

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

5. Do not proceed to Step 3 until every `MODEL_ID` in the plan is either present in `openrig://plugins` OR explicitly substituted with the user's OK in (3b).

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

1. **Read `openrig://project` and pick the chain.** List every chain
   with its `instrument` field and current `blocks`. Pick the chain
   whose `instrument` matches the song (`electric_guitar`,
   `acoustic_guitar`, `bass_guitar`). When several match, prefer the
   one **without** acoustic-specific blocks (body IR) for an electric
   song, **with** them for an acoustic song. Still ambiguous → ask
   the user once. **If no chain matches, STOP** — the user adds the
   chain in the GUI; you do NOT call `add_chain`.

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

5. **Set parameters** with the typed param tools on each block id:
   - numeric → `set_block_parameter_number { chain, block, path, value }`
   - boolean → `set_block_parameter_bool { chain, block, path, value }`
   - text → `set_block_parameter_text { chain, block, path, value }`
   - enum/option → `select_block_parameter_option { chain, block, path, value }`

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
1.  dynamics/ compressor_studio_clean    enabled:true   params: parallel mix=20-40 (clean rhythm/lead)
2.  filter  / native_guitar_eq           enabled:true   params: low/low_mid/high_mid/high (start flat, tilt by ±2 dB max)
3.  dynamics/ gate_basic                  enabled:true   params: attack_ms=0.1, release_ms=<60-120>, threshold=<25-65>
4.  gain    / <gain_model_id>             enabled:<bool> params: per blocks-reference.md (only if the song uses a boost/drive)
5.  amp     / <amp_model_id>              enabled:true   params: one of the NAM amp patterns in blocks-reference.md
6.  filter  / eq_eight_band_parametric    enabled:true   params: mimic real bass/mid/treble/presence (see Step 4)
7.  delay   / analog_warm  (or other)     enabled:<bool> params: time_ms=<from BPM math>, feedback=<10-40>, mix=<5-35>
8.  reverb  / room (rhythm) | hall (lead) enabled:true   params: room_size + damping + mix per analyzer RT60
9.  dynamics/ limiter_brickwall           enabled:true   params: defaults (threshold=-1.0, ceiling=-0.1, release_ms=100)
10. gain    / volume                      enabled:true   params: volume=<70-90>, mute=false
```

**Tuner and spectrum analyzer are NOT in this plan.** `tuner_chromatic`
and `spectrum_analyzer` are NOT valid `add_block` kinds — the runtime
rejects them with "unknown utility model". They are **rig-wide
utilities** controlled by separate Commands (`set_tuner_enabled`,
`set_spectrum_enabled`) and live outside the per-chain block
processor. The preset has no business toggling them.

Adjust per song style:

- **Clean / acoustic**: drop the boost (skip block 4), drop the gate, switch to a clean amp, add a body IR for acoustic.
- **Funk / clean rhythm**: keep `compressor_studio_clean` paralleled with `mix: 30-50`. Lower amp gain.
- **Lead solo**: bump `volume` to 85-90, raise delay mix to 12-25%, switch reverb to `hall`, larger room_size, higher mix.
- **Delay-driven (Edge/Buckland/Mayer rhythm)**: time = dotted-eighth at the song BPM (`60000 / bpm * 1.5 / 2`), feedback 25-35%, mix 30-40% so the delay pattern is clearly audible.
- **Doom / drone**: drop boost, raise reverb mix to 25%+, add `tape_vintage` delay.

### 4. Knob translation rule

NAM amp captures have **knobs baked into the capture**. Most NAM amps expose only structural switches (`character` / `cabinet` + `gain`) -- not continuous bass/mid/treble/master controls. Approximate the EQ shape with the parametric EQ block **after** the amp (block 6).

For Native preamps (`american_clean`, `brit_crunch`, `modern_high_gain`) you DO get all knobs -- set numeric values directly on the amp block instead of via parametric EQ.

### 5. Provenance comment in the chat reply

After `save_chain_preset` succeeds, summarize:

1. **Chain + slot + preset name**: which chain, which slot index, and
   the preset name (e.g. `"Clocks — Coldplay (rhythm)" added to slot 5
   of chain "gUItARRA - SETLIST"`).
2. **Mapping table**: real gear → OpenRig model. Mark fallbacks explicitly.
3. **Cite sources** you actually fetched.
4. **Note uncertainty** explicitly. For any substitution that came out
   of **Step 2.5**, name BOTH the wanted `MODEL_ID` and the installed
   substitute (e.g. `nam_diezel_vh4` → `nam_diezel_herbert`, per user
   OK in Step 2.5). Silent substitutions are forbidden — see Red Flags.
5. **Tunings** mentioned as a playing hint, optionally in the preset name.

### 6. Render and A/B compare (MANDATORY validation loop — runs BEFORE you report "done")

> ⛔ **This is the hard gate from the top of the file.** If the user
> provided a reference WAV — or if you can reasonably infer they expect
> the preset to match a real recording — this loop is NOT optional and
> NOT post-hoc. Without it, your preset is a research-grade guess and
> the user has no way to tell. Run it BEFORE declaring done; iterate
> until convergence; only then report.

1. Render the **canonical bundled DI** through the just-saved preset
   via `openrig-render` (headless DSP renderer): `openrig render
   --preset "<Song> — <Artist> (<role>)" --input
   <openrig-source-root>/assets/audio/input.wav --output
   /tmp/openrig-render/<song>-<role>.wav`. The DI ships with OpenRig
   (the NAM-standardized reamp input — covers the dynamic range and
   frequency content needed to characterize a chain). You never ask
   the user for a DI; only the reference *wet* stem comes from them.
2. Compare the rendered output against the reference stem with
   `openrig-tone-analyzer` in compare mode: `.venv/bin/python
   scripts/compare.py <reference-stem.wav> <rendered.wav>`. Reads as
   "how close is my preset to the source on the same playing".
3. Read the produced `diff.json`. The top 2-3 `recommendations` are
   concrete, priority-sorted instructions (e.g. "raise EQ band 4 gain
   by 3 dB", "delay time wrong by 80 ms", "needs more high-shelf").
4. **Apply ONE recommendation at a time** with the relevant
   `set_block_parameter_*` call, re-render, re-compare. Iterate until
   `diff.converged` is true OR `match_score` plateaus.

Without the render→compare loop, you are building from research +
analyzer fingerprint alone — that's an **educated guess**, not a
measured match. Flag this in the chat reply so the user knows.

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
- [ ] Every `model:` referenced appears in [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) Quick Reference.
- [ ] Every `MODEL_ID` actually passed to `add_block` is present in
      `openrig://plugins` — verified by reading the resource in
      **Step 2.5**.
- [ ] Any missing captures were resolved through **Step 2.5** with the
      user's explicit (a) import via `openrig:openrig-tone3000-fetch` /
      (b) substitute choice, and the resulting substitution (if any) is
      recorded in the Step 5 provenance.
- [ ] You did NOT call `add_chain` (this skill never does).
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
- Opening any research URL, calling any MCP tool, or planning the FX
  layout **before** invoking `openrig:openrig-tone-analyzer` on every
  reference WAV the user provided. Step 0 comes first. No exceptions.

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

## Workflow (file-only path)

If the user picked the file-only path in Step −1:

1. Do **steps 1, 2** of the MCP workflow (research + map gear). Skip
   the MCP precondition.
1b. **Installedness on the file-only path.** If the OpenRig MCP server
   happens to be reachable in this session anyway (rig running with
   `--mcp`, just not the persistence path the user picked), run
   **Step 2.5** to flag missing captures — the user can still opt to
   import via `openrig:openrig-tone3000-fetch` BEFORE you write the
   YAML, so the eventual `Load Preset` doesn't fail to resolve a
   capture. If MCP is offline, you **cannot verify installedness from
   here** — list **every** `MODEL_ID` your plan uses (not only the
   exotic NAM/IR ones — also `compressor_studio_clean`, `gate_basic`,
   `eq_eight_band_parametric`, `limiter_brickwall`, etc.) in your chat
   reply, label the list explicitly as **"unverified — your rig may
   not have all of these"**, and recommend the user run
   `openrig:openrig-tone3000-fetch` against any captures they don't
   have locally before they load the YAML in OpenRig. Do NOT silently
   trust the plan; the user is your installedness oracle when MCP
   is offline.
2. Determine the YAML output path:
   `~/.openrig/presets/<Song> — <Artist> (<role>).yaml` (the OS path
   varies — macOS uses `~/Library/Application Support/OpenRig/presets`
   when that's configured; ask the user once if unsure).
3. Write the YAML in the schema OpenRig's `LoadChainPreset` expects.
   The minimum is the `blocks:` list with one entry per FX block and
   the parameters resolved from `blocks-reference.md`. The chain's I/O
   blocks are NOT included (the preset only carries FX).
4. Print the file path and tell the user: "Pra ouvir, abre OpenRig,
   seleciona a chain `<chain>`, e usa **Load Preset** apontando pra
   esse arquivo. Não tocou no rig em memória."
5. Skip the render+compare loop unless the user explicitly opts in
   later (would require switching to the MCP path for the render).

## Anti-patterns (all paths)

- ❌ **Calling `add_chain` to make a new slot for the tone.** Chain ≠
  slot. The slot is created by `apply_rig_nav Preset(-1)`.
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
