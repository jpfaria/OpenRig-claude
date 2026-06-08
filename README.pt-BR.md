# OpenRig-claude

Plugin do Claude Code que transforma qualquer cliente AI compatível com MCP (Claude Code, Claude Desktop, Cursor) num assistente de mãos livres para o [OpenRig](https://github.com/jpfaria/OpenRig) — o host de rig de guitarra open source para capturas NAM e respostas de impulso.

Descreva o timbre que você quer em linguagem natural e o plugin pesquisa, monta na sua rig **viva**, analisa o resultado e ainda faz crescer sua biblioteca de equipamentos — tudo pelo servidor MCP embutido do OpenRig.

> Outros idiomas: [English](README.md) · [Español](README.es-ES.md)

## O que é o OpenRig?

O [OpenRig](https://github.com/jpfaria/OpenRig) é um host de amp-sim / efeitos: você monta uma **chain** de **blocos** (capturas de amp, cabs/IRs, drives, modulação, efeitos de tempo), salva como **preset** e troca de preset ao vivo — opcionalmente pilotado por um controlador MIDI de chão. Os timbres vêm de **plugins**: pastas de capturas [Neural Amp Modeler](https://www.neuralampmodeler.com/) (`.nam`) e respostas de impulso `.wav` descritas por um `manifest.yaml`.

Este plugin ensina seu cliente AI a operar cada parte desse fluxo.

## O que este plugin faz

Ele traz **cinco skills** que cobrem o ciclo completo do OpenRig — da ideia ao timbre ao vivo até uma biblioteca de gear que cresce. Cada uma ativa sozinha quando você descreve a tarefa correspondente; você não as chama pelo nome.

### 🎸 Timbrar & validar

| Skill | O que faz | Diga algo como |
|-------|-----------|----------------|
| **openrig-tone-builder** | Pesquisa a cadeia de sinal original de uma música ou artista, mapeia para blocos do OpenRig e salva como um **novo preset nomeado** (nunca sobrescreve). Commita na rig viva via MCP, ou escreve um preset YAML — ele pergunta qual, uma vez. | *"timbre da Duality"*, *"recria o tom do Slipknot"*, *"monta um preset pra [música]"* |
| **openrig-tone-analyzer** | Função de análise pura: WAV entra → fingerprint JSON + PNGs de espectrograma saem. Lida com renders curtos e faixas de vários minutos (fingerprints por seção). Nunca toca na rig — é o que o tone-builder usa para *verificar* se um timbre bate com a referência. | *"analisa esse áudio"*, *"compara o som que saiu com a referência"*, *"fingerprint do som"* |

### 📦 Crescer a biblioteca de gear

| Skill | O que faz | Diga algo como |
|-------|-----------|----------------|
| **openrig-plugin-author** | Empacota suas capturas `.nam` e IRs `.wav` locais numa pasta de plugin do OpenRig, inferindo os eixos de parâmetro a partir dos nomes de arquivo e rascunhando um `manifest.yaml`. | *"gera plugin nam para esses arquivos"*, *"monta a pasta do plugin de IR"* |
| **openrig-tone3000-fetch** | Descobre, busca e importa packs de IR/NAM do [tone3000.com](https://tone3000.com) direto no `OpenRig-plugins`, e então repassa para o dev-flow do repo (issue → solver → gate de QA → PR). | *"novidades do tone3000"*, *"procura IR de Mesa Rectifier no tone3000"*, *"import tone3000 \<id\>"* |

### 🎛️ Controlar hardware

| Skill | O que faz | Diga algo como |
|-------|-----------|----------------|
| **openrig-midi-profile-builder** | Cria um profile MIDI para um controlador de chão que o OpenRig ainda não traz de fábrica, customiza um existente, ou converte uma captura de MIDI Monitor / `receivemidi` num profile YAML. | *"cria profile MIDI pro meu FCB1010"*, *"meu Morningstar MC8 não tem profile"*, *"converte este log do MIDI Monitor em profile"* |

### Como elas se encaixam

```
tone-builder ──pesquisa──▶ chain ──monta via MCP──▶ rig viva
     │                                                 │
     └──── tone-analyzer (verifica render vs. ref.) ◀──┘

plugin-author  ┐
               ├──▶ plugins do OpenRig (a biblioteca .nam / .wav de onde os timbres vêm)
tone3000-fetch ┘

midi-profile-builder ──▶ profile do controlador de chão para trocar preset ao vivo
```

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

### Requisitos

- **OpenRig** rodando com `--mcp` (para tudo que toca a rig viva).
- **Node.js** (`npx`) — para o browser Playwright usado na pesquisa de timbres.
- **Python 3.12+** — o `openrig-tone-analyzer` faz bootstrap de um virtualenv no primeiro uso (numpy, librosa, soundfile, matplotlib). Sem instalações globais.

### Claude Desktop

Settings → **Connectors** → Add custom connector → URL `http://127.0.0.1:4123` (HTTP). Suba o OpenRig com `openrig --mcp` primeiro.

## Atualização

```
/plugin update openrig@openrig
```

Ou habilite **auto-update** para o marketplace no painel `/plugin` (aba Marketplaces → selecione `openrig` → Enable auto-update). O cliente atualiza na inicialização da sessão.

## Licença

Apache-2.0 — veja [LICENSE](LICENSE).
