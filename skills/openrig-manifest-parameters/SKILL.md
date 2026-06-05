---
name: openrig-manifest-parameters
description: "Use when authoring or fixing the parameters/captures block of an OpenRig plugin manifest.yaml — deciding the axes and values for NAM/IR captures, or when the OpenRig model picker shows a flat \"model\" dropdown, raw filenames as values, quoted numbers, or invented low/mid/high knobs. Triggers: \"parâmetros ficaram errados\", \"deveria ser um knob\", \"ainda está com model\", \"os parâmetros não batem com o arquivo\", reviewing manifest parameters, fixing a tone3000 import's params."
---

# openrig-manifest-parameters

How an OpenRig plugin's **parameters** are created. This is the canonical
method; `openrig-plugin-author` and `openrig-tone3000-fetch` defer to it
for the `parameters:`/`captures:` block.

## Core principle

**The capture FILENAME is the source of truth for the parameters.** Each
`.nam`/`.wav` filename encodes the knob/switch settings that capture was
taken at. Decompose every filename into those exact settings and expose
THEM as the axes. Never invent an abstraction, never collapse real
controls into one axis, never dump raw filenames as values.

```
file: captures/plumes_switch_3_level_25_gain_75_tone_100.nam
        → switch=3 (constant → omit) · level=25 · gain=75 · tone=100
parameters: level [25,50,100] · gain [0,50,75] · tone [0,25,50,75,100]   (all NUMERIC → knobs)
```

