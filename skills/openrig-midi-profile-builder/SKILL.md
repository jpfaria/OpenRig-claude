---
name: openrig-midi-profile-builder
description: "Use when the user asks to author a MIDI profile for a controller OpenRig doesn't ship a factory profile for yet, customise an existing profile, or convert a MIDI Monitor / receivemidi capture into a profile YAML. Triggers: \"cria profile MIDI pro [pedal]\", \"meu Chocolate / FCB1010 / iRig BlueBoard / Behringer / Morningstar MC8 não tem profile\", \"converte este log do MIDI Monitor em profile\", \"adapta o profile do Chocolate pro meu setup\", \"build a MIDI profile\". Writes `<name>.yaml` + `<name>.md` either to the user's per-app dir (custom) or to the OpenRig repo `assets/midi-profiles/` (factory contribution)."
---

# OpenRig MIDI Profile Builder

Author a MIDI profile for OpenRig from either (a) a live capture of the
controller's messages, or (b) the user telling you what each switch /
knob should do. The output is two files the runtime picks up
immediately — no rebuild required.

This skill is a **pure file-writer**. It does NOT touch the OpenRig
runtime. The daemon loads new profiles when the user clicks the
**refresh** button in **Settings → MIDI** (or restarts the app).

## What a profile is

A YAML in one of two directories:

- **User**: `~/Library/Application Support/openrig/midi-profiles/<name>.yaml`
  (macOS) — `~/.local/share/openrig/midi-profiles/` (Linux),
  `%APPDATA%/openrig/midi-profiles/` (Windows). Drop a file here; the
  daemon picks it up on the next refresh / restart.
- **Factory** (PR to the OpenRig repo): `assets/midi-profiles/<name>.yaml`
  ships with the binary as a bundled profile.

Each YAML carries:

```yaml
name: "Human-readable profile name"
source: "FootCtrlPlus"      # optional substring of the MIDI port name
description: |              # optional
  free-form
bindings:
  - when: { kind: ProgramChange, channel: 1, program: 0 }
    do: prev_chain
  - when: { kind: ControlChange, channel: 1, controller: 7 }
    do: chain_volume
```

Each `<name>.yaml` has a companion `<name>.md` with the
bank/switch/knob table for humans (the `Settings → MIDI` UI shows it).

## The 21 catalog slots — `do:` must be one of these

The parser rejects anything else at load time. Source of truth lives
in `crates/adapter-midi/src/profile.rs::CATALOG` in the OpenRig repo
(`https://github.com/jpfaria/OpenRig`, branch `develop` once issue
#548 lands).

| # | Slot | What it does |
|---|---|---|
| 1 | `toggle_tuner` | Flip the tuner button. |
| 2 | `toggle_output_mute` | Flip output mute. |
| 3 | `toggle_spectrum` | Flip the spectrum window. |
| 4 | `prev_chain` | Active chain ← (wraps). |
| 5 | `next_chain` | Active chain → (wraps). |
| 6 | `toggle_active_chain_enabled` | Enable/disable the active chain. |
| 7 | `toggle_compact_view` | Flip the compact-view UI. |
| 8 | `prev_preset` | Previous preset on the active chain (wraps). |
| 9 | `next_preset` | Next preset on the active chain. |
| 10 | `prev_scene` | Previous scene on the active chain. |
| 11 | `next_scene` | Next scene on the active chain. |
| 12 | `jump_preset_n` | Jump to preset `N` (`N` = MIDI value byte). |
| 13 | `jump_scene_n` | Jump to scene `N`. |
| 14 | `prev_block_1` | Previous block (1 step, wraps). |
| 15 | `next_block_1` | Next block (1 step, wraps). |
| 16 | `prev_block_2` | Previous block (2 steps — compact-view pair). |
| 17 | `next_block_2` | Next block (2 steps). |
| 18 | `toggle_active_block_enabled` | Bypass/engage the active block. |
| 19 | `toggle_active_block_neighbor_enabled` | Bypass/engage the block AFTER the active one (the right of the compact-view pair). |
| 20 | `chain_volume` | CC continuous — scales 0..127 → 0.0..1.0 on the active chain. |
| 21 | `block_param_numeric` | CC continuous — first numeric param of the active block. |

Slots that act on the "active chain / block" depend on the user having
clicked the chain/block (or having navigated to it via MIDI itself).
`jump_*_n` reads the MIDI value byte as the index.

## The 4 supported `kind`s

Standard MIDI 1.0 names — the parser is strict about the spelling.

| `kind` | Required | Optional |
|---|---|---|
| `NoteOn` | `channel` (1-16) | `note` (0-127). Omit → wildcard. |
| `NoteOff` | `channel` | `note`. Omit → wildcard. |
| `ControlChange` | `channel` | `controller`. Omit → wildcard. |
| `ProgramChange` | `channel` | `program`. Omit → wildcard. |

Omitting the value field makes the binding wildcard-match — the slot
sees the byte. Used by `jump_preset_n`, `jump_scene_n`, and continuous
CCs.

## Source filter

`source:` (optional) filters by **substring** of the MIDI port name as
the OS exposes it. Examples observed in the wild:

- macOS BLE: `FootCtrlPlus Bluetooth` (M-Vave Chocolate family)
- USB devices typically end in the model name, sometimes prefixed by
  the vendor.

Pick a substring stable enough to survive a re-pair but specific
enough to exclude other ports. `FootCtrlPlus` works for the Chocolate
family across macOS BLE and the equivalent USB name on Linux.

## Workflow

### Step 0 — Decide user vs factory

Ask once:

- "Is this for **just your setup** (user profile, lives in your home
  dir) or for **everyone using OpenRig** (factory profile, lands in
  the OpenRig repo as a PR)?"

