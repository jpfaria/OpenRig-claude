# OpenRig-claude

Claude Code plugin that turns any MCP-aware AI client (Claude Code, Claude Desktop, Cursor) into a hands-free assistant for [OpenRig](https://github.com/jpfaria/OpenRig) — the open-source guitar rig host for NAM captures and impulse responses.

Describe the tone you want in plain language and the plugin researches it, builds it on your **live** rig, analyzes the result, and even grows your gear library — all through OpenRig's built-in MCP server.

> Other languages: [Português](README.pt-BR.md) · [Español](README.es-ES.md)

## What is OpenRig?

[OpenRig](https://github.com/jpfaria/OpenRig) is an amp-sim / effects host: you build a **chain** of **blocks** (amp captures, cabs/IRs, drives, modulation, time-based effects), save it as a **preset**, and switch presets live — optionally driven by a MIDI foot controller. Tones come from **plugins**: folders of [Neural Amp Modeler](https://www.neuralampmodeler.com/) (`.nam`) captures and `.wav` impulse responses described by a `manifest.yaml`.

This plugin teaches your AI client how to operate every part of that workflow.

## What this plugin does

It bundles **five skills** that span the full OpenRig lifecycle — from idea to live tone to a growing gear library. Each one activates automatically when you describe the matching task; you don't call them by name.

### 🎸 Build & validate tones

| Skill | What it does | Say something like |
|-------|--------------|--------------------|
| **openrig-tone-builder** | Researches the original signal chain of a song or artist, maps it to OpenRig blocks, and saves it as a **new named preset** (never overwrites). Commits to the live rig via MCP, or writes a YAML preset — it asks you which, once. | *"timbre da Duality"*, *"recreate the Slipknot tone"*, *"build a preset for [song]"* |
| **openrig-tone-analyzer** | Pure analysis function: WAV in → JSON fingerprint + spectrogram PNGs out. Handles short renders and multi-minute tracks (per-section fingerprints). Never touches the rig — it's what tone-builder uses to *verify* a tone matches the reference. | *"analyze this track"*, *"compare what came out with the reference"*, *"fingerprint this take"* |

### 📦 Grow your gear library

| Skill | What it does | Say something like |
|-------|--------------|--------------------|
| **openrig-plugin-author** | Packages your local `.nam` captures and `.wav` IRs into a proper OpenRig plugin folder, inferring parameter axes from filenames and drafting a `manifest.yaml`. | *"create a plugin from these .nam files"*, *"scaffold an IR plugin"* |
| **openrig-tone3000-fetch** | Discovers, searches, and imports IR/NAM packs from [tone3000.com](https://tone3000.com) straight into `OpenRig-plugins`, then hands off to the repo's dev-flow (issue → solver → QA gate → PR). | *"latest tone3000 packs"*, *"find a Mesa Rectifier IR on tone3000"*, *"import tone3000 \<id\>"* |

### 🎛️ Control hardware

| Skill | What it does | Say something like |
|-------|--------------|--------------------|
| **openrig-midi-profile-builder** | Authors a MIDI profile for a foot controller OpenRig doesn't ship yet, customizes an existing one, or converts a MIDI Monitor / `receivemidi` capture into a profile YAML. | *"build a MIDI profile for my FCB1010"*, *"my Morningstar MC8 has no profile"*, *"turn this MIDI log into a profile"* |

### How they fit together

```
tone-builder ──researches──▶ chain ──builds via MCP──▶ live rig
     │                                                    │
     └──── tone-analyzer (verify render vs. reference) ◀──┘

plugin-author  ┐
               ├──▶ OpenRig plugins (the .nam / .wav gear library tones draw from)
tone3000-fetch ┘

midi-profile-builder ──▶ foot-controller profile to switch presets live
```

## Install

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Start OpenRig with the MCP server on:

```
openrig --mcp
```

The plugin's `.mcp.json` wires two MCP servers automatically — no manual config:

- **`openrig`** at `http://127.0.0.1:4123` — the running rig (commands, resources, prompts).
- **`playwright`** via `npx @playwright/mcp@latest` — headless browser for the tone-builder skill to scrape JS-heavy gear sources (tonedb.co, groundguitar, killerrig, …) when `WebFetch` falls short. Requires Node.js (`npx`); first run downloads Chromium (~300 MB cached under `~/.cache/ms-playwright/`).

### Requirements

- **OpenRig** running with `--mcp` (for everything that touches the live rig).
- **Node.js** (`npx`) — for the Playwright browser used during tone research.
- **Python 3.12+** — `openrig-tone-analyzer` self-bootstraps a virtualenv on first use (numpy, librosa, soundfile, matplotlib). No global installs.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Start OpenRig with `openrig --mcp` first.

## Update

```
/plugin update openrig@openrig
```

Or enable **auto-update** for the marketplace in the `/plugin` UI (Marketplaces tab → select `openrig` → Enable auto-update). The client refreshes on session start.

## License

Apache-2.0 — see [LICENSE](LICENSE).
