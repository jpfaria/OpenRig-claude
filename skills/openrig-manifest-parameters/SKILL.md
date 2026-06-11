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

1. **List every capture filename AND read the tone3000 description.**
   `ls captures/` (NAM) or the IR dir; then fetch both
   `…/rest/v1/tones?id=eq.<id>&select=title,description` and
   `…/rest/v1/models?tone_id=eq.<id>&select=name,model_url`. **The filename is
   frequently opaque** (a storage hash) — the real settings live in the model
   `name` and the **description**, which often spells the dial positions out in
   words: *"File numbers = Presence, Bass, Middle, Treble, Volume I, Volume II"*,
   *"everything at 12 o'clock"* (= noon = 5), *"BCL_HG_2: Gain 5, Bass 7…"*.
   Decode from the filename **and** the description — reading the filename alone
   is the #1 cause of invented/metadata axes.
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

### A knob's value is always a NUMBER — decode the position

If an axis IS a real knob (gain/drive/tone/level/…), its values MUST be numeric
on the knob's own scale. Decode every position-as-word / clock / code into the
number — never ship `9_oclock`, `noon`, `max`, `900`, `8_5` as a knob value:

- **Clock face → number** on a 0–10 knob: `noon` / `12_oclock` = 5,
  `9_oclock` ≈ 2.5, `3_oclock` ≈ 7.5, fully clockwise = 10. ×100 / ×10 clock
  codes: `Tone900` = 9.0, `1030` (10:30) = 10.3, `p0900` = 9. Divide — do not
  keep the raw `900`.
- **`max` / `full`** = the knob's TOP for THAT pedal (read the range: TS808 drive
  0–10 ⇒ `max` = 10; a knob to 12 ⇒ `max` = 12). **`off` / `min`** = `0`.
  **Absent control** (the knob is not present on this capture/channel — e.g. an
  AC30 Normal channel has no Bass/Treble) = **`-1`** (a numeric sentinel, distinct
  from a real `0`). Never leave a literal word on a knob.
- **Concatenated digits**: `555` = 5 / 5 / 5 across three knobs in name order.
  **Underscore-decimal**: `8_5` = 8.5, `g4_5` = 4.5 (NOT 85 / 45).
- **Numbered hand-picked settings** (author shipped N configs that do NOT form a
  knob grid) → one `preset` axis numbered `1..N`, NOT four sparse EQ knobs.
- **Numeric values are PLAIN integers — never zero-padded** (`01`→`1`, `08`→`8`).
  Leading zeros hit the YAML octal trap: `08`/`09` are invalid octal and silently
  parse as **strings** while `01`–`07` parse as ints, producing a mixed-type axis
  that breaks the grid. Strip the padding so every value on the axis is the same
  numeric type.

**A knob axis NEVER holds a string.** When you find string values on a
knob-named axis (`gain`/`bass`/`treble`/`volume`/`mid`/`presence`/`master`/
`level`/`drive`/`tone`/`dist`/…), exactly one of two things is true:

1. **They are knob POSITIONS** → decode to numbers (per the rules above;
   qualitative `low`/`mid`/`high` = `3`/`5`/`8`, absent = `-1`).
   **ORDERED label positions are a KNOB.** If the values clearly RANK — an N-step
   sweep written `low1`/`low2`/`mid1`/`mid2`/`high1`/`high2`/`high3` (Marshall JVM:
   8 gain levels) or `lg`/`mg`/`hg` — they form ONE numeric knob: order them
   lowest→highest and number `1..N`, keep the knob name. Don't reflexively dump an
   ordered ramp into a `gain_stage` enum.
2. **They are a genuinely DISCRETE, UNORDERED selector — VOICINGS / CHANNELS /
   MODES / INPUTS / PEDALS** (`clean`/`crunch`/`od`, `in1`/`in2`,
   `standard`/`ultra_lo`/`ultra_hi`, pedal names) → **the axis is MISNAMED.**
   Rename it to the right enum (`voicing`/`channel`/`mode`/`input`/`gain_stage`/
   `pedal`); the string values stay (it is a selector, not a knob).

A genuine selector that already has the right name (`channel`, `mic`, `voicing`,
`mode`, a `boost` PEDAL selector, `off`/`on` switch) correctly keeps string
values — the rule is only that a control NAMED like a knob must be numeric.

## Hard rules

- **Correlated knobs still get separate axes.** If `level` and `gain`
  always move together (only 3 combos exist), STILL expose both `level`
  and `gain`. A **sparse grid is valid** — missing cells are fine; only
  DUPLICATE cells (two captures with the same value combo) are forbidden
  (`pack_plugins`: "capture grid has duplicate entries").
- **Every parameter NAME is a real control on the gear.** Use only names that
  exist on an amp/preamp/pedal — knobs/switches like `gain`, `drive`, `tone`,
  `level`, `treble`, `bass`, `mid`, `presence`, `master`, `volume`, `depth`,
  `reverb`, `channel`, `mic`, `voicing`, `mode`, `boost`, `bias`, `comp`,
  `blend`, `filter`, `contour`, `sag`, `transistor`, `voltage`, `feel`, `hf`,
  `load`, `aggression`, `solo`, `tubes`… For **IR** plugins (cabs AND
  acoustic-guitar bodies) use a real mic-ing / version axis: `mic`, `position`,
  `distance`, `version`, `flavor`, `pickup`. **FORBIDDEN as a name:** NAM
  training/capture metadata (`epochs`, `train`, `capture`, `buffer`, `nam_size`,
  `take`, `arch`, `block`, `module`) and invented abstractions (`model`, `size`,
  `variant`, `setting`, `version`/`flavor` on an amp). If you reached for one of
  these, you did NOT decode the real control — go back to the filename and the
  description.
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