User profile → write straight into `<DATA_DIR>/openrig/midi-profiles/`.
Factory profile → write into a clone of the OpenRig repo's
`assets/midi-profiles/` and remind the user to open a PR.

### Step 1 — Identify the controller and its mode

- Model + firmware (Chocolate Plus / Chocolate / FCB1010 / iRig
  BlueBoard / Morningstar MC8 / generic …).
- Vendor app mode if any (CubeSuite "Program change A", "Advanced
  custom mode", etc.).
- The MIDI port name as it shows up in MIDI Monitor / Audio MIDI
  Setup — this becomes the `source:` substring.

### Step 2 — Capture or specify

Two paths; pick whichever is faster for the user.

**A) Capture from the device**

1. macOS: install [MIDI Monitor](https://www.snoize.com/midimonitor/),
   start it, tick the controller in Sources.
2. Linux: `brew install gbevin/tools/receivemidi`, then
   `receivemidi dev "<your port name>"`.
3. Press each switch / move each knob in a known order, then paste
   the log here.

Parse each row into `(kind, channel, value, repeat-pattern)`. Group
rows that look like sustain (NoteOn paired with NoteOff at the same
note) and treat them as one switch.

**B) Specify by hand**

If the user already knows what their pedal sends (e.g. "CubeSuite is
in Program change A — bank N switch X sends PC = 4(N-1)+X-1 on channel
1"), skip the capture and produce the table directly. The Chocolate
Plus factory profile is the canonical example for this path.

### Step 3 — Bank/section the captured rows

A pedal usually has more switches than the user has actions for. Group
rows into **banks** (or "themes"): chains nav, preset/scene, blocks,
toggles, etc. Bank 1 should always be the most-frequent live actions.

Reference layout (from the shipped Chocolate Plus profile):

| Bank | Theme | A | B | C | D |
|---|---|---|---|---|---|
| 1 | Chains | prev_chain | toggle_active_chain_enabled | toggle_compact_view | next_chain |
| 2 | Preset/Scene | prev_preset | next_preset | prev_scene | next_scene |
| 3 | Block pair | prev_block_2 | toggle_active_block_enabled | toggle_active_block_neighbor_enabled | next_block_2 |
| 4 | Globals | toggle_tuner | toggle_output_mute | toggle_spectrum | *(unbound)* |

Adapt to the controller — an FCB1010 has 10 switches + 2 expression
pedals; an iRig BlueBoard has 4 + expression input; an expression
pedal alone is just `chain_volume` / `block_param_numeric` CC.

### Step 4 — Walk the user through assignment

For each captured / specified row, ask **one question**:

> Switch/knob sends `<kind, channel, value>`. Which slot should it run?
> (Catalog above, or "skip" to leave unbound.)

Build the bindings list as you go. Reuse the same `kind`/`channel` so
the YAML stays consistent.

### Step 5 — Emit the YAML + markdown

Suggested file name: `<vendor>_<model>_<mode>.yaml` —
`chocolate_plus_program_change_a.yaml`, `fcb1010_factory.yaml`,
`expression_pedal_cc11.yaml`. Lower-case, snake_case, no spaces.

YAML structure (the parser is strict; this is the exact shape that
loads cleanly):

```yaml
name: "<Pretty Name> (factory|custom)"
source: "<port-name-substring>"
description: |
  Multi-line explanation of the mode + bank layout. Optional but
  helpful.

bindings:
  - when: { kind: ProgramChange, channel: 1, program: 0 }
    do: prev_chain
  # ...
```

Markdown companion (`<name>.md`) — the GUI's [View Map] link opens it:

```markdown
# <Pretty Name>

| Field | Value |
|---|---|
| Source | `<substring>` |
| Channel | <N> |
| Message type | <Note / CC / PC> |

| Bank | A | B | C | D |
|---|---|---|---|---|
| 1 | <slot> | <slot> | <slot> | <slot> |
| 2 | ... |
```

End the markdown with a short "How to pair" section if the device
needs special setup (BLE pairing, vendor-app export, etc.).

### Step 6 — Where to write

- **User profile** → write straight into:
  - macOS: `~/Library/Application Support/openrig/midi-profiles/`
  - Linux: `~/.local/share/openrig/midi-profiles/`
  - Windows: `%APPDATA%\openrig\midi-profiles\`

  Make the dir with `mkdir -p` if missing. The OpenRig daemon picks it
  up on the next **Settings → MIDI → refresh** click — no app restart
  needed.

- **Factory profile** → write into the OpenRig repo at
  `assets/midi-profiles/`. Then tell the user:

  > Wrote `assets/midi-profiles/<name>.{yaml,md}`. Commit on a branch
  > like `feature/midi-profile-<name>` and open a PR against
  > `develop` so it ships in the next release.

  Do **not** open the PR yourself — it's the user's contribution.

### Step 7 — Validate

After writing, run this sanity check by hand:

1. `grep -n "do:" <name>.yaml` — every right-hand value MUST be in the
   21-slot list above; the parser rejects unknown slot names at load
   time.
2. `grep -n "kind:" <name>.yaml` — every value MUST be exactly
   `NoteOn` / `NoteOff` / `ControlChange` / `ProgramChange`. Anything
   else is a typo that turns the binding into noise.
3. Channels in `1..=16`, values in `0..=127`.

If the user wants a stronger gate, point them at
`crates/adapter-midi/tests/profile_dir_loader_test.rs` in the OpenRig
repo — drop the new file into a `tempfile::TempDir` in that test and
call `load_profiles_from_dir` to round-trip it.

## Anti-patterns

- **Inventing slot names.** Only the 21 listed above are valid. If a
  user wants something that isn't there (e.g. "save preset", "trigger
  latency probe"), ask them to file an OpenRig issue first — the
  Command + slot have to be added in the Rust code, not in the YAML.
- **`source:` too broad.** `"Bluetooth"` matches every BLE-MIDI device.
  Use the device-specific substring (`FootCtrlPlus`).
- **`source:` too narrow.** Pinning the trailing ` Bluetooth` /
  ` USB` suffix breaks across platforms / transports. Strip it.
- **One YAML per pedal AND per mode.** Different vendor-app modes
  (Chocolate's "Program change A" vs "Advanced custom") emit
  different messages — they need separate profiles, not one big
  catch-all.
- **Writing into the running app's user dir from inside the OpenRig
  repo workspace.** Always resolve the platform user data dir; never
  hard-code `~/.local/share/...` on a Mac.

## See also

- `docs/midi-profiles.md` in the OpenRig repo — same content, deeper.
- `assets/midi-profiles/chocolate_plus_program_change_a.{yaml,md}` —
  the canonical factory profile this skill mirrors.
- Issue jpfaria/OpenRig#548 — the design spec and the 21-slot catalog
  rationale.
