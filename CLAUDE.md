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

## Shipping a skill edit: edit source → commit → push, in one go (transversal)

When the user asks to **edit a skill** (or any committed file) in this repo, the unit of work **includes `git commit` + `git push origin main`** — do NOT stop after the edit to ask "want me to commit/push?". This repo's whole purpose is distribution: a skill edit that stays local is useless because it never reaches the installed plugin. The global "no unrequested shared-state actions" rule is **overridden here** — publishing the skill IS the requested work.

**Always edit the SOURCE repo, never the installed cache.** The OpenRig plugin source is `https://github.com/jpfaria/OpenRig-claude`; skills live at `skills/<name>/SKILL.md`. Edits under `~/.claude/plugins/cache/...` (or the marketplace clone at `~/.claude/plugins/marketplaces/openrig/`) are transient — they vanish on the next plugin update. A cache edit is at most a same-session stopgap; the PR/push to source is the deliverable.

**ALWAYS bump `.claude-plugin/plugin.json` yourself, with semver, in the same commit as the change — and push the tag.** There is no CI auto-bump (the `auto-bump.yml` workflow was removed on purpose). The version travels WITH the change, decided semantically by you — never blind, never deferred. The client gates `/plugin update` on both the `version` field and the matching `vX.Y.Z` git tag, so a change that ships without a bump + tag never reaches any install. The bump is part of the unit of work, exactly like `commit` + `push`.

**How to apply, every ship:**
1. Read the current `version` from `.claude-plugin/plugin.json`.
2. Choose the bump by **semver**, by the nature of the change:
   - **patch** (`0.1.x`) — bug fix, wording, doc, governance/infra, refactor that doesn't change a skill's user-facing behavior.
   - **minor** (`0.x.0`) — a new skill, or a new capability/behavior added to an existing skill.
   - **major** (`x.0.0`) — a breaking change to a skill's contract (renamed/removed skill, changed trigger or interface that can break existing user workflows).
3. Edit `version` to the new value **in the same commit** as the skill/file change (or, if you already committed, amend or add a follow-up commit before pushing — but never push the change without the bump).
4. Push the change, then the tag — **explicitly**: `git push origin main` && `git tag -a vX.Y.Z -m vX.Y.Z` && `git push origin vX.Y.Z`. Do NOT rely on `--follow-tags`: a lightweight `git tag vX.Y.Z` is silently skipped by it, so the tag never reaches the remote. Use an annotated tag (`-a`) and push the tag ref by name.
5. The work is **not "done"** until BOTH the bumped `version` AND the `vX.Y.Z` tag are on the remote — verify with `git ls-remote --tags origin | grep vX.Y.Z` before claiming done. (`--follow-tags` failing silently is the documented trap here.)

**Commit style:** `fix(<skill-short-name>): …` / `feat(<skill>): …` (match `git log`).

**Scope note:** this applies to `OpenRig-claude` only. The main OpenRig app repo (Rust/Slint) and OpenRig-plugins keep their standard gitflow — issue branches, PRs, gate, no auto-push to `main`/`develop`.
