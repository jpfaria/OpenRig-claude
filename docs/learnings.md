---
tags: [openrig-claude, learnings]
created: 2026-09-14
updated: 2026-09-16
source: claude-code-sessions
---

# OpenRig-claude — Learnings

## 2026-09-16 — plugin agents and skills live under the `openrig:` namespace

- **Gotcha / invariant:** the plugin is installed as `openrig@openrig`, so its agents and
  skills are addressed as `openrig:<name>` (e.g. `openrig:gear-researcher`,
  `openrig:tone3000-fetch`), never bare and never with the old `claude-plugin:` prefix.
- **Why it matters:** a reference with the wrong prefix points to nothing; the tone-builder
  shipped two such references until v1.2.1.
- **Applies to:** every cross-reference in `skills/*/SKILL.md` and `agents/*.md`, and the
  `tools:` allowlist in `agents/*.md` — plugin-scoped MCP tools are named
  `mcp__plugin_<plugin-name>_<server>__<tool>`, so they move with the plugin name too.

## 2026-09-16 — the plugin name is the namespace, so the skill name must not repeat it

- **Gotcha / invariant:** the plugin used to be named `claude-plugin` inside the `openrig`
  marketplace, so every skill carried an `openrig-` prefix to say which product it belonged
  to. Naming the plugin `openrig` makes the namespace carry that, and the prefix becomes
  noise: `openrig:tone-builder`, not `claude-plugin:openrig-tone-builder`. `claude-plugin`
  was also a real collision — `claude-plugin@xgodev` and `claude-plugin@carrefour` exist.
- **Why it matters:** renaming a plugin is a breaking change. Installs do not migrate:
  every user must `/plugin uninstall` the old id and `/plugin install` the new one, and
  every `.claude/settings.json` in every consuming repo names the plugin by the old id.
- **Applies to:** `.claude-plugin/plugin.json` + `marketplace.json`, and a sweep of every
  repo that references the plugin or its skills (v2.0.0 touched OpenRig, OpenRig-plugins,
  music-setup and tone-analyzer).

## 2026-09-14 — baseline runs for a reviewer agent must be a clean control

- **Gotcha / invariant:** baseline subagents started with the repo as cwd found and read
  `skills/tone-builder/SKILL.md` on their own, so they were not a no-guidance control.
  Forbid local file access in the baseline prompt; in production the auditor runs in the
  user's project, where that file is absent.
- **Why it matters:** a contaminated baseline makes the new agent look unnecessary.
- **Applies to:** RED phase of `superpowers:writing-skills` for any agent in `agents/`.

## 2026-09-14 — the planted defect must not be caught for the wrong reason

- **Gotcha / invariant:** when the cited page contradicts the planted block outright
  ("Reverb: None"), every baseline reviewer rejects it without applying the real rule.
  Use a fixture where the page mentions the effect but never names a unit (Gravity/John
  Mayer). Baselines then failed it for the wrong reason ("knobs not on the page"), treated
  cover-recommendation gear as evidence, and flagged valid cases (NAM `noise_gate.*` params,
  `cab: null` for a full amp).
- **Why it matters:** those wrong-reason failures are exactly what the auditor's
  instructions must fix; an easy fixture hides them.
- **Applies to:** `research-auditor` tests (8/8 correct with the agent, no false positives).

## 2026-09-14 — subagents cannot ask the user

- **Gotcha / invariant:** subagents have no `AskUserQuestion`. Anything that needs the user
  (MCP-or-YAML choice, ear feedback, saving to the rig) stays in the main conversation;
  agents only research, audit and return a conclusion.
- **Why it matters:** an agent that needs a user decision stalls or guesses.
- **Applies to:** splitting `openrig:tone-builder` phases into agents.

## 2026-09-14 — smoke-test agents in a real session

- **Gotcha / invariant:** reading an agent file into a generic subagent does not prove the
  plugin agent loads. Verify with a real `claude -p --plugin-dir <repo>` run that dispatches
  `openrig:<agent>` end to end (researcher writes the JSON, auditor audits it).
- **Why it matters:** frontmatter or naming errors only show up when the client loads the plugin.
- **Applies to:** every new or renamed agent.
