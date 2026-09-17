---
name: tone-builder
description: "Use when the user asks for a tone, timbre, or preset for a specific song or artist (\"timbre da Duality\", \"preset do Slipknot\", \"tom da [música]\", \"recreate the [song] sound\", \"build a [artist] preset\"). Researches the original signal chain in natural language, lets a deterministic tool resolve it to catalog gear, and saves it as a NAMED PRESET in the chain's bank — adding a NEW slot via `apply_rig_nav Preset(-1)`, never overwriting existing presets. ALWAYS asks the user once up front whether to commit via the live MCP rig or as a YAML file only."
---

# OpenRig tone builder → use the `tone-builder` plugin

A song's tone **with a record to measure against** is built by the **`tone-builder:tone-builder`**
skill (plugin `jpfaria/tone-builder`): research with opened pages, target = the record read at each
harmonic, one library note at a time, every choice under retention, `tone-builder build --device openrig`.
Load it and follow it. Not installed:

```
/plugin marketplace add jpfaria/tone-builder
/plugin install tone-builder@tone-builder
```

## What stays here

| case | do |
|---|---|
| record + separated guitar track | `tone-builder:tone-builder` |
| no reference at all (a genre tone, "som de blues") | [reference-less.md](reference-less.md): researched gear, flat EQ, no number |
| writing the resulting `preset.yaml` into the live rig | [persist.md](persist.md) (new slot, never overwrite), then `tone-builder verify --device openrig` |

## Never

| don't | because |
|---|---|
| `tone-analyzer compare`, `eq-match`, `proximity_pct`, `within`, `self_floor_pct` | obsolete: 1/3-octave bands on single notes fall 74–84 dB between harmonics, and the separated track deletes harmonics above ~H6 |
| `build_preset.py --ref` validation loop | same obsolete comparison; EQ without retention overfit on Gravity (fit 6.7 dB, test 8.3 → 13.5) |
| use the separated track as the tone target | it only locates notes; the record gives the level |
