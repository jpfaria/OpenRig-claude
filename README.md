# OpenRig-claude

Claude Code plugin to drive a running [OpenRig](https://github.com/jpfaria/OpenRig) rig from any MCP-aware AI client (Claude Code, Claude Desktop, Cursor).

> Other languages: [Português](README.pt-BR.md) · [Español](README.es-ES.md)

## What it does (today)

For now, it knows how to **build tones**. One skill — `openrig-tone-builder` — ships with the plugin: ask for a tone ("timbre da Duality", "preset do Slipknot", "recreate the [song] sound"), and it researches the original signal chain, maps it to OpenRig blocks, and builds the chain on the **live** rig through MCP.

## Install

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Start OpenRig with the MCP server on:

```
openrig --mcp
```

The plugin's `.mcp.json` points the client at `http://127.0.0.1:4123` — no manual config.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Start OpenRig with `openrig --mcp` first.

## Update

```
/plugin update openrig@openrig
```

Or enable **auto-update** for the marketplace in the `/plugin` UI (Marketplaces tab → select `openrig` → Enable auto-update). The client refreshes on session start.

## License

Apache-2.0 — see [LICENSE](LICENSE).
