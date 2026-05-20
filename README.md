# OpenRig-claude

Claude Code plugin that drives a running [OpenRig](https://github.com/jpfaria/OpenRig)
rig from any MCP-aware AI client (Claude Code, Claude Desktop, Cursor): build
tones, tweak the chain, switch presets — by calling tools on the live
instance.

> Other languages: [Português](README.pt-BR.md) · [Español](README.es-ES.md)

## What it bundles

- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` — plugin
  manifest and marketplace entry.
- `.mcp.json` — declares the OpenRig MCP server at
  `http://127.0.0.1:4123`. Installing the plugin auto-wires this; no manual
  client config.
- `skills/openrig-tone-builder/SKILL.md` — end-user skill. Triggers when you
  ask for an artist/song tone, researches the original signal chain, maps it
  to OpenRig blocks, and builds it on the running rig through MCP tools.

## Install

### Claude Code

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Then start OpenRig with the MCP server on:

```
openrig --mcp
```

The plugin's `.mcp.json` points the client at `http://127.0.0.1:4123`. The
client lists one tool per OpenRig `Command`, the `openrig://project` /
`openrig://devices` resources, and the prompts.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL
`http://127.0.0.1:4123` (HTTP). Start OpenRig with `openrig --mcp` first.

## Precondition

OpenRig must be running with `--mcp` and the audio device must already be
held by that instance. Running a second OpenRig instance on the same device
will contend — point the agent at the instance that owns the device.

## Notes for the `openrig-tone-builder` skill

The skill references `docs/user-guide/blocks-reference.md` as its **only**
catalog source for `MODEL_ID`s and parameters. That file lives in the
OpenRig repo. The skill assumes the Claude Code session is opened in a
clone of [jpfaria/OpenRig](https://github.com/jpfaria/OpenRig) so that
relative path resolves.

## Relation to OpenRig

This repo holds **end-user** AI control (plugin + skill + MCP example).
The OpenRig repo keeps its own `.claude/` with **developer** skills only
(`openrig-code-quality`, `rust-best-practices`, `slint-best-practices`),
plus the MCP server implementation itself (`crates/adapter-mcp`).

## License

Apache-2.0 — see [LICENSE](LICENSE).
