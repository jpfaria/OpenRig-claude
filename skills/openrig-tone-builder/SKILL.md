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
  workflow** at the bottom. Do NOT call any MCP tool.
* If the user does not answer, default to **(a) MCP** but only after the
  precondition check passes; if the MCP server is offline, fall back to
  asking again rather than silently writing a file.

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

## Iron rule -- the catalog source of truth

**The ONLY catalog source you may consult for `MODEL_ID`s and parameters is [`docs/blocks-reference.md`](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md) in the `jpfaria/OpenRig-plugins` repo.** Specifically the **Model ID Quick Reference** section near the top of that file, and the per-section catalogs further down. WebFetch the URL if you don't have the repo checked out locally.

You MUST NOT:

- Open or grep any file under `crates/block-*/src/` to discover model IDs or parameters. Ever. Not for "double-checking", not for "the doc might be stale", not for "just one quick lookup".
- Read existing presets to copy their `MODEL_ID` strings or parameter shapes. They drift from the registry; the doc does not.
- Guess or invent model IDs based on what "sounds right". Every ID is a string the runtime hard-matches.

If a model you need is not in [blocks-reference.md](https://github.com/jpfaria/OpenRig-plugins/blob/main/docs/blocks-reference.md), that is a doc bug -- stop, tell the user, suggest opening an issue against the doc. Do not work around it by reading source.

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

### 0. Check for a pre-existing preset for this song

The worst-case failure mode for this skill is silently overwriting a
preset the user spent time tuning. Run this check **before any other
MCP call**.

1. Decide which chain the preset belongs to (electric guitar / bass /
   acoustic). If multiple chains in the project match the instrument
   and the user did not name one in the prompt, ask once which chain
   to write into; never pick by yourself when more than one would fit.

2. Read the chain's bank:

   ```
   ReadMcpResourceTool {
     server: "plugin_openrig_openrig",
     uri: "openrig://chains/<chain-id>/presets"
   }
   ```

   The response is JSON: `{ active_preset, slots: [{ index, name, key }, ...] }`.
   The slot's display name lives in `name` (set via `rename_rig_preset`);
   the bank's stable identifier lives in `key` (auto-generated, ignore
   for matching).

3. Construct the canonical preset name for this build:
   `"<Song> — <Artist> (<role>)"` (em dash, single space; `<role>` is
   `rhythm` / `lead` / `solo` / `clean` / `intro`, etc.). Examples:
   `"Enter Sandman — Metallica (rhythm)"`, `"Clocks — Coldplay (lead)"`.

4. Compare case-insensitively against every `name` in `slots[]`. A
   match means the user already built (or started) this preset.

5. **If there is a match**, do not touch the rig. Ask the user via
   `AskUserQuestion` which of the following to do:

   - **Overwrite** that slot (the skill will `apply_rig_nav` to
     activate it, then drop and re-add its FX blocks — destructive to
     the existing tone in that slot only).
   - **Save under a new name** (suggest a suffixed variant such as
     `"<Song> — <Artist> (<role>, v2)"` or
     `"<Song> — <Artist> (<role>, takeN)"`); a brand-new slot will be
     added.
   - **Cancel** and stop the skill (the existing preset stays exactly
     as it is).

   Wait for the answer. Do not infer from silence.

6. **If there is no match**, you will add a new slot in Step 3. Carry
   the canonical name forward for Steps 7 (`rename_rig_preset`) and 8
   (`save_chain_preset`).

7. Document in your provenance reply (Step 5) whether you created a
   new slot or overwrote an existing one — the user reading the diff
   later needs to know.

### 1. Research the signal chain

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

**Fingerprint caveat (`openrig-tone-analyzer` data):**

- **Isolated guitar stem** (rhythm/lead WAV) — the centroid, rolloff,
  band energy, gain_character and time_fx fields describe the **guitar
  itself**. Trust them, they map directly to your EQ / amp choice.
- **Full mix** — the centroid is dominated by drums, bass and piano
  (mid-low energy). Treat the mix's centroid as an **upper bound** on
  what the guitar contributes; do NOT EQ-darken your preset just
  because the mix's centroid is low. Look at the spectrogram of the
  guitar's identifiable parts (introdução, solo) instead. When in
  doubt, ask the user for an isolated stem before committing.

If `openrig-tone-analyzer` produced a fingerprint, look up `source.kind`
or the WAV title — most isolated stems are labelled `rhythm`, `lead`,
`solo`, etc. in the filename.

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
4. **Note uncertainty** (substitutions, missing captures).
5. **Tunings** mentioned as a playing hint, optionally in the preset name.

### 6. Render and A/B compare (validation loop)

If the user provided a reference WAV (isolated guitar stem), close the
feedback loop instead of stopping at "saved":

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

## Workflow (file-only path)

If the user picked the file-only path in Step −1:

1. Do **steps 1, 2** of the MCP workflow (research + map gear). Skip
   the MCP precondition.
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
