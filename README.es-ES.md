# OpenRig-claude

Plugin de Claude Code que convierte cualquier cliente AI compatible con MCP (Claude Code, Claude Desktop, Cursor) en un asistente manos libres para [OpenRig](https://github.com/jpfaria/OpenRig) — el host de rig de guitarra open source para capturas NAM y respuestas de impulso.

Describe el timbre que quieres en lenguaje natural y el plugin lo investiga, lo arma sobre tu rig **viva**, analiza el resultado e incluso hace crecer tu biblioteca de equipos — todo a través del servidor MCP integrado de OpenRig.

> Otros idiomas: [English](README.md) · [Português](README.pt-BR.md)

## ¿Qué es OpenRig?

[OpenRig](https://github.com/jpfaria/OpenRig) es un host de amp-sim / efectos: armas una **cadena** de **bloques** (capturas de amp, cabs/IRs, drives, modulación, efectos de tiempo), la guardas como **preset** y cambias de preset en vivo — opcionalmente manejado por un controlador MIDI de piso. Los timbres vienen de **plugins**: carpetas de capturas [Neural Amp Modeler](https://www.neuralampmodeler.com/) (`.nam`) y respuestas de impulso `.wav` descritas por un `manifest.yaml`.

Este plugin le enseña a tu cliente AI a operar cada parte de ese flujo.

## Qué hace este plugin

Trae **cinco skills** que cubren el ciclo completo de OpenRig — de la idea al timbre en vivo hasta una biblioteca de equipos que crece. Cada una se activa sola cuando describes la tarea correspondiente; no las llamas por nombre.

### 🎸 Armar y validar timbres

| Skill | Qué hace | Di algo como |
|-------|----------|--------------|
| **openrig-tone-builder** | Investiga la cadena de señal original de una canción o artista, la mapea a bloques de OpenRig y la guarda como un **nuevo preset con nombre** (nunca sobrescribe). Aplica sobre la rig viva vía MCP, o escribe un preset YAML — pregunta cuál, una vez. | *"timbre da Duality"*, *"recrea el tono de Slipknot"*, *"arma un preset para [canción]"* |
| **openrig-tone-analyzer** | Función de análisis pura: WAV entra → fingerprint JSON + PNGs de espectrograma salen. Maneja renders cortos y pistas de varios minutos (fingerprints por sección). Nunca toca la rig — es lo que el tone-builder usa para *verificar* que un timbre coincide con la referencia. | *"analiza este audio"*, *"compara lo que salió con la referencia"*, *"fingerprint del sonido"* |

### 📦 Hacer crecer la biblioteca de equipos

| Skill | Qué hace | Di algo como |
|-------|----------|--------------|
| **openrig-plugin-author** | Empaqueta tus capturas `.nam` e IRs `.wav` locales en una carpeta de plugin de OpenRig, infiriendo los ejes de parámetro desde los nombres de archivo y redactando un `manifest.yaml`. | *"crea un plugin con estos .nam"*, *"arma la carpeta del plugin de IR"* |
| **openrig-tone3000-fetch** | Descubre, busca e importa packs de IR/NAM de [tone3000.com](https://tone3000.com) directo en `OpenRig-plugins`, y luego deriva al dev-flow del repo (issue → solver → gate de QA → PR). | *"novedades de tone3000"*, *"busca un IR de Mesa Rectifier en tone3000"*, *"import tone3000 \<id\>"* |

### 🎛️ Controlar hardware

| Skill | Qué hace | Di algo como |
|-------|----------|--------------|
| **openrig-midi-profile-builder** | Crea un profile MIDI para un controlador de piso que OpenRig aún no trae de fábrica, personaliza uno existente, o convierte una captura de MIDI Monitor / `receivemidi` en un profile YAML. | *"crea un profile MIDI para mi FCB1010"*, *"mi Morningstar MC8 no tiene profile"*, *"convierte este log de MIDI Monitor en profile"* |

### Cómo encajan

```
tone-builder ──investiga──▶ cadena ──arma vía MCP──▶ rig viva
     │                                                  │
     └──── tone-analyzer (verifica render vs. ref.) ◀───┘

plugin-author  ┐
               ├──▶ plugins de OpenRig (la biblioteca .nam / .wav de donde salen los timbres)
tone3000-fetch ┘

midi-profile-builder ──▶ profile del controlador de piso para cambiar preset en vivo
```

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

### Requisitos

- **OpenRig** corriendo con `--mcp` (para todo lo que toca la rig viva).
- **Node.js** (`npx`) — para el navegador Playwright usado en la investigación de timbres.
- **Python 3.12+** — `openrig-tone-analyzer` hace bootstrap de un virtualenv en el primer uso (numpy, librosa, soundfile, matplotlib). Sin instalaciones globales.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Arranca OpenRig con `openrig --mcp` primero.

## Actualización

```
/plugin update openrig@openrig
```

O habilita **auto-update** para el marketplace en el panel `/plugin` (pestaña Marketplaces → selecciona `openrig` → Enable auto-update). El cliente actualiza al iniciar la sesión.

## Licencia

Apache-2.0 — ver [LICENSE](LICENSE).