`level: 25, gain: 75, tone: 100` is what the user SEES in that filename —
that is exactly what the manifest must say. Anything else (a "drive:
low/mid/high" axis, a single "model" dropdown) is wrong.

## Method (per plugin)

1. **List every capture filename.** `ls captures/` (NAM) or the IR dir.
2. **Tokenize each filename** on `_`/`-`/space. Identify each setting:
   its NAME (gain, drive, tone, level, treble, bass, mid, presence,
   master/mv, volume, depth, reverb, sustain, blend, contour, channel,
   mic, voicing, mode, switch, rectifier, boost, pickup…) and its VALUE.
3. **Drop constant tokens.** A token identical in EVERY capture
   (`switch_3`, `vol_5`, an epoch count like `700epochs`, the amp/brand
   name, the plugin slug) is NOT a parameter — omit it (mention in
   `description` if useful).
4. **One axis per setting that VARIES** across captures.
5. **Classify each axis (knob vs enum) and format its values** — see
   next section.
6. **Map every capture** to `{axis: value, …}` from its filename.
7. **Validate** (checklist below) and run the gate.

## Knob vs enum — the value-type rule

| Axis is a… | When | Values |
|---|---|---|
| **KNOB** (continuous control swept across positions) | gain, drive, level, tone, treble, bass, mid, presence, master/mv, volume, depth, reverb, sustain, blend, contour, gate, sag — the filename gives a number | **NUMERIC**: `tone_25`→`25`, `g8`→`8`, `8_5`→`8.5`, clock `1_30`→`1.30`, `'5'`→`5`. OpenRig renders numeric values as a knob. |
| **ENUM** (discrete selector/switch) | channel, mic, voicing, model name, mode, pickup, rectifier, boost, speaker, position | short **STRING** label. A number inside a name (`sm57`, `ch1`, `bc109`, `hg_2`) is part of the name, NOT a knob position — keep it a string. |

Strip the amp/brand/plugin-id/epoch tokens from every value. Values:
short, lowercase, snake_case, distinct.

## Hard rules

- **Correlated knobs still get separate axes.** If `level` and `gain`
  always move together (only 3 combos exist), STILL expose both `level`
  and `gain`. A **sparse grid is valid** — missing cells are fine; only
  DUPLICATE cells (two captures with the same value combo) are forbidden
  (`pack_plugins`: "capture grid has duplicate entries").
- **No invented abstraction.** Never replace `level_25_gain_75` with
  `drive: high`. Expose `level` + `gain`.
- **No flat `model` of raw filenames.** A single `model` axis whose
  values are the raw capture names is the #1 defect.
- **A catch-all axis is the LAST resort.** Only when the filenames are a
  genuine grab-bag of named presets that do NOT decompose into settings
  (e.g. `cranked_norm`, `jumpered_sweet`, `v1_pulled` with no consistent
  grid). Then name it **`preset`** (not `model`), values clean.
- **Single capture** → omit the axis, or one axis with value `default`.
  Never an empty value (`- ` / `axis:`) — `pack_plugins` rejects it
  ("did not match any variant of untagged enum ParameterValue").
- **Mirror the sibling.** If an `_a1`/`_a2` twin exists and the captures
  correspond, reuse its axis names + values.

## Validate before the gate

- [ ] Every capture file appears exactly once; none dropped/added/renamed.
- [ ] For each capture, the values MATCH what the filename encodes
      (cross-check `tone_25` ⇒ `tone: 25`).
- [ ] Every capture lists every declared axis; every used value is in
      `parameters[].values`; all value-combos unique.
- [ ] Knobs numeric, enums string, no empty values.
- [ ] `cargo run --release --bin pack_plugins` → exit 0.

Cross-check script (READ-ONLY analysis — fine; a file-MUTATING transform
script is NOT, see below):

```bash
# every numeric token in the filename should equal the matching axis value
python3 - <<'PY'
import re,glob
for mp in glob.glob("plugins/source/nam/<plugin>/manifest.yaml"):
    man=open(mp).read()
    for blk in re.split(r'\n- values:', man.split('captures:')[1])[1:]:
        vals=dict(re.findall(r'(\w+):\s*([^\s,}]+)', blk.split('file:')[0]))
        fn=re.search(r'file:\s*\S+/(\S+)\.nam', blk).group(1)
        for ax,v in vals.items():
            if v.replace('.','').isdigit() and f"{ax}_{v}" not in fn.replace('.','_') and v not in re.findall(r'\d+', fn):
                print("CHECK", fn, ax, v)
PY
```

## Editing rule (LAW)

Edit manifests **one at a time, by hand** (`Read` + `Edit`/`Write`).
**NEVER** a transform script that batch-rewrites manifests — it always
breaks on edge cases (empty values, prefix collisions like
`low1/mid1/high1`→`1`, dropped files). A multi-agent workflow may
ANALYSE one plugin per agent, but each manifest EDIT is still a manual
per-file write.

## Anti-patterns (every one observed in production)

```
❌ parameters: [model: <33 raw filenames>]            → decompose by filename
❌ drive: [low, mid, high]  (file says level/gain)    → expose level + gain
❌ gain: ['3','5','7'] / [g6,g7] / [8_5]              → 3,5,7 / 6,7 / 8.5
❌ mic: [sm57→57]                                      → sm57 is a mic, keep string
❌ collapse correlated level+gain into one axis       → two axes, sparse grid
❌ value: '' (empty)                                   → default, or omit single-axis
❌ apply_params.py / knobify.py bulk transform         → per-file Read+Edit
```

## Worked example — EarthQuaker Plumes

Files: `plumes_switch_3_level_{100,50,25}_gain_{0,50,75}_tone_{0,25,50,75,100}`.
`switch_3` constant → omit. `level` & `gain` are locked (100/0, 50/50,
25/75) but BOTH exposed → sparse grid. `tone` independent.

```yaml
parameters:
- {name: level, display_name: Level, values: [25, 50, 100]}
- {name: gain,  display_name: Gain,  values: [0, 50, 75]}
- {name: tone,  display_name: Tone,  values: [0, 25, 50, 75, 100]}
captures:
- values: {level: 25, gain: 75, tone: 100}
  file: captures/plumes_switch_3_level_25_gain_75_tone_100.nam
# … one entry per file, values copied straight from the filename
```
