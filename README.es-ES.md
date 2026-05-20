# OpenRig-claude

Plugin de Claude Code que controla una instancia de [OpenRig](https://github.com/jpfaria/OpenRig)
en ejecución desde cualquier cliente AI compatible con MCP (Claude Code,
Claude Desktop, Cursor): arma timbres, ajusta la cadena, cambia presets —
llamando tools sobre la instancia viva.

> Otros idiomas: [English](README.md) · [Português](README.pt-BR.md)

## Qué contiene

- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` —
  manifiesto del plugin y entrada del marketplace.
- `.mcp.json` — declara el servidor MCP de OpenRig en
  `http://127.0.0.1:4123`. Instalar el plugin lo conecta automáticamente;
  no requiere configuración manual del cliente.
- `skills/openrig-tone-builder/SKILL.md` — skill de usuario final. Se
  activa cuando pides el timbre de una canción/artista: investiga la
  cadena de señal original, la mapea a bloques de OpenRig y la construye
  sobre la rig en ejecución, vía tools MCP.

## Instalación

### Claude Code

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Después, arranca OpenRig con el servidor MCP encendido:

```
openrig --mcp
```

El `.mcp.json` del plugin apunta el cliente a `http://127.0.0.1:4123`. El
cliente listará una tool por cada `Command` de OpenRig, los recursos
`openrig://project` / `openrig://devices` y los prompts.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL
`http://127.0.0.1:4123` (HTTP). Primero arranca OpenRig con
`openrig --mcp`.

## Precondición

OpenRig debe estar en ejecución con `--mcp` y el dispositivo de audio ya
debe estar tomado por esa instancia. Arrancar una segunda instancia
sobre el mismo dispositivo genera contención — apunta el agente a la
instancia que posee el dispositivo.

## Notas sobre el skill `openrig-tone-builder`

El skill referencia `docs/user-guide/blocks-reference.md` como la
**única** fuente para `MODEL_ID`s y parámetros. Ese archivo vive en el
repo de OpenRig. Por eso el skill asume que la sesión de Claude Code se
abre en un clon de [jpfaria/OpenRig](https://github.com/jpfaria/OpenRig)
para que la ruta relativa resuelva.

## Relación con OpenRig

Este repo guarda el control por IA de **usuario final** (plugin + skill +
ejemplo MCP). El repo OpenRig mantiene su propio `.claude/` solo con
skills de **desarrollador** (`openrig-code-quality`,
`rust-best-practices`, `slint-best-practices`), además de la
implementación del propio servidor MCP (`crates/adapter-mcp`).

## Licencia

Apache-2.0 — ver [LICENSE](LICENSE).
