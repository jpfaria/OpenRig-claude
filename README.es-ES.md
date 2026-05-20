# OpenRig-claude

Plugin de Claude Code para manejar una instancia de [OpenRig](https://github.com/jpfaria/OpenRig) en ejecución desde cualquier cliente AI compatible con MCP (Claude Code, Claude Desktop, Cursor).

> Otros idiomas: [English](README.md) · [Português](README.pt-BR.md)

## Qué hace (hoy)

Por ahora, sabe **armar timbres**. Una skill — `openrig-tone-builder` — viene con el plugin: pide un timbre ("timbre da Duality", "preset do Slipknot", "recreate the [song] sound") y la skill investiga la cadena de señal original, la mapea a bloques de OpenRig y arma la cadena sobre la rig **viva** vía MCP.

## Instalación

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Arranca OpenRig con el servidor MCP encendido:

```
openrig --mcp
```

El `.mcp.json` del plugin conecta dos servidores MCP automáticamente — sin configuración manual:

- **`openrig`** en `http://127.0.0.1:4123` — la rig viva (commands, resources, prompts).
- **`playwright`** vía `npx @playwright/mcp@latest` — navegador headless para que la skill de tone-builder rastree fuentes JS-heavy (tonedb.co, groundguitar, killerrig, …) cuando `WebFetch` no alcanza. Requiere Node.js (`npx`); la primera ejecución descarga Chromium (~300 MB en `~/.cache/ms-playwright/`).

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Arranca OpenRig con `openrig --mcp` primero.

## Actualización

```
/plugin update openrig@openrig
```

O habilita **auto-update** para el marketplace en el panel `/plugin` (pestaña Marketplaces → selecciona `openrig` → Enable auto-update). El cliente actualiza al iniciar la sesión.

## Licencia

Apache-2.0 — ver [LICENSE](LICENSE).
