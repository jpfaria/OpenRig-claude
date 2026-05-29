# OpenRig-claude — project conventions

## Persistence: skill / CLAUDE.md over local memory (transversal)

**NEVER persist user-requested changes to `~/.claude/projects/*/memory/`.** When the user corrects a behaviour, requests a new rule, or asks "remember this for next time", the change goes into **this repo** — the relevant `skills/<name>/SKILL.md`, this `CLAUDE.md`, or another committed file. Local memory is per-machine, per-user, and doesn't travel with the plugin.

**Why:** if a rule is worth remembering, it's worth shipping. Memory files at `~/.claude/.../memory/` only help one laptop; skills + this CLAUDE.md travel via `git`, ship to every install of the plugin, and are visible to every contributor and to the user across machines.

**How to apply:** when receiving a correction or new rule from the user, ask:

1. "Does this change how a skill should behave?" → edit the relevant `skills/<name>/SKILL.md`.
2. "Is this a cross-skill governance rule?" → edit this `CLAUDE.md`.
3. "Is this purely ambient context Claude derived on its own (user role, prior session)?" → local memory MAY be appropriate.

Cases (1) and (2) cover virtually every explicit user correction. Default to the project. When in doubt, the project wins.

## Language: skills and committed docs are written in English (transversal)

Every `skills/<name>/SKILL.md`, every script docstring, every committed `.md`, every commit message body — **English only**. The user converses in PT-BR with the agent; the agent renders user-facing chat messages in the user's language. But the skill *artefact* itself ships to every installer, in every locale, and is read by every contributor.

**Templates the agent renders to users** (e.g. menu prompts, ask-the-user phrasings) are also written in English inside the skill, with a note like "render in the user's language at runtime". The skill never hardcodes PT-BR templates — that locks the artefact to one locale and surfaces foreign words to non-PT users.

**Why:** the skill is a shared artefact. Mixing languages inside it makes it harder for future contributors to read, harder for English-locale users to follow, and inconsistent for any non-PT agent invocation. The agent's transient chat output is the right place for locale adaptation — not the durable skill text.

**How to apply:** before committing any edit to a `SKILL.md`, scan for PT-BR (or any non-English) phrases and either translate them to English or, if they're examples of what the agent should *say* to a user, wrap them as `<!-- render in user's language -->` examples with English commentary.
