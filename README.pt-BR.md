# OpenRig-claude

Plugin do Claude Code para pilotar uma instância do [OpenRig](https://github.com/jpfaria/OpenRig) em execução a partir de qualquer cliente AI compatível com MCP (Claude Code, Claude Desktop, Cursor).

> Outros idiomas: [English](README.md) · [Español](README.es-ES.md)

## O que ele faz (hoje)

Por enquanto, ele sabe **timbrar**. Uma skill — `openrig-tone-builder` — vem com o plugin: peça um timbre ("timbre da Duality", "preset do Slipknot", "recreate the [song] sound") e ele pesquisa a cadeia de sinal original, mapeia para blocos do OpenRig e monta a chain na rig **viva** via MCP.

## Instalação

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Suba o OpenRig com o servidor MCP ligado:

```
openrig --mcp
```

O `.mcp.json` do plugin fia dois servidores MCP automaticamente — sem configuração manual:

- **`openrig`** em `http://127.0.0.1:4123` — a rig viva (commands, resources, prompts).
- **`playwright`** via `npx @playwright/mcp@latest` — browser headless para a skill de tone-builder raspar fontes JS-heavy (tonedb.co, groundguitar, killerrig, …) quando o `WebFetch` não dá conta. Precisa de Node.js (`npx`); a primeira execução baixa o Chromium (~300 MB em `~/.cache/ms-playwright/`).

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Suba o OpenRig com `openrig --mcp` primeiro.

## Atualização

```
/plugin update openrig@openrig
```

Ou habilite **auto-update** para o marketplace no painel `/plugin` (aba Marketplaces → selecione `openrig` → Enable auto-update). O cliente atualiza na inicialização da sessão.

## Licença

Apache-2.0 — veja [LICENSE](LICENSE).
