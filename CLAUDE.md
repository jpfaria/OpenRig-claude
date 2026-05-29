# OpenRig-claude — project conventions

## Persistence: skill / CLAUDE.md over local memory (transversal)

**NEVER persist user-requested changes to `~/.claude/projects/*/memory/`.** When the user corrects a behaviour, requests a new rule, or asks "remember this for next time", the change goes into **this repo** — the relevant `skills/<name>/SKILL.md`, this `CLAUDE.md`, or another committed file. Local memory is per-machine, per-user, and doesn't travel with the plugin.

**Why:** if a rule is worth remembering, it's worth shipping. Memory files at `~/.claude/.../memory/` only help one laptop; skills + this CLAUDE.md travel via `git`, ship to every install of the plugin, and are visible to every contributor and to the user across machines.

**How to apply:** when receiving a correction or new rule from the user, ask:

1. "Does this change how a skill should behave?" → edit the relevant `skills/<name>/SKILL.md`.
2. "Is this a cross-skill governance rule?" → edit this `CLAUDE.md`.
3. "Is this purely ambient context Claude derived on its own (user role, prior session)?" → local memory MAY be appropriate.

Cases (1) and (2) cover virtually every explicit user correction. Default to the project. When in doubt, the project wins.
