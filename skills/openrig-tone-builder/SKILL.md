---
name: openrig-tone-builder
description: "Use when the user asks for a tone, timbre, or preset for a specific song or artist (\"timbre da Duality\", \"preset do Slipknot\", \"tom da [música]\", \"recreate the [song] sound\", \"build a [artist] preset\"). Researches the original signal chain in natural language, lets a deterministic tool resolve it to catalog gear, and saves it as a NAMED PRESET in the chain's bank — adding a NEW slot via `apply_rig_nav Preset(-1)`, never overwriting existing presets. ALWAYS asks the user once up front whether to commit via the live MCP rig or as a YAML file only."
---

# OpenRig Tone Builder

## ⛔ THE PROCESS — feed RESEARCH, never type an id

The whole job: you make the **judgment calls** (research the artist's real rig
in natural language, cited), and a deterministic tool turns that into
catalog-backed model ids. **You NEVER type a `nam_*` / `ir_*` model id or a param
path from memory** — `resolve_gear` finds them, the gate rejects what it can't
back. You do ONLY this:

1. **Fingerprint the stems** the user sent (Step 0). Confirm they are the
   **isolated instrument being built** (the guitar — or acoustic). A separated
   stem can be the WRONG instrument: a piano-driven song (e.g. Clocks) separated
   badly yields a piano stem; matching a guitar to it is hopeless. If unsure, ask.
2. **Research the artist's actual rig for THIS song** (Step 1) — every element:
   comp, gate, drive(s), amp/preamp, cab (if preamp), modulation, delay, reverb,
   body. **`tonedb.co` is source #1 — hit it FIRST**, then the rest of the ladder.
   Cite sources. Never assert gear from memory (the gear HARD RULE).
3. **Write the research JSON** (Step 3) — gear NAMES + brands + sources (Rule A)
   and FX params + provenance (Rule B). This is your ONLY hand-authored input.
   You do NOT write a single model id or param path.
4. **Run `build_preset.py --research`** (Step 4). One command: it `resolve_gear`s
   the names into catalog ids (PINNING the exact/signature capture), runs the
   validate+lint GATE, searches the gear, trims the EQ, sets headroom, and emits
   the preset + report. If it ABORTS on `unresolved`, you fix the RESEARCH — never
   guess an id. You relay the report and persist (Step 5–6).

**Forbidden shortcuts — each has burned a real build:**
- Skipping `tonedb.co`, jumping to a generic web search or to memory.
- **Typing a model id or param path yourself** to "save a step". The gate exists
  precisely so you never do this — fix the research name, never hand-author the id.
- **Asking the user to diagnose by ear** ("what sounds wrong / too dark?"). You
  have no ears AND you do not outsource the diagnosis. The engine drives the
  number; the user's ear enters only when THEY volunteer "it's bad", and even then
  you act on the specific complaint — you never fish for it.
- Treating a low **self-floor** as a tone failure: a sparse/separated stem has a
  low self-floor, the proximity caps there, and "at the floor" is the honest
  ceiling — **report that plainly** (e.g. "the stem's own ceiling is 89%; the
  preset is at it — a longer/cleaner guitar stem is what would move the number").

## ⛔ THE FORM — research → `--research` → relay → persist

Build EXACTLY this way, every tone, the same. The deterministic loop
(resolve+pin → gate → gear search → EQ trim → headroom) lives in
**`build_preset.py`** (the `openrig-tone-analyzer` engine). Your job is to feed it
a correct **research JSON** and relay its **report** — never to re-narrate the
loop by hand, never to type an id it should resolve.

1. **Fingerprint the reference** → the honest `match_target` (analyzer schema ≥3):
   `ltas_norm_db` + `reliable_mask` + `reliable_range_hz` + `top_octave_dead` +
   `self_floor_pct`. **The fingerprint is the validator — not the user's ear.** The
   user's ear only enters when THEY volunteer a complaint; never fish for it.
   (`build_preset` re-measures the reference itself; you fingerprint up front to
   read the per-song floor and shape the EQ direction.)
2. **Research the gear EXHAUSTIVELY** (cited, `tonedb.co` first, THEN multiple
   sources — interviews, rig rundowns, gear DBs, forums). Discover the artist's
   FULL signal chain for THIS song — guitar + pickups, and **EVERY element**:
   compressor, noise gate, boost/OD/distortion/fuzz, wah, modulation, delay,
   reverb, amp(s), cab(s), mic, studio technique. A shallow "amp + done" search is
   exactly how pedals get missed and the tone comes out wrong. Never from memory.
   ⛔ **Reproduce the COMPLETE researched rig — omit NO element.** Dropping ANY —
   because it "feels minor", "wasn't a stomp box", or "the number didn't ask for it"
   — is the error that gets the whole batch thrown away. Three traps that make you omit
   (detailed in Workflow Step 1):
   - **Gain:** "no stomp box on the record" is NOT "amp-only" — the saturation was
     often a CRANKED / MODDED amp (Green Day's Dookie-Mod Plexi) while our captures
     are STOCK. Name the amp's mod/cranked character so the tool regulates the pinned
     capture's **gain-axis**, and/or research a **drive pedal** (players stack 2–3).
   - **Time/feel:** comp/mod/delay/reverb the research lists ARE the tone even though
     they barely move the LTAS number (heard, not measured). Put each in `fx[]`; the
     engine keeps every FIXED block verbatim and never tells you one is missing. A
     finished rig with **zero reverb AND zero delay is a RED FLAG** — re-research the
     ambience or cite a source that the part is genuinely dry.
   - **Noise:** a high-gain NAM capture is noisy — add an **enabled** `dynamics` gate
     when research cites one OR the capture's measured noise floor is high (threshold
     `provenance: unverified` if undocumented); don't blanket-gate a clean part.
3. **Rule A — research the gear by NAME; the tool PINS it; the number REGULATES,
   never PICKS the amp.** In the research JSON you name each core element — amp (+
   brand + any artist `signature`), drive(s), cab (only if the amp is a preamp).
   `resolve_gear` then decides per slot, on this ladder:
   - **(1) The EXACT researched capture / signature exists → it PINS that one
     model.** The proximity number is too weak to tell amps apart — on a real John
     Mayer "Gravity" build it ranked a generic `nam_fender_deluxe_reverb` at 67.81%
     ABOVE the artist's actual `nam_dumble_ods_john_mayer` at 66.10% (a 1.7% noise
     gap), with nothing clearing the floor. A 1–2% spread between amp models is
     noise; it must NEVER swap the artist's amp. The pinned amp's **gain-axis IS
     timbre**, so the engine regulates it (gain-axis variants of that ONE model) —
     but it NEVER lists a different amp model. **Cite the artist + signature in the
     research so the catalog grep finds it** (e.g. "Dumble, John Mayer").
   - **(2) No exact capture → it emits `candidates:`** (top ≤3 documented stand-ins
     — same brand/family/circuit — the number picks the closest, all guesses
     anyway). For a cranked/modded amp with no modded capture, the pinned stock
     capture's gain-axis covers the gain, and/or a mod-matched drive.
   - **Same PIN logic for a preamp or a cab** when the exact capture exists.
   **The engine preferring a different amp than the researched one is NOT permission
   to ship it.** When the exact capture exists it PINS; if the pinned chain cannot
   reach the floor, that is a real signal (degraded reference, wrong drive/EQ, high
   floor) you SURFACE to the user. You do NOT swap the artist's amp to chase 1–2% of
   a noisy number. **If `resolve_gear` can't back a name, it ABORTS as `unresolved`
   — you fix the RESEARCH name, never feed it an id.**
