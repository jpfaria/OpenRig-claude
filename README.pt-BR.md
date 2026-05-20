# OpenRig-claude

Plugin do Claude Code que pilota uma instância do [OpenRig](https://github.com/jpfaria/OpenRig)
em execução a partir de qualquer cliente AI compatível com MCP (Claude Code,
Claude Desktop, Cursor): monta timbres, ajusta a cadeia, troca presets —
chamando tools na instância viva.

> Outros idiomas: [English](README.md) · [Español](README.es-ES.md)

## O que vem dentro

- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` —
  manifesto do plugin e entrada do marketplace.
- `.mcp.json` — declara o servidor MCP do OpenRig em
  `http://127.0.0.1:4123`. Instalar o plugin já fia tudo; sem config
  manual no cliente.
- `skills/openrig-tone-builder/SKILL.md` — skill de usuário final.
  Dispara quando você pede o timbre de uma música/artista: pesquisa a
  cadeia original, mapeia para blocos do OpenRig e monta a cadeia na
  rig que está rodando, via tools MCP.

## Instalação

### Claude Code

```
/plugin marketplace add jpfaria/OpenRig-claude
/plugin install openrig@openrig
```

Em seguida, suba o OpenRig com o servidor MCP ligado:

```
openrig --mcp
```

O `.mcp.json` do plugin aponta o cliente para `http://127.0.0.1:4123`. O
cliente vai listar uma tool por `Command` do OpenRig, os recursos
`openrig://project` / `openrig://devices` e os prompts.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL
`http://127.0.0.1:4123` (HTTP). Suba o OpenRig com `openrig --mcp`
primeiro.

## Pré-condição

O OpenRig precisa estar rodando com `--mcp` e o dispositivo de áudio já
precisa estar tomado por essa instância. Subir uma segunda instância no
mesmo dispositivo gera contenção — aponte o agente para a instância que
detém o dispositivo.

## Notas sobre o skill `openrig-tone-builder`

O skill referencia `docs/user-guide/blocks-reference.md` como a **única**
fonte para `MODEL_ID`s e parâmetros. Esse arquivo mora no repo OpenRig.
Assim, o skill assume que o Claude Code está aberto num clone de
[jpfaria/OpenRig](https://github.com/jpfaria/OpenRig) para o caminho
relativo resolver.

## Relação com o OpenRig

Este repo guarda o controle por IA de **usuário final** (plugin + skill +
exemplo MCP). O repo OpenRig mantém o seu próprio `.claude/` apenas com
skills de **desenvolvedor** (`openrig-code-quality`,
`rust-best-practices`, `slint-best-practices`), além da implementação do
próprio servidor MCP (`crates/adapter-mcp`).

## Licença

Apache-2.0 — veja [LICENSE](LICENSE).
