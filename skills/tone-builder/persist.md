# Persisting a tone-builder preset in OpenRig

Moved verbatim from the former SKILL.md (step 6). `presets/<role>-v<N>.yaml` below is the `preset.yaml` that `tone-builder build` writes.

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

**A chain does NOT carry device endpoints.** It references **per-machine I/O bindings by
id** (`io_binding_ids`) and the engine discovers its input/output endpoints from them. A
chain created by the GUI has NO `Input`/`Output` blocks — its `blocks` list starts at the
first FX. Build one the same way.

1. **Name + instrument prompts** (one ask). Never infer the instrument from the song or
   chain name; re-ask the missing one explicitly.
2. **Read the I/O binding registry and render it as a menu — this is the common case.**
   The registry is per-machine and lives in `<openrig-user-data-root>/config.yaml` under
   `io_bindings:` (no MCP resource exposes it yet — read the file; `openrig://project`
   only shows which ids each chain already uses). Render every binding numbered:

   > "Which I/O binding should the new chain use?
   > **(1)** `io-1-2a1b` — 'Scarlett 2i2' — in: `In 1` (ch `[0]`, mono) · out: `Out 1` (ch `[0,1]`, stereo)
   > ...
   > **(N+1) create a new binding** — I'll ask for device + channels + mode."
   > *(render in the user's language at runtime)*

   Recommend allowed, but **wait for the explicit pick** — render the menu even with one
   binding. An existing binding that already covers the wanted in/out is the answer;
   creating a second binding over the same channels is not.
3. **Only when no existing binding serves** (the user picked `(N+1)`, or `io_bindings:` is
   empty): read `openrig://devices` ONCE and render TWO numbered device menus (input,
   output) using the actual `<label>` + `device_id`; ask channels + mode per side
   (**zero-based**: `[0]` mono, `[0,1]` stereo; mode `mono`/`stereo`/`dual_mono`). Suggest
   a default, never self-apply. Then build the binding:
   ```
   create_io_binding { "binding": { "id": "<slug>", "name": "<label>", "inputs": [], "outputs": [] } }
   add_io_endpoint  { "binding_id": "<slug>", "device_id": "<in…>",  "channels": [0],    "mode": "mono",   "is_input": true  }
   add_io_endpoint  { "binding_id": "<slug>", "device_id": "<out…>", "channels": [0,1], "mode": "stereo", "is_input": false }
   ```
   Endpoint names are auto-assigned by the handler (`In 1` / `Out 1`).
4. **Verify the input channel is free BEFORE calling `add_chain` with `enabled: true`.**
   The engine refuses a second enabled chain on a captured input:
   ```
   chain 'chain:<uuid>' cannot be enabled: input '<device>' channel 0 is already captured
   by the enabled chain 'rig:input-1' — disable that chain or bind this one to a free channel
   ```
   From `openrig://project` take every chain with `enabled: true` and its
   `io_binding_ids`; resolve those bindings' input channels in `config.yaml`. If the
   chosen binding's input channel collides, **STOP and offer the three legitimate exits**:
   **(a)** create the chain **disabled** (`enabled: false`) and enable it later, **(b)**
   bind to a free channel (pick/create another binding), **(c)** disable the occupying
   chain. The user picks — never decide for them.
5. **Build the Chain payload and call `add_chain` — with NO I/O blocks:**
   ```json
   { "chain": {
       "enabled": true,
       "instrument": "<from 1>",
       "description": "<chain name from 1>",
       "io_binding_ids": ["<binding id picked in 2/3>"],
       "blocks": []
   } }
   ```
   `blocks` holds FX only. Never emit `{ "Input": … }` / `{ "Output": … }` entries: the
   routing already comes from `io_binding_ids`, and those blocks make the chain look
   unlike every GUI-made chain in the same rig.
   If `add_chain` errors, **STOP and surface the exact error** — do not retry with
   mutated values or fall back to a different device or binding.
6. **Continue the import into the new chain id.**

**Zero chains:** go straight to create-new (still asking name + instrument + I/O) but say
"your rig has no chains yet — I'll create one". **Exactly one chain:** still render the
menu. **No answer:** ask once more or stop — never decide for them.