4. **Rule B — every FX param is sourced, derivable, or `unverified`.** In the
   research JSON's `fx[].params`+`provenance`, follow the source: **documented** (rig
   rundown / interview) → use the values, `provenance: sourced`; **derivable** (delay
   time = tempo math from the song BPM) → compute, `provenance: derived`; **not
   documented** (a compressor's exact knobs) → a sensible default, `provenance:
   unverified`. An absent marker defaults to `unverified`. The report surfaces every
   FX block under `param_provenance.blocks` plus an explicit
   `param_provenance.unverified` list — you **relay that list** (Step 5), never
   presenting a default as sourced. Params the proximity number cannot validate
   (comp/mod/delay/reverb feel) are set from source/default and **never** optimized
   by the number.
5. **"Regulate" is MULTI-BLOCK, not the EQ alone.** Regulating toward the reference
   moves the **timbre-affecting** controls together: the **pinned amp's gain-axis**,
   the **drive** (selection/gain-axis), AND the **EQ trim**. A run where only the EQ
   moved and every other block sat at its default is WRONG. The **feel/time blocks**
   (comp, gate, delay, reverb, mod) carry their researched params and are NEVER left
   at the engine/plugin DEFAULT and NEVER optimized by the number (heard, not
   measured). The amp/drive gain-axis IS timbre — so the number regulates THOSE.
6. **AMP vs PREAMP decides the cab — by catalog TYPE, never by measurement.** A
   `type: amp` capture is a FULL amp — a **combo** (speaker baked in) OR a head+cab
   mic'd — so it **already has its speaker and NEVER takes a cab**. Only a
   `type: preamp` capture (preamp, no power amp/speaker) needs a cab. The engine
   decides **by the catalog `type`**: for a `preamp` core it auto-inserts a
   **`type: cab` plugin** (supplied via `--cab-model`, whose manifest `output_gain_db`
   is applied so the level is right) — ONLY when there is no researched cab already.
   For a `type: amp` or `type: body` (acoustic) core it inserts NOTHING. You do NOT
   detect this by hand; the `type` is authoritative. So in the research JSON, set
   `cab` ONLY when the artist used a preamp (or an explicit separate cab) — leave it
   `null` for a full amp. Never research both a full amp and a duplicate cab.
7. **Run `build_preset.py --research`** (Step 4). It resolves+pins, gates (validate
   + lint), searches the gear (amp × drive(s); a cab auto-inserts only for a `preamp`
   core), trims the EQ (**±6 dB cap**; dead-top/out-of-range bands held at 0), and sets
   headroom on the EQ `output_db` so the DI peak lands **as hot as possible without
   clipping** (≈ −1 dBFS, never 0 — there is no limiter). It emits the preset YAML + a
   report JSON. **Below the per-song floor is not done** — read `within`.
   ⛔ **The chain ends at the EQ. NO brickwall limiter, NO volume block** — the gate
   HARD-fails either (`limiter_brickwall` / `type: volume`); never put them in `fx[]`.
8. **React to the run:**
   - **ABORTS on `unresolved`** → a gear name was wrong, too vague, or genuinely not in
     the catalog. Tighten the name (add the artist signature), or route a real-but-missing
     capture through `tone3000-fetch` (Step 4a). **Never guess an id to get past it.**
   - **`within` false (plateau below floor)** → for a **pinned amp** the amp does NOT
     move; regulate gain-axis / drive / EQ, and if it still can't reach the floor, SURFACE
     that plainly. For **stand-in candidates** (no exact capture) the RESEARCH is too thin
     — widen the researched gear and re-run.
9. **ONE tone at a time.** `build_preset.py` builds ONE tone per run by design. Never
   batch-rebuild with an auto loop — that ships every preset broken at once (it gutted 38
   presets). Finalize one, write the preset file, relay the report, let the user validate.

> **Escape path (rare):** for genuinely OFF-catalog gear (a private IR `.wav`, a
> block the catalog can't represent), `build_preset.py --base-chain <yaml>` takes a
> hand-authored flat `blocks:` list instead of `--research`. This is the
> lower-level escape, not the default — the `--research` pipeline is the FORM.

## ⛔ The degraded-reference trap — when the number LIES

A separated stem from a **mix where the instrument is buried** (e.g. the guitar in
a piano-driven song) is not a guitar spectrum — it is a low-mid fragment with the
top octave stripped by the separator. The engine already **protects you**: it caps
the EQ trim at ±6 dB and **holds the dead-top / out-of-range bands at 0** (the
`fingerprint_match_target` excludes those bands from `proximity_pct`). So the old
"+10…+15 dB low-mid pile" can't happen through the engine. What CAN still mislead is
**which gear scores best**. The reference is **degraded** when any holds:

- **top octave** (~10 kHz) more than ~30 dB below the ~400 Hz body, AND/OR
- **85 % of the energy rolled off below ~1 kHz**, AND/OR
- a **low `self_floor_pct`** (< ~90 %).

Measured on the real Clocks guitar (Moisés stem: 10 k at −101 dB, 85 % of energy
below 630 Hz): the darkening build measured **88 %** but its high end sat **−18 dB**
below the body (boxy); the gear-driven bright build measured only **64 %** but had a
flat, guitar-like tilt — the **lower** number was the **right** tone.

**Rule:** on a degraded reference, build the **researched gear** (the amp IS the
timbre), let the engine tune within its ±6 cap, and hand it to the **user's ear** —
this is the one case where the number is actively misleading and only the user
playing can judge. Report it plainly ("the stem is a top-dead, low-mid fragment —
matching it would darken the tone; I built the researched rig bright instead, your
ear decides"). A cleaner stem (or the full-mix guitar) lets the number lead again.

## Chain vs preset vs slot — read this before anything else

**A chain is a top-level group in the rig** (e.g. "Electric Guitar", "Acoustic",
"Bass"). Owns the I/O wiring and an instrument tag. **Where this preset lives —
which chain, or a brand-new one — is always the user's call** (Step 3.1). This skill
may call `add_chain` when the user explicitly opts in; it never picks or creates a
chain on its own.

**A chain has a BANK of preset slots.** Each slot holds one named preset (the FX
layout for one tone), referenced by index; the display name lives in
`RigPreset.name`. The user switches slots at runtime to swap tones live.

**A preset is the FX layout for ONE tone**, stored in one slot of a chain's bank.

> "Look for the preset, not the chain." Your job is to write a **preset**. The
> chain is just the rig slot it lives in.

This skill **only ever creates or updates presets**, and **adds a NEW slot** to the
chain's bank — it does **NOT** edit the chain's currently-loaded blocks (that would
destroy the user's active preset). See Step 6. **Before anything else, check whether
a preset for this song already exists** — overwriting tone work is the worst-case
failure (Step 0 / Step 6).

## ⛔ VALIDATION GATE — the engine generates a FAITHFUL match number

The job: **user gives a reference recording → you produce a preset whose TIMBRE is
as faithful as possible.** You have no ears, so the only thing you optimise toward is
a **number** — and `build_preset.py` computes and drives it. The documented failure
("I send a WAV of the song and the tone is nothing like it") happens when that number
is **meaningless**, for two fixable reasons:

> **1. Compare GUITAR against GUITAR.** A timbre number is only faithful if both
> sides are the isolated guitar. A **full mix** is dominated by everything that is
> NOT the guitar. → **Isolate the guitar from the reference FIRST** (source
> separation — Step 0). Only ever pass the isolated-guitar reference (`--ref`). If
> you cannot isolate it, say so and ask for a stem — do **not** validate against a mix.

> **2. The number measures TIMBRE, not the performance.** The reference is almost
> never the bundled DI re-amped — different notes, timing, level. A raw `match_score`
> (folding in onsets, silence, loudness) can't converge. The engine's number is the
> **energy-weighted spectral proximity over the reliable range** (the level-normalised
> LTAS distance over signal-bearing windows): it ignores which notes were played and
> how loud, so it isolates **tonal balance** — and it converges.

> ⛔ **You (the agent) cannot hear. Your own "ear" is NEVER the basis.** You cannot
> decide a render "sounds muffled", "dark", or "the delay is too long" — asserting any
> such verdict is fabrication (same as the no-suppositions HARD RULE in Step 0). The
> engine optimises the faithful NUMBER. **The ONLY ear that counts is the USER'S, and
> only when they explicitly say it's bad** ("tá ruim", "muffled", "too dark"). Until
> then you relay the number. When the user *does* say it's bad, that specific complaint
> overrides the number and you act on it.

**Acceptance bar: the report's `within` is true** (`proximity_pct ≥ self_floor_pct − 3`,
NOT a fixed 95). `proximity_pct` is the energy-weighted, reliable-range timbre distance
of the winning chain; `self_floor_pct` is the reference's own self-similarity, the
per-song physical ceiling (~79–96 %) you cannot beat. A fixed 95 is wrong both ways: it
chases an impossible number on floor-85 material and lets a boomy preset reading 95 pass.
The render+compare is MANDATORY whenever a reference exists (saving without it is the
Clocks v1 blind-guess failure) — `build_preset` IS that gate. **`match_score` is NEVER
the bar.** If `proximity_pct` plateaus below the floor, widen the researched gear and
re-run — but the **pinned amp does not move** (THE FORM step 8); only if you genuinely
cannot reach the floor do you STOP and report both numbers. The user's ear can override
at any point; their *silence* never lowers the bar.

If the user explicitly says they have **no reference at all**, declare it **out loud
in the chat** before saving — "no reference provided, this preset is a research-only
guess; I cannot validate it." Silent skipping = failure. The DI is the bundled
`<openrig-di>` (Step 0b); you never ask the user for a DI, only the wet reference.

### Level is NOT timbre — the engine owns headroom, never the ref's RMS

The preset's **output level is set by the engine's headroom pass** (the EQ
`output_db`, targeting the DI peak ≈ −1 dBFS, hot but never clipping) — **never**
matched to the reference's RMS. A real reference is often quiet (soft playing, gaps,
mastering headroom); matching its RMS ships a broken-feeling preset. The report's
`peak_db` is the measured DI peak you relay. Any `match_score`/`diff.json`
recommendation about RMS or level is **ignored** for tone purposes — the headroom pass
owns level, the proximity number owns timbre, and neither touches the other.

## Step −1 — Ask the user: MCP live or YAML file only?

Before touching anything, ask **once** which persistence path. This choice is about
**where the emitted preset is stored** (live bank vs YAML file) — **not** whether the
build runs. `build_preset.py` runs **offline on both paths**; it never requires
`--mcp`. Both are valid:

> "For this preset, I'll go: **(a) via MCP on the live rig** (I build it offline, then
> import the emitted preset into a new slot in the bank, audible immediately — requires
> OpenRig running with `--mcp`), or **(b) YAML file only** (the emitted preset YAML is
> the deliverable; I write it to `<openrig-user-data-root>/presets/<name>.yaml` without
> touching the rig)?" *(render in the user's language at runtime — this English
> template documents the structure, not the literal words to ship)*

* **(a) MCP** — confirm the MCP tools are wired (precondition below) and follow the
  MCP persistence step (Step 6, MCP branch).
* **(b) file** — the emitted preset YAML is the deliverable; no MCP needed. The only
  MCP calls allowed are reads of `openrig://plugins`, `openrig://project`,
  `openrig://paths` (when the rig happens to be up). Every other MCP call is forbidden.
* **No answer → default to (b) file only** — the flow that always works. Mention you
  can import it into the live bank later if they start OpenRig with `--mcp`.

## Step 0a — Persistent evaluation directory (BEFORE Step 0)

Everything a build produces — fingerprints, renders, report JSONs, per-iteration
research + preset snapshots, the iteration log — lands under a **per-song persistent
directory** so it survives a `/tmp/` wipe, a reboot, a migration, or "re-validate this
preset next month against the same reference".

### Resolve the evaluations directory, once

**MCP up:** read `openrig://paths` (it returns `data_root`, `presets_path`,
`plugins_path`, `evaluations_path` as JSON). Use `evaluations_path` as the root
(`<openrig-evaluations-root>`).

**MCP closed (the common case):** resolve from on-disk config, then the OS default:
1. `<openrig-user-data-root>/config.yaml` → its `evaluations_path` / `plugins_path` /
   `presets_path` keys, if set.
2. Else the OS default data root: macOS → `~/Library/Application Support/OpenRig/`,
   Linux → `${XDG_CONFIG_HOME:-~/.config}/OpenRig/`, Windows → `%APPDATA%\OpenRig\`;
   evaluations live under `<data-root>/evaluations/`.

Do NOT hardcode any per-OS path inline; resolve once and reuse. Pass
`--out-dir`/`--output` at `<openrig-evaluations-root>/<song-slug>/` so outputs land
where they belong from the start, not in volatile `/tmp/` scratch.

### Compute `<song-slug>` and create the directory

`<song-slug>` is derived deterministically from `"<song> - <artist>"` (or
`"<song> - <artist> (<role-group>)"`): lowercase, strip accents, replace any run of
non-`[a-z0-9]` with a single `-`, trim leading/trailing `-`. Keep it stable across
re-builds — the slug is the directory key.

Create (or reuse) `<openrig-evaluations-root>/<song-slug>/` (substitute the real
`<song-slug>`, `<role>`, iteration `<N>`):

```text
<openrig-evaluations-root>/<song-slug>/
├── eval.md                       # human-readable iteration log
├── refs/<role>.wav               # copy of user's reference WAV (sha256 verified), one per role
├── fingerprints/ref-<role>.json  # one per role
├── research/<role>-v<N>.json     # the research JSON you authored (engine input)
├── chains/<role>-v<N>.yaml       # ONLY for the --base-chain escape path
├── renders/<role>-v<N>.wav       # engine render(s)
├── reports/<role>-v<N>.json      # build_preset report JSON per run
└── presets/
    ├── <role>-v<N>.yaml          # emitted preset snapshot per run
    └── <role>-final.yaml         # the version the user accepted
```

### Reuse vs first-build

- **If `<song-slug>/` exists**, READ `eval.md` first: prior iteration count, last
  `proximity_pct` vs floor, status (`done`/`iterating`/`abandoned`), gear mapping.
  Continue numbering from the last `<role>-v<N>`; never overwrite one.
- **If not**, create it fresh; initialise `eval.md` from the template below.
- **Never `rm -rf` an existing `<song-slug>/` to "start clean"** — prior renders,
  reports, and snapshots are the user's audit trail. If genuinely corrupted, ask first.

The `refs/` subdir exists so **re-evaluation (Step 8) remains possible months later**.

### Copy the user's reference WAVs (do NOT symlink)

For every reference WAV: compute its sha256; `cp` (NOT `ln -s`) it to
`refs/<role>.wav`; re-compute the destination sha256 and verify — if not, STOP and
surface the mismatch. If `refs/<role>.wav` already exists: **same hash** → reuse, log
"ref unchanged"; **different hash** → ask once whether it's a deliberate swap or a
mistake. Never silently overwrite a reference prior iterations compared against.

### `eval.md` template

Initialise on first build by **substituting** every `<placeholder>` with the live
value (real song title, artist, slug, chain id):

```markdown
# <Song> — <Artist>
**Status:** iterating
**Date:** <YYYY-MM-DD>
**Chain:** <chain display name> (<chain id>)
**Slots:** <role>=<slot index>

## Gear research
- <bullet list of researched gear + era + sources>

## Mapping
| Real | Resolved catalog id(s) |
| ---- | ---------------------- |
| <real-gear> | <model_id(s) from the report> |

## Iteration log
### <role>
| iter | proximity_pct | self_floor_pct | within | key change |
| ---- | ------------- | -------------- | ------ | ---------- |
| v1   | <pct>         | <floor>        | <bool> | baseline   |

## Param provenance (unverified FX defaults)
- <type/model from the report's param_provenance.unverified, surfaced to the user>

## Methodology notes
- <session-specific notes>

## Sources
- <URLs>
```

Set `Status:` to `done` when the user accepts, `abandoned` if they walk away,
`iterating` otherwise. Optionally maintain a global
`<openrig-evaluations-root>/INDEX.md` (one row per song).

## Step 0b — Resolve the engine (`build_preset.py` + `openrig-render` + DI) — BEFORE Step 0

The build gate runs **`build_preset.py`** (the `openrig-tone-analyzer` engine),
driving the **installed** `openrig-render` — the headless offline renderer OpenRig
ships next to the GUI (#741), the **same** `engine::offline::render_chain` the live
rig uses, so an offline render is byte-identical. No live runtime, no MCP. Resolve
**once, up front**:

**1. `build_preset.py`** — `skills/openrig-tone-analyzer/scripts/build_preset.py`, run
via its venv (`skills/openrig-tone-analyzer/.venv/bin/python`, after `./bootstrap.sh`).
A standalone `resolve_gear.py` CLI also exists, for inspecting the resolved chain from
a research JSON without rendering.

**2. `openrig-render` (`--render-bin`)**, in order:
1. `$OPENRIG_RENDER_BIN` if set — explicit override, wins.
2. `command -v openrig-render` — on `PATH` (Linux `.deb`/`.tar.gz` →
   `/usr/bin/openrig-render`).
3. Per-OS install: macOS → `/Applications/OpenRig.app/Contents/MacOS/openrig-render`
   (also `$HOME/Applications/...`); Linux → `/usr/bin/openrig-render`; Windows →
   `openrig-render.exe` in the install dir.
4. **Dev tree** (contributor in the source repo): `target/release/openrig-render`.

⚠️ **The installed app may NOT ship `openrig-render` yet.** When only the dev-tree
binary resolves, it REQUIRES two extra inputs that map to `build_preset` flags:
- **`--dyld-lib`** → `DYLD_FALLBACK_LIBRARY_PATH` pointing at the NAM dylib dir
  (`libnam_wrapper.dylib`, e.g. `<OpenRig>/build/nam-*/out/lib`). macOS dev only.
- **`--plugins-root`** → `OPENRIG_PLUGINS_ROOT` = `<OpenRig-plugins>/plugins/source`.

With a properly bundled **installed** binary, the bundle's rpath finds the dylib and
the data root auto-resolves the bundled plugins — so `--dyld-lib` is omitted. But
**`--research` ALWAYS requires `--plugins-root`** (it builds the catalog
`resolve_gear` pins against). If neither an installed nor a dev `openrig-render`
resolves, **STOP and tell the user to install/update OpenRig** — never skip the gate.

**3. Bundled DI (`--di`).** macOS →
`/Applications/OpenRig.app/Contents/Resources/assets/audio/input.wav`; Linux →
`/usr/share/openrig/assets/audio/input.wav`; dev → `<OpenRig>/assets/audio/input.wav`.
(Or `openrig://paths.data_root` + `/assets/audio/input.wav` when MCP is up.) You
**never** ask the user for a DI.

**4. Cab model (`--cab-model`, optional).** A catalog `type: cab` plugin model id
(e.g. `ir_marshall_4x12_v30`, NOT a `.wav`) the engine auto-inserts ONLY for a
`type: preamp` core — the cab plugin's manifest `output_gain_db` is applied, so the
level is right. Omit for a `type: amp` (combo/head+cab) or an already-cabbed research
JSON. (You find this id the same way as any gear — research the cab by name and let
`resolve_gear` resolve it, or read `openrig://plugins`/manifests; never type it blind.)

> ⛔ **`openrig-render` EXITS 0 even when it cannot build a block.** It logs `ignoring
> unsupported or invalid block ...` / `unsupported nam model '<id>'` and renders
> WITHOUT that block. A zero exit does NOT prove a complete render. `build_preset`
> handles this: it treats those markers as a HARD failure (`assert_no_dropped_blocks`),
> so no preset can silently ship missing a researched block. (For Step 8 re-eval, scan
> the raw render output yourself.) Exit `1` = render failed; exit `2` = argument error.

## Step 0 — Fingerprint the reference audio FIRST (when WAVs are provided)

If the user provided ANY reference WAV, invoke the
**`openrig:openrig-tone-analyzer` skill on each WAV before research, before gear
mapping, before any MCP call**. The fingerprint is a **primary input for tonal SHAPE**
(where the energy sits) — it shapes the EQ direction; research fills in what the signal
cannot reveal (amp model/era, brand of pedal, delay/reverb). Going straight to research
biases toward what "sounds right on paper"; the opposite failure is **over-trusting
fragile fingerprint fields** (`centroid`, `RMS`, `time_fx`) on a sparse stem. Read the
caveat below.

0. **Guitar-only check.** The reference must be the **isolated guitar**. If the user
   sends a full mix, isolate the guitar first (source separation — e.g. `demucs`); if
   you cannot, STOP and ask for an isolated stem rather than validating against a mix.
1. For each reference WAV, invoke `openrig:openrig-tone-analyzer` with the file path. It
   writes a JSON fingerprint + spectrogram PNGs and returns the paths.
2. **Read every fingerprint JSON before opening any research URL.** It tells you: EQ
   **shape** to lean toward (centroid + band_energy → direction, cross-checked against
   the spectrogram + LTAS, never a hard target); gain stage (gain_character →
   clean/crunch/high-gain); time effects (**low-confidence, do NOT set blocks from
   these**); role hint (source.kind → preset name).
3. If multiple stems (rhythm + lead, several solos), fingerprint **each** separately —
   they produce different presets.
4. **Persist each fingerprint** into `fingerprints/ref-<role>.json` (`cp` from the
   analyzer's scratch dir). Overwrite only when the ref WAV's sha256 also matches.

If the user provided **no** reference audio, skip Step 0 and declare out loud: "no
reference WAV provided — analyzer fingerprint skipped, this preset will be research-only
and cannot be validated objectively."

### ⛔ Fingerprint reliability caveat — which fields lie, and when

A **sparse stem**, a **source-separated stem** (bleed, artifacts), or a **leaky/full
mix** distorts the scalar fields:

| Field | Trust | How to use it |
|---|---|---|
| `band_energy` / normalized **LTAS shape** over signal-bearing windows | **Usable as SHAPE** | Directional EQ guide ("more energy 2–4 kHz") — cross-check against the spectrogram. Never a hard target. |
| `centroid` | **Fragile** | On a sparse/separated stem it tracks *which notes were held*, not timbre. Do not low-pass off a low centroid; confirm against spectrogram + LTAS. |
| `RMS` / loudness | **Never a target** | Reflects performance dynamics + mastering, not tone. Level is the engine's headroom pass, never matched to the ref. |
| `time_fx` (delay/reverb) | **Low-confidence** | Artifact-prone (reverb tail → "long delay"; hall → "spring"). Delay/reverb come from research (Step 2), not this field. |
| `gain_character` / `tone_profile` | Usable | Clean/crunch/high-gain class is robust. |

**The cross-check is always spectrogram PNG + normalized LTAS shape, not a single
scalar.** When a fragile scalar and the spectrogram disagree, the spectrogram + shape
win. (You never substitute your own ear — you have none; the user's ear is the only
override.)

### ⛔ Ref-sanity check — is the top end real, or a separation artifact?

A source-separated stem often **loses its top octave**. The engine detects and excludes
it: when the reference's top octave is dead, the `fingerprint_match_target` marks it
(`top_octave_dead`), the proximity metric restricts to the trustworthy range, and the
EQ trim **holds** the top bands (never cutting toward the dead ref). So `proximity_pct`
already reflects only the trustworthy range; you still gate on `within`. When the top is
dead:
- **NEVER hand-cut the top or swap to a darker amp to "match" the dead ref** — that's
  the "99% but sounds muffled" bug.
- **Let the amp's natural voicing carry the presence.**
- **Tell the user once**, e.g.: *"this stem is source-separated and lost its top octave,
  so I'm matching the trustworthy range and letting the amp's natural brilho carry the
  presence — I will NOT low-pass the tone. A cleaner stem would let me match the full
  range."* *(render in the user's language at runtime)*

### ⛔ HARD RULE — no suppositions about what the reference contains

> Every claim about what is IN the user's reference WAV must cite a **fingerprint field**
> (or a directly readable artefact: spectrogram PNG, raw waveform). **Cultural priors
> about the song / artist / era / genre are NOT evidence about THIS specific WAV.** If
> the fingerprint doesn't measure something, you don't know it — say so.

**Always forbidden** (even in chat narration):
- Claiming a **playing technique** no fingerprint field measures. The fingerprint
  exposes `tone_profile`, `dynamics_profile`, `presence`, `loudness`, `spectrum`,
  `distortion`, `time_fx` — NOT palm-mute, fingerpicking, sweep/hybrid picking, tapping,
  arpeggios, chugging, or strumming pattern. "Heavy palm-mute" about the user's WAV is
  fabrication unless a specific waveform/spectrogram detail supports it (and even then,
  "consistent with X", not "the WAV is X").
- Inferring content from the **song title**, **artist**, **album/era**, or **memory of
  how the song sounds**. The WAV might be a cover, a bad stem, a different section, a
  live take, a remix. Cultural priors belong in **research** (Step 1), not in claims
  about the reference.
- Inventing differences between the DI and the user's reference to explain a gap. Name
  real fingerprint/report deltas, never guessed performance differences.

**Phrase claims correctly** — pair every observation with its citation:
- ✅ "section 2 has `tone_profile: high_gain` (conf 0.88) and `dynamics_profile:
  rhythmic` — the render came out `crunch`, THD deficit ~7%."
- ✅ "I cannot assert the player's technique — the analyzer does not measure palm-mute."
- ❌ "the player is probably palm-muting, that's why it's more compressed."

**Stem vs mix caveat:** an isolated stem's centroid describes the guitar; a full-mix
centroid is dominated by drums/bass/keys and is only an upper bound. When the WAV is a
full mix, treat the centroid as a ceiling, look at guitar-only sections in the
spectrogram, and ask for an isolated stem.

### ⛔ HARD RULE — no suppositions about real-world GEAR / tone / history

This is the **transversal** version, applying in **any** turn this skill is loaded —
including a casual chat question with no build running ("how do you get the Green Day
tone?"). **Never state a claim about real-world gear, signal chains, amp/cab/pedal/
pickup models, specs, prices, an artist's rig, an album's recording setup, or music
history from training memory.** Those priors produced the documented failure: confidently
asserting "Green Day = cranked Marshall, zero pedal, Bill Lawrence L-500XL" — and being
wrong (there was a Boss Blues Driver; the pickup is disputed; the tone is low-gain).

**Every such factual claim must be backed by ONE of:**
1. a **measured number** from the analyzer (fingerprint / `proximity_pct` / LTAS /
   spectrogram), or
2. a **web source you fetched THIS turn** (`WebSearch` / `WebFetch`), URL cited.

If you have neither: **verify first** (`WebSearch`, then cite), or **label it** *"
(unverified — from training memory)"*. "It's the logical answer" = the anti-pattern. A
plugin hook (`no-suppositions-guard`) reinforces this, but the rule binds regardless.

## Precondition (MCP persistence path only) — the MCP server must be connected

Only relevant if the user picked the MCP path (the build itself runs offline):
1. Confirm the OpenRig MCP tools are available (`apply_rig_nav`, `load_chain_preset`,
   `rename_rig_preset`, `save_chain_preset`) and `openrig://project` reads. The OpenRig
   plugin wires this when OpenRig runs with `--mcp`.
2. If not available, STOP. Tell the user to start OpenRig with `--mcp` and install the
   OpenRig plugin (`docs/mcp.md`). Offer the file-only path as the alternative. Do NOT
   silently fall back.

The rig is shared: changes via MCP are reflected in the open GUI in real time.

## Mandatory inputs

- `<artist>` — band/artist name.
- `<song>` — song title (optional but strongly preferred — gear varies by era).
- `<role>` — `rhythm` / `lead` / `solo` / `clean`. Rhythm and lead almost always need
  DIFFERENT presets. Ask once if not given.
- *(optional)* `<reference-audio>` — a WAV stem of the guitar (ideally isolated). Lets
  the engine run the render→compare gate. Without it you cannot validate the preset
  objectively; flag this to the user.

If only `<artist>` is given, ask once for the song and role.

## Workflow — research → `build_preset.py --research` → relay → persist

The SAME flow on both paths; only the final **persist** step (Step 6) differs. The
build is always offline.

### 1. Research the signal chain

**The Step 0 fingerprint comes first.** Research fills gaps the analyzer cannot resolve
(amp model/era, brand of pedal, recording context). If you have not fingerprinted every
reference WAV, go to Step 0.

Hit sources **in order**, stopping when you have a confident gear list (instrument →
pedals → amp → cab → mic). Always cite which sources you used.

| Priority | Source | Why |
|---|---|---|
| 1 | `https://www.tonedb.co/` (search by song or artist) | Crowdsourced, song-specific, often explicit signal chain. JS-heavy — if WebFetch returns 404/empty, fall back to Playwright MCP. |
| 2 | `https://www.groundguitar.com/tone-breakdown/` | Per-song gear listings with chain order. |
| 3 | `https://killerrig.com/` | Numeric knob settings per song. |
| 4 | `https://musicstrive.com/<artist>-amp-settings/` | Settings per song / per guitarist. |
| 5 | `https://www.guitarchalk.com/<player>-amp-settings/` | Player-focused. |
| 6 | `https://prosoundhq.com/...` | Generic recipes; fallback EQ. |
| 7 | `https://blog.andertons.co.uk/sound-like/...` | Gear context per era. |
| 8 | Premier Guitar / Guitar World rig rundowns | Authoritative for era + recording context. |

When two sources disagree on knob values, prefer the one that names the song. **Fallback
ladder when `WebFetch` fails/empties** (common on tonedb.co): Playwright MCP → WebSearch
→ ask the user to paste page text.

**What to research, per element** (the rig the research JSON must cover):

| Element | What you research | Where it goes in the JSON |
|---|---|---|
| compressor | named pedal + (if documented) knobs | `fx[]` `type: dynamics` |
| noise gate | research-cited OR needed for a noisy high-gain capture | `fx[]` `type: dynamics` |
| drive(s) | every boost/OD/distortion/fuzz, in order; players STACK 2–3 | `drives[]` |
| amp | model + brand + any artist `signature`; mod/cranked character | `amp` |
| cab | ONLY if the amp is a preamp (or a documented separate cab) | `cab` (else `null`) |
| modulation | chorus/phaser/tremolo + rate/depth | `fx[]` |
| delay | time (BPM math if undocumented) + feedback + mix | `fx[]` `type: delay` |
| reverb | room (rhythm) / hall (lead), mix | `fx[]` `type: reverb` |
| acoustic body | which guitar (clean/acoustic builds) | `amp` (a `type: body` capture) |

> ⛔ **The drive stage is first-class and STACKS.** An electric tone almost always has
> at least one drive; players run two or three (clean boost → TS → Big Muff). Research
> each, in order, into `drives[]`. A cranked/modded amp's gain is covered by the amp's
> **gain-axis** (note the mod in the amp research), not by defaulting to amp-only. The
> ONLY electric exception is a genuinely clean part. "The amp crunch is enough" is a
> rationalization unless research shows the part was truly pedal-free.

Adjust per style: **Clean/acoustic** — drop the drives + gate, clean amp, add an
acoustic `body`. **Funk/clean rhythm** — keep the compressor, low amp gain.
**Lead solo** — more delay mix, hall reverb. **Delay-driven (Edge/Mayer rhythm)** —
delay time = dotted-eighth at the song BPM (`60000/bpm*1.5/2`), feedback ~25–35%, mix
~30–40% (`provenance: derived`). **Doom/drone** — drop boost, raise reverb mix, tape
delay.

### 2. (No manual id mapping — `resolve_gear` does it)

You do **not** look up model ids or grep manifests for them. `resolve_gear` (inside
`build_preset --research`) greps the offline catalog, **PINS** the exact/signature
capture, emits `candidates:` stand-ins only where no exact capture exists, and ABORTS
on anything it can't back (so you fix the research name). Your only job in this step is
to make the research **names** specific and correct — include the artist + signature so
the catalog grep finds the signature capture (Rule A, Step 3 of THE FORM). Discovery is
the tool's; judgment about *what gear the artist used* is yours.

The Step 0 fingerprint is your primary input for the EQ **shape** (the engine TUNES the
EQ; you never pre-set it) and the gain class. (`time_fx`/`centroid`/`RMS` are fragile —
do not set delay/reverb from `time_fx`, do not EQ-darken off a raw `centroid`, do not
target the ref's `RMS`.) Prefer real amp models the research names; let the tool resolve
them.

### 3. Write the research JSON

Write your cited judgment to
`<openrig-evaluations-root>/<song-slug>/research/<role>-v<N>.json`. Gear NAMES + brands
+ sources (Rule A); FX `params` + `provenance` (Rule B). **No model ids, no param
paths.**

```json
{
  "song": "Gravity", "artist": "John Mayer", "role": "rhythm",
  "id": "john_mayer_gravity_rhythm", "name": "John Mayer - Gravity (rhythm)",
  "amp":  { "name": "Dumble Overdrive Special", "brand": "dumble",
            "signature": "john mayer", "sources": ["<url>"] },
  "drives": [ { "name": "Ibanez TS808", "brand": "ibanez", "sources": ["<url>"] } ],
  "cab": null,
  "fx": [
    { "type": "dynamics", "name": "noise gate", "params": { "threshold_db": -60 },
      "provenance": "unverified", "sources": [] },
    { "type": "delay", "name": "analog delay",
      "params": { "time_ms": 343, "feedback": 28, "mix": 30 },
      "provenance": "derived", "sources": ["<bpm-source>"] },
    { "type": "reverb", "name": "spring", "params": { "mix": 14 },
      "provenance": "unverified", "sources": [] }
  ]
}
```

- **`amp`** — `name` + `brand` + optional `signature` (artist/song capture) + `sources`.
  Note a mod/cranked character in the `name` (e.g. "Marshall 1959SLP Dookie-Mod") so the
  tool regulates the pinned capture's gain-axis. Leave `amp` resolving to a `type: body`
  capture for acoustic/clean builds.
- **`drives[]`** — one entry per pedal, in signal order. Empty `[]` = no drive (clean).
- **`cab`** — an object (`{ "name": ... }`) ONLY when the amp is a preamp or a documented
  separate cab; `null` for a full amp (combo/head+cab). The engine cabs a `preamp` core
  itself (via `--cab-model`).
- **`fx[]`** — every comp / gate / mod / delay / reverb, each with `type`, `name`,
  `params`, `provenance` (`sourced` / `derived` / `unverified`; absent → `unverified`),
  `sources`. The engine keeps each verbatim. **Never put a `limiter` or `volume` here —
  the gate rejects them.** The EQ TUNE slot is inserted by the engine; you never author it.

Before running, re-walk the research **element by element** and confirm each is in the
JSON. A finished JSON with no reverb AND no delay is a red flag (Step 2 of THE FORM).

### 4. Run `build_preset.py --research`

```bash
skills/openrig-tone-analyzer/.venv/bin/python skills/openrig-tone-analyzer/scripts/build_preset.py \
  --research     <…>/research/<role>-v<N>.json \
  --plugins-root <plugins source root>   # REQUIRED with --research (builds the catalog) \
  --ref          <…>/refs/<role>.wav \
  --cab-model    <catalog type:cab model id>   # optional; preamp cores only \
  --render-bin   <openrig-render-bin>    # Step 0b \
  --di           <openrig-di>            # Step 0b \
  --dyld-lib     <NAM dylib dir>         # dev-tree macOS only \
  --out-preset   <…>/presets/<role>-v<N>.yaml \
  --out-report   <…>/reports/<role>-v<N>.json \
  --name "<Song> — <Artist> (<role>)" --id <song-slug>-<role>
```

One command does the whole pipeline: `resolve_gear` turns the names into catalog ids
(PINNING the exact/signature capture, `candidates:` only where none exists); the
**validate + lint GATE** hard-fails an unknown id, an off-axis plugin param, or a
`limiter`/`volume`/policy block BEFORE any render; the gear search picks the best
proximity (the pinned amp never swaps — the number only regulates EQ/gain-axis/drive/
level); the EQ trim (±6 cap, dead-top/out-of-range held); the headroom pass (DI peak ≈
−1 dBFS, never 0). It catches any silently-dropped block and HARD-fails — a clean run
means every researched block built. It emits the preset YAML + report JSON.

**If it ABORTS on `unresolved`:** `resolve_gear` could not back a researched slot — the
gear name was wrong, too vague, or genuinely absent. **Fix the RESEARCH JSON** (tighten
the name; add the artist signature) and re-run. **Never guess an id.** For a genuinely
missing capture, route it through Step 4a.

**If the GATE blocks** (`validation_warnings` / a lint `block`) or the run fails
(`assert_no_dropped_blocks` / non-zero render exit): fix the research and re-run — never
ship past it.

### 4a. A researched capture is genuinely not in the catalog → `tone3000-fetch`

When `resolve_gear` reports a slot `unresolved` and the gear is REAL but not installed
(not just a vague name), the default proposal is **`openrig:openrig-tone3000-fetch`** —
substitution with a different plugin is a last resort, only after import was attempted
and failed OR the user refused. Ask, leading with import:

> "For the [amp/cab/...] the canonical capture (`<gear name>`) isn't in the catalog.
> I'll attempt to import it from tone3000 via `openrig:openrig-tone3000-fetch <query>` —
> this gets the authentic capture, though it triggers the issue → PR → qa_audit/
> pack_plugins flow. Confirm to proceed, or tell me to pick a different path."
> *(render in the user's language at runtime)*

On import success, the user's instance reloads its catalog (`reload_plugin_catalog`)
before the id appears; re-run `--research`. On failure/veto, ask explicitly which
**substitute** gear name to research instead (naming the failure mode), and record it in
the Step 5 provenance. One ask per missing capture; never a unilateral "substitute all".

### 5. Relay the report (incl. lint + unverified FX defaults) + update `eval.md`

The report JSON carries: `amp` / `amp_type` / `amp_params`, `drives` / `drive_params`,
`core` / `core_params`, `cab_model` / `cab_reason`, `fixed_fx_preserved`,
**`param_provenance`** (`blocks` + `unverified`), **`lint`** + **`validation_warnings`**,
`proximity_pct`, `self_floor_pct`, **`within`**, `best_prox`, `peak_db`,
`reliable_range_hz`, `refine_history`, `gear_history`.

**Chat reply provenance summary** (every build):
1. **Chain + slot + preset name** (the actual rig values, never skill examples).
2. **Mapping table**: real gear → the **resolved/chosen** ids from the report (`amp`,
   `amp_params`, `drives`, `cab_model`). Mark any Step-4a substitution (wanted + used).
3. **Match numbers**: `proximity_pct` vs `self_floor_pct`, and `within`. If `within` is
   false, say the gear plateaued below the floor and what you'll widen (or that the floor
   is the honest ceiling).
4. **Headroom**: the report's `peak_db` (e.g. "DI peak −1.1 dBFS, max without clipping").
5. **Lint / validation warnings**: relay any `lint` or `validation_warnings` entry — a
   near-certain issue the gate flagged (not hard-failed).
6. **Unverified FX defaults**: read `param_provenance.unverified` and **surface each**
   ("the comp + reverb knobs are sensible defaults, not sourced — tell me if you have the
   real values"). Never present a default as sourced.
7. **Cite sources** you fetched. **Point at the eval dir**
   (`<openrig-evaluations-root>/<song-slug>/`) for the full audit trail.

**`eval.md`** (per build): append an iteration row (`proximity_pct`, `self_floor_pct`,
`within`, key change); populate `## Gear research`, `## Mapping`, `## Param provenance`,
`## Methodology notes`, `## Sources`; set `Status:`; update a global `INDEX.md` row if
you keep one.

### 6. Persist the emitted preset

**File-only path (default):** the emitted `presets/<role>-v<N>.yaml` IS the deliverable.
Copy it to the user's presets dir `<openrig-user-data-root>/presets/"<Song> — <Artist>
(<role>)".yaml` (ask once if a non-default `presets_path` is configured) and snapshot it
as `presets/<role>-final.yaml` on accept. Tell the user: *"To hear it, open OpenRig,
select chain `<chain>`, and use **Load Preset** pointing at this file. The in-memory rig
was not touched."* *(render in the user's language at runtime)*

**MCP path:** import the emitted preset into a **NEW slot** — never overwrite, never a
manual `add_block`/`set_block_parameter_*` build:

0. **Check first whether a preset for this song already exists** across all chains
   (`openrig://chains/<chain>/presets`, `openrig://presets`). If a candidate exists, STOP
   and ask whether to **replace**, **save alongside** (` (v2)`), or **show only**. Never
   overwrite without confirmation.
1. **Read `openrig://project` and ALWAYS ask where to put this preset** — Step 3.1 below.
2. **Add a NEW empty slot:** `apply_rig_nav { chain, kind: { Preset: -1 } }`. The `-1`
   adds an empty slot and makes it active — it does NOT touch any existing preset.
3. **Load the emitted preset into that slot** — `load_chain_preset` on the written
   `presets/<role>-v<N>.yaml`, or `cp` it into the configured `presets_path` and reload
   the bank. The blocks come from the engine, verbatim — you do not re-author them.
4. **Name + commit:** `rename_rig_preset { chain, name: "<Song> — <Artist> (<role>)" }`
   then `save_chain_preset { chain, name }`. Do **not** call `save_project`. Snapshot the
   live YAML back to `presets/<role>-v<N>.yaml` if it differs.

#### Step 3.1 — Where to put the preset (MCP path) — new slot, never overwrite

**Read `openrig://project` and ALWAYS ask the user.** List every chain (id, display
name, `instrument`, short block summary) as a numbered menu — **including when only one
chain matches** — plus a final "create new chain" option. Do NOT auto-pick.

> "Where do you want to put this preset?
> **(1)** chain `<id>` ('<name>', instrument `<x>`, blocks: `<summary>`)
> ...
> **(N+1) create new chain** — I'll ask for name + instrument + I/O devices."
> *(render in the user's language at runtime)*

You MAY recommend one option, but **MUST wait for the user's explicit pick**.
Auto-selecting because "only one chain matches" is forbidden, as is a single-line "use
`<chain>`? (y/n)" — render the full menu always.

**If the user picks `(N+1) create new chain`:**
1. **Name + instrument prompts** (one ask). Never infer the instrument from the song or
   chain name; re-ask the missing one explicitly.
2. **Read `openrig://devices`** ONCE, immediately before the menus, and render TWO
   numbered menus (input, output) using the actual `<label>` + `device_id`. Recommend
   allowed, but wait for an explicit pick per side; render the menu even with one device.
3. **Channels + mode prompts** per chosen device (`[1]` mono, `[1,2]` stereo; mode
   `mono`/`stereo`/`dual_mono`). Suggest a default, never self-apply.
4. **Build the Chain payload and call `add_chain`:**
   ```json
   { "chain": { "enabled": true, "instrument": "<from 1>", "blocks": [
     { "id": "rig:input",  "kind": { "Input":  { "entries": [{ "device_id": "<…>", "channels": [<…>], "mode": "<…>" }] } } },
     { "id": "rig:output", "kind": { "Output": { "entries": [{ "device_id": "<…>", "channels": [<…>], "mode": "<…>" }] } } }
   ] } }
   ```
   If `add_chain` errors, **STOP and surface the exact error** — do not retry with
   mutated values or fall back to a different device.
5. **Continue the import into the new chain id.**

**Zero chains:** go straight to create-new (still asking name + instrument + I/O) but say
"your rig has no chains yet — I'll create one". **Exactly one chain:** still render the
menu. **No answer:** ask once more or stop — never decide for them.

## Step 8 — Re-evaluation of an existing preset

Use when the user asks to re-validate a preset that already exists ("compara de novo X
com a ref", "rerun the compare for <song>"). NOT a fresh build — no research, no rebuild.
A strict **render-current-YAML → compare → log** cycle.

Preconditions: (1) `openrig-render` resolves (Step 0b); (2) `refs/<role>.wav` exists
(else ask for the original ref and run Step 0a + Step 0 to backfill); (3) the preset YAML
exists (the live `presets/...yaml` OR `presets/<role>-final.yaml` — ask which if they
diverge).

Flow:
1. **Read `eval.md`** to recover chain, gear mapping, last index. Use a
   `<role>-vREEVAL-<YYYY-MM-DD>` index (re-evals don't bump `<N>`).
2. **Render the current preset YAML** directly: `<openrig-render-bin> --chain
   <preset.yaml> --input <openrig-di> --output <…>/renders/<role>-vREEVAL-<date>.wav`.
   ⚠️ **Scan the render's stdout+stderr for `ignoring unsupported or invalid block` /
   `unsupported nam model`** — exit 0 does NOT prove a complete render. If a marker
   appears, surface it; don't compare a partial render.
3. **Compare** against the persistent ref: `.venv/bin/python scripts/compare.py
   <…>/refs/<role>.wav <…>/renders/<role>-vREEVAL-<date>.wav --output
   <…>/diffs/<role>-vREEVAL-<date>.json`.
4. **Append a re-eval row** to `eval.md` (do NOT flip `Status:` from `done`). To actually
   tune from the result, that's a fresh build (re-run `build_preset.py`, continuing `<N>`).
5. **Chat reply**: the new proximity, the diff vs the prior best (from `eval.md`), the
   diff-file path.

Re-eval does NOT mutate the rig, does NOT call `save_chain_preset`.

## Validation before declaring done

- [ ] You fingerprinted every reference WAV (Step 0) BEFORE research and any MCP call,
      and the reference is the **isolated guitar** (separated from a mix if needed, or you
      stopped and asked for a stem) — never a full-band mix.
- [ ] You resolved `<openrig-user-data-root>` / `<openrig-evaluations-root>` per OS (or
      via `openrig://paths` / `config.yaml`) at the top of Step 0a and used the resolved
      value everywhere. No `~/.openrig/` literal in any output.
- [ ] You created `<openrig-evaluations-root>/<song-slug>/` with the full subtree
      (`refs/`, `fingerprints/`, `research/`, `renders/`, `reports/`, `presets/`,
      `eval.md`); ref WAVs `cp`'d (NOT symlinked) and sha256-verified; fingerprints
      persisted.
- [ ] You authored a **research JSON** (gear NAMES + Rule-B FX params/provenance) — NOT a
      hand-typed model id or param path anywhere. The COMPLETE researched rig is in it:
      every drive/comp/gate/mod/delay/reverb the research showed, the amp (+ artist
      `signature` for the catalog grep), `cab` only for a preamp.
- [ ] You ran **`build_preset.py --research`** (with `--plugins-root`) — not a hand-built
      `add_block` loop, not a manual eq_match loop. It did NOT abort on `unresolved`
      (every researched name was backed by the catalog, or a genuinely-missing capture
      went through Step 4a `tone3000-fetch` / an explicit user-picked substitute), the
      GATE passed (no `validation_warnings` hard-fail), and it completed without
      `assert_no_dropped_blocks` / render failure. The render used the bundled
      `<openrig-di>`, never a user DI.
- [ ] You gated on the report's **`within`** (`proximity_pct ≥ self_floor_pct − 3`), NOT a
      fixed 95, NOT `match_score`, NOT a hand-converted dB gap. If it plateaued below the
      floor you widened the research and re-ran — you did NOT swap a pinned amp to chase
      the number, and did NOT call a below-floor preset done (unless the floor IS the
      honest ceiling, reported plainly).
- [ ] You relayed the report's `peak_db` (engine headroom set the EQ `output_db` to ≈ −1
      dBFS, hot but never clipping; you did NOT match the ref's RMS, did NOT add a
      limiter/volume, did NOT hand-stage level), the `lint`/`validation_warnings`, and
      surfaced every `param_provenance.unverified` FX default — no default presented as
      sourced.
- [ ] You did NOT set delay/reverb from `time_fx`, did NOT EQ-darken off a raw `centroid`,
      did NOT assert a sonic verdict of your own. The user's ear redirected the build ONLY
      when the user said it's bad.
- [ ] **Persist (file path):** the emitted preset YAML was copied to the presets dir and
      snapshotted to `presets/<role>-final.yaml` on accept. **Persist (MCP path):** you
      checked for a pre-existing preset, ran the Step 3.1 menu (no auto-pick; `add_chain`
      only with all four prompt blocks answered + `openrig://devices` read), added a NEW
      slot via `apply_rig_nav Preset(-1)`, loaded the emitted preset, set the name via
      `rename_rig_preset`, committed via `save_chain_preset`, and did NOT call
      `save_project`.
- [ ] `eval.md` was updated per build with the proximity/floor/within row and `Status:`.

## Red flags — STOP

- **Typing a model id or param path yourself** instead of feeding a gear NAME and letting
  `resolve_gear` back it. The gate exists to block guessed ids — fix the research name,
  never hand-author the id. (The ONE pointer: the gate HARD-fails an unknown id / off-axis
  param / `limiter`/`volume`; an `unresolved` abort means fix the RESEARCH, never guess.)
- **Hand-building the preset with `add_block`/`set_block_parameter_*` instead of running
  `build_preset.py --research`.** The engine owns resolve → gate → search → EQ trim →
  headroom. Your job is the research JSON + relaying the report. (The only MCP mutations
  are the Step 6 import: `apply_rig_nav Preset(-1)` → load → `rename_rig_preset` →
  `save_chain_preset`.)
- **Guessing an id to get past an `unresolved` abort.** The abort means the gear name was
  wrong/vague or the capture is genuinely missing — fix the name, or route it through
  `tone3000-fetch` (Step 4a). Never feed the tool an id it couldn't resolve itself.
- **Letting the number SWAP the artist's actual amp.** On a real "Gravity" build the
  proximity ranked a generic `nam_fender_deluxe_reverb` (67.81%) above the artist's
  `nam_dumble_ods_john_mayer` (66.10%) — a 1.7% noise gap, nothing clearing the floor.
  When the EXACT capture exists, `resolve_gear` PINS it and the number only regulates its
  gain-axis; it NEVER picks the amp. A below-floor pinned chain is a degraded-ref /
  wrong-drive / high-floor signal you surface — not a license to ship the Fender. Cite the
  artist + signature in the research so the catalog grep finds the signature capture.
- **Leaving timbre blocks at default while only the EQ moves** — "todos os blocos têm
  regulagens" (every block has adjustments). Regulating is multi-block: the amp gain-axis
  + the drive + the EQ together, and every feel block (comp/gate/delay/reverb/mod) carries
  researched params (Rule B), never the engine/plugin default.
- **Shipping a chain with ZERO reverb AND ZERO delay** without a cited source confirming
  the part is dry — almost always a research miss. Re-research the ambience or cite the
  dryness. **And leaving a noisy high-gain capture UNGATED** — add + enable a `dynamics`
  gate when research or the measured noise floor calls for it.
- **Presenting a guessed FX knob (comp/mod/delay/reverb) as if researched.** If a param
  isn't documented or derivable, set a default, tag `provenance: unverified`, and surface
  it from the report's `unverified` list (Rule B). The proximity number never sets these.
- **Researching a cab after a full amp.** A `type: amp` capture (combo OR head+cab) has
  its speaker baked in — set `cab: null`. A separate cab auto-inserts ONLY for a
  `type: preamp` core (via `--cab-model`). Never research both.
- **Chasing the raw `match_score`, a fixed 95, or a hand-converted dB gap.** Gate on the
  report's **`within`** (`proximity_pct ≥ self_floor_pct − 3`). The raw score folds in
  onsets/silence/level and can't converge (the "Gravity" 166→131 dB stall).
- **Asserting your OWN sonic verdict** ("sounds muffled/dark/the delay is too long"). You
  cannot hear — that is fabrication (Step 0). Act on the measurement; the only ear that
  redirects the build is the **user's**, and only when they say it's bad — and then that
  complaint overrides the number (**dismissing the user's ear** is equally forbidden).
- **Treating a fragile fingerprint field as a target** — `time_fx` (a reverb tail reads
  as an 865 ms delay), a low `centroid` (tracks which notes were held → don't low-pass),
  the ref's `RMS` (performance + mastering → never matched). Delay/reverb from research;
  centroid as directional shape vs the spectrogram; level from the headroom pass.
- **Reporting "done" without running `build_preset.py`** when a reference exists ("you
  should run the render"). A research-only preset is a guess.
- **Silently substituting a missing capture** instead of proposing `tone3000-fetch` first
  (Step 4a) — substitution is a fallback that still needs the user's specific pick.
- **Proposing any write to `~/.claude/projects/*/memory/`** to capture a user correction.
  Corrections go into the **SKILL** (this file) or the project's **`CLAUDE.md`** — local
  memory doesn't ship with the plugin.
- **Claiming a playing technique** (palm-mute, sweep, tapping, chugging) or **using
  song/artist/era/genre knowledge as evidence about THIS WAV.** The fingerprint doesn't
  measure technique; cultural priors feed research (Step 1), never claims about the audio.
- **Calling `add_chain` without `openrig://devices` + both I/O menus + explicit
  device/channels/mode picks**, or **auto-picking a chain** in Step 3.1.
- **`rm -rf`-ing an existing `<song-slug>/`**, **leaving renders/reports in `/tmp/`**,
  **symlinking** the ref instead of `cp`, or **hardcoding `~/.openrig/`** / any per-OS path
  inline (resolve once in Step 0a).
- **Opening any reference / planning the layout before invoking
  `openrig:openrig-tone-analyzer` on every reference WAV.** Step 0 comes first.

## Common rationalizations — forbidden

| Rationalization | Reality |
|---|---|
| "I'll just type the `nam_*` id myself, it's faster than naming the gear" | You NEVER type an id. `resolve_gear` greps the catalog and PINS the exact capture; the gate hard-fails a guessed id. Feed the gear NAME + signature; fix the research if it aborts. |
| "`resolve_gear` aborted on `unresolved` — I'll feed it an id to unblock it" | The abort means the NAME was wrong/vague or the capture is genuinely missing. Tighten the name (add the artist signature), or route a real-but-missing capture through `tone3000-fetch`. An id you'd type is exactly what the abort exists to prevent. |
| "I'll hand-build it with `add_block` / hand-tune the EQ — same result" | No. `build_preset.py --research` is the deterministic FORM: resolve+pin → gate → gear search → EQ trim (±6) → headroom, one pass. A hand loop is the stale manual workflow this skill replaced. |
| "I'll add a safety limiter / output volume so it doesn't clip" | The GATE hard-fails `limiter_brickwall` / `type: volume`, and the engine strips them. The chain ends at the EQ; headroom is the EQ `output_db` (DI peak ≈ −1 dBFS, report `peak_db`). |
| "Proximity is stuck at 88%, close enough / best I can get" | The bar is the report's `within` (within ~3% of `self_floor_pct`), not 95. If 88% is below the floor, widen the research. If 88% IS within ~3% of the floor (the material's ceiling), you're DONE — stop chasing an impossible number. |
| "The number ranked a Fender above the John-Mayer Dumble, so I'll ship the Fender" | The number is too weak to tell amps apart — 67.81% vs 66.10% is a 1.7% noise gap, nothing cleared the floor. When the exact capture exists `resolve_gear` PINS it and the number only regulates the gain-axis; it NEVER picks the amp. A below-floor pinned chain is a degraded-ref / wrong-drive / high-floor signal you surface. |
| "I'll just regulate the EQ, the other blocks are fine at default" | Regulating is multi-block: the amp gain-axis + the drive + the EQ trim all move, and every feel block carries researched params (Rule B), never the default. A run where only the EQ moved is wrong — "todos os blocos têm regulagens". |
| "No reverb or delay in my JSON — the record was probably dry" | "Probably dry" is an assumption, not a source. Zero reverb AND zero delay is a red flag: re-research the ambience or cite a source. And a noisy high-gain capture needs an enabled gate. |
| "I don't have the comp's exact knobs, I'll set values and move on" | Set the default, but tag `provenance: unverified` and surface it from the report's `unverified` list (Rule B). Never present a default as sourced; the number never sets feel params. |
| "I built it from research, no need to render" | Research = educated guess. `build_preset.py` is mandatory when a reference exists; the only validated preset is one the engine rendered + measured to the floor. Clocks v1 (saved without rendering) was thrown away. |
| "I'll convert `total_gap_db` to a % / gate on the dB gap / chase `match_score`" | The report emits `proximity_pct` + `self_floor_pct` + `within` directly. Gate on `within`. `match_score` folds in level/onsets/silence and never converges on a real recording. |
| "It sounds muffled to me, so I'll EQ-brighten / trust the number over the user" | A sonic opinion from YOU is fabrication — you have no ears; act on the measurement. But when the **user** says it's bad, that overrides the number — act on their specific complaint. |
| "The fingerprint says delay 865 ms / centroid is low / RMS is quiet — I'll use it" | `time_fx`/`centroid`/`RMS` are fragile (an 865 ms "delay" was a reverb tail; centroid tracks which notes were held; RMS is performance + mastering). Delay/reverb come from research; centroid is directional shape only; level is the headroom pass. Never a target. |
| "I'll toss extra amps/pedals into the research to see what scores" | Rule A: the research is the artist's actual gear, cited. The engine picks among research-derived options only; padding with unrelated gear to fish for a score is the anti-pattern. Thin research → dig deeper, not wider with guesses. |
| "Only one chain matches / the user pre-confirmed it earlier" | Step 3.1 always renders the menu and waits for the pick, even with one match. Unless you can paste a verbatim "use chain X" from THIS turn, they did not pre-confirm. Cross-session memory is forbidden. |
| "The Metallica riff is obviously high_gain — I'll skip the fingerprint / research first" | Step 0 is unconditional and comes before research. The WAV could be a cover, a different take, a clean mix; research-first biases toward what sounds right on paper. Cultural prior + "obvious" = the failure this skill blocks. |
| "The user corrected me — I'll save the lesson to memory" | Local memory is per-machine, doesn't ship with the plugin. A correction becomes an edit in `SKILL.md` or the project's `CLAUDE.md`. |
| "MCP isn't connected, I'll just write the YAML" | The file-only path is a first-class valid path — but the user picked the path in Step −1. Don't silently switch; if they chose MCP, stop and ask. |

## Anti-patterns (all paths)

- ❌ **A `preamp` for a full-amp song** — `preamp` has no power-amp/cab; songs almost
  always want `amp`. (And never research both a full amp and a cab — double cabinet.)
- ❌ (MCP path) **Editing the chain's current blocks / `apply_rig_nav`-skipping** to write
  a preset — switch to a NEW slot first; **calling `save_project`** instead of
  `save_chain_preset`; **overwriting an existing preset** without asking; **`add_chain`
  with `blocks: []`** or inferred device_ids.
- ❌ **Silently switching MCP↔file** without the user's explicit Step −1 answer.
