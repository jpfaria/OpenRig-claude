---
name: openrig-tone3000-fetch
description: "Use when the user asks to discover, search, or import IR/NAM packs from tone3000.com into OpenRig-plugins (\"novidades do tone3000\", \"latest tone3000 packs\", \"procura IR de Mesa Rectifier no tone3000\", \"import tone3000 <id>\", \"traz o pack <id>\"). Drives the Supabase API of tone3000.com directly via curl + writes the draft manifest, then hands off to the OpenRig-plugins dev-flow LAW (issue → .solvers/issue-N → qa_audit/pack_plugins gate → PR)."
---

# tone3000 fetch

Discover, search, and import IR / NAM packs from
[tone3000.com](https://www.tone3000.com) into a local checkout of
[OpenRig-plugins](https://github.com/jpfaria/OpenRig-plugins).

No native binary. The work is **curl** against the tone3000 Supabase
API (public anon JWT, no user account) plus **Write** for the draft
`manifest.yaml`. The `playwright` MCP that this plugin already wires
is a **fallback** for steps where the API surface is insufficient (rare).

## Iron rules

1. **NEVER touch the user's main OpenRig-plugins checkout.** Every
   import runs in a fresh `.solvers/issue-N/` **independent clone** per
   the OpenRig-plugins dev-flow LAW. `git worktree` is FORBIDDEN —
   worktrees share the parent `.git` (refs, index, hooks) and break the
   isolation guarantee; use a clone.
2. **The user picks the tone.** Even when listing "novidades", show
   the candidates and let the user choose; never import a guess.
3. **Inference misses become `# TODO:` YAML comments** in the
   generated manifest. The user must resolve them before running
   the gate. Do not silently fabricate parameter axes.
4. **Validation is `qa_audit` + `pack_plugins`, not your ear.**
   Asking the user "does it sound better now?" is forbidden — see
   the `openrig-code-quality` skill in OpenRig-plugins. The gate is
   the only acceptable acceptance signal.
5. **English everywhere** in the generated manifest (id, comments,
   commit messages) — repo LAW. Live chat stays in the user's
   language.

## Required inputs

Ask the user once per session, then remember:

- **`PLUGINS_REPO`** — absolute path to their OpenRig-plugins checkout
  (e.g. `/Users/<u>/Projetos/.../OpenRig-plugins`). If they don't have
  one, send them to
  `https://github.com/jpfaria/OpenRig-plugins` to clone it first.

## Tone3000 API surface (verified)

All endpoints public; auth is a single anon JWT embedded in the
tone3000 SPA (`role: anon`, project `gzybiuopxkdxbytnojds`, expires
2035-02-06):

```
TONE3000_ANON="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd6eWJpdW9weGtkeGJ5dG5vamRzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MzgwODIxNjUsImV4cCI6MjA1MzY1ODE2NX0.Gq66BJXjtLsqP2nAGXm9Xb9PAjoeZalWUj66K4nmVSU"
```

| Function | Method + URL |
|---|---|
| Search / list | `POST https://api.tone3000.com/rest/v1/rpc/search_tones_a2` with headers `apikey`, `Authorization: Bearer`, `content-profile: public`, `Content-Type: application/json`. Body: `{"query_term":"<q>","page_number":1,"page_size":<n>,"order_by":"newest","tag_names":null,"make_names":null,"gear_filters":null,"is_calibrated":false,"size_filters":null,"usernames":null}`. `order_by="newest"` for "latest"; set `query_term` for search; `gear_filters=["ir"]` etc. to filter. |
| Tone detail (description, license, links, images) | `GET https://api.tone3000.com/rest/v1/tones?id=eq.<id>&select=*` |
| Tone summary with **makes/tags/model_name/models_count** (NOT in `/tones`) | `POST /rpc/search_tones_a2` with `query_term=<first 2-3 words of the title>`, then pick the row matching `.id` client-side. |
| Models in tone | `GET https://api.tone3000.com/rest/v1/models?tone_id=eq.<id>&select=id,name,model_url,size,position,architecture_version,created_at` |
| Download (no headers) | `GET https://api.tone3000.com/storage/v1/object/public/models/<filename>` — public bucket, **no auth**. |

> ⚠ The `/rest/v1/tones` table does **not** expose `makes` or `tags` (they live in junction tables that PostgREST denies to `anon`). You MUST recover them via the search RPC.

If any call returns 401, the anon JWT may have rotated — open
`https://www.tone3000.com/` in the `playwright` MCP, grep the page
JS for an `eyJ…` JWT (`role:"anon"`), use that as `TONE3000_ANON`.

## Workflow

### Discover / search / show

For the user request, run the right curl and present a table with one
row per candidate. Always mark `imported` / `new` by scanning the
user's repo for the tone id in `sources:`.

**Latest 20:**

```bash
curl -sS -X POST \
  -H "apikey: $TONE3000_ANON" -H "Authorization: Bearer $TONE3000_ANON" \
  -H "Content-Type: application/json" -H "content-profile: public" \
  -d '{"query_term":"","page_number":1,"page_size":20,"order_by":"newest","tag_names":null,"make_names":null,"gear_filters":null,"is_calibrated":false,"size_filters":null,"usernames":null}' \
  "https://api.tone3000.com/rest/v1/rpc/search_tones_a2" \
  | jq -r '.[] | "\(.id)\t\(.platform)\t\(.gear)\t\(.title)"'
```

**Search "mesa rectifier", NAM only:**

```bash
curl -sS -X POST \
  -H "apikey: $TONE3000_ANON" -H "Authorization: Bearer $TONE3000_ANON" \
  -H "Content-Type: application/json" -H "content-profile: public" \
  -d '{"query_term":"mesa rectifier","page_number":1,"page_size":10,"order_by":"newest","tag_names":null,"make_names":null,"gear_filters":["amp"],"is_calibrated":false,"size_filters":null,"usernames":null}' \
  "https://api.tone3000.com/rest/v1/rpc/search_tones_a2" | jq -r '.[] | "\(.id)\t\(.title)"'
```

**Annotate local status** by grepping the user's repo:

```bash
grep -rl "tone3000.com/tones/<id>$" "$PLUGINS_REPO/plugins/source"
```

If any path is returned → status is `imported`; else `new`.

**Show a tone** — three calls, because `makes`/`tags` require the search RPC:

```bash
ID=<id>
# 1) description, license, links, images, title — from the table
curl -sS -H "apikey: $TONE3000_ANON" -H "Authorization: Bearer $TONE3000_ANON" \
  "https://api.tone3000.com/rest/v1/tones?id=eq.$ID&select=*" | jq '.[0]'
# 2) makes, tags, model_name, gear, platform — from the search RPC
TITLE_PREFIX="<first 2-3 words of the title from step 1>"
curl -sS -X POST \
  -H "apikey: $TONE3000_ANON" -H "Authorization: Bearer $TONE3000_ANON" \
  -H "Content-Type: application/json" -H "content-profile: public" \
  -d "{\"query_term\":\"$TITLE_PREFIX\",\"page_number\":1,\"page_size\":20,\"order_by\":\"newest\",\"tag_names\":null,\"make_names\":null,\"gear_filters\":null,\"is_calibrated\":false,\"size_filters\":null,\"usernames\":null}" \
  "https://api.tone3000.com/rest/v1/rpc/search_tones_a2" \
  | jq --argjson id "$ID" '.[] | select(.id == $id) | {makes, tags, gear, platform, model_name}'
# 3) the captures
curl -sS -H "apikey: $TONE3000_ANON" -H "Authorization: Bearer $TONE3000_ANON" \
  "https://api.tone3000.com/rest/v1/models?tone_id=eq.$ID&select=id,name,model_url,size,position,architecture_version,created_at" | jq
```

If step 2 returns nothing (older tone whose title prefix returns >20 newer matches first), retry with a longer `query_term` or increment `page_number`.

### Import (full flow)

#### 1 — Confirm intent

Print the tone title, gear, model count, and the chosen slug to the
user. Ask for confirmation before downloading. Imported once = one
issue + one PR in OpenRig-plugins.

#### 2 — Open OpenRig-plugins issue + isolated clone

```bash
cd "$PLUGINS_REPO"
ISSUE=$(gh issue create \
  --title "import tone3000 <id>: <pack title>" \
  --body "Source: https://www.tone3000.com/tones/<id>. Imported via openrig-tone3000-fetch skill (jpfaria/OpenRig-claude)." \
  | grep -oE '[0-9]+$')
mkdir -p .solvers
# Independent clone — NOT `git worktree` (worktrees share the parent
# .git and break isolation). Cleanup is `rm -rf` of the dir.
git clone . ".solvers/issue-$ISSUE"
cd ".solvers/issue-$ISSUE"
git remote set-url origin git@github.com:jpfaria/OpenRig-plugins.git
git fetch origin main && git reset --hard origin/main
git checkout -b "feature/issue-$ISSUE"
WORK="$PLUGINS_REPO/.solvers/issue-$ISSUE"
```

All file ops below happen under `$WORK`. **Never** under
`$PLUGINS_REPO/plugins/source/` directly.

#### 3 — Resolve `kind` and `slug`

- `kind` = `nam` if the first `model_url` ends with `.nam`, else `ir`.
- `slug` = `<brand>_<short-model>`, lowercased, non-alphanumerics → `_`, collapsed. Brand = first word of `makes[0]` from the tone detail, or first word of `title` if `makes` is empty.
- If `$WORK/plugins/source/$kind/$slug` exists, suffix `_2`, `_3`, …

#### 4 — Download captures

```bash
TARGET="$WORK/plugins/source/$kind/$slug"
SUBDIR=$([ "$kind" = "ir" ] && echo "ir" || echo "captures")
mkdir -p "$TARGET/$SUBDIR"
# For every model from /rest/v1/models?tone_id=eq.<id>:
curl -sS -o "$TARGET/$SUBDIR/$(basename "$MODEL_URL")" "$MODEL_URL"
```

The bucket URL is direct and unauthenticated. Reject any download
that yields HTTP ≠ 200 or 0 bytes — surface the failure, don't
continue silently.

#### 5 — Write `manifest.yaml`

Use `Write` to author `$TARGET/manifest.yaml` with this structure:

```yaml
manifest_version: 1
id: <kind>_<slug>
display_name: <tone title, trimmed>
brand: <lowercased first word of makes[0] or "unknown">
# When makes has > 1 element:
# TODO: brand guessed from makes=[<list>]; pick the right one
sources:
- https://www.tone3000.com/tones/<id>
type: <see mapping below>
backend: <ir | nam>
parameters:
- name: <axis>
  display_name: <Title Case>
  values:
  - <value 1>
  - <value 2>
captures:
- values:
    <axis 1>: <value>
    <axis 2>: <value>
  file: <subdir>/<filename>
```

**`type` mapping** (tone3000 `gear` → OpenRig `type`):
- `ir` + tags contain `bass` or `acoustic` → `body`; else `cab`.
- `amp` → `amp`.
- `pedal` + tags contain `delay`/`reverb`/`chorus`/`modulation` → `fx_pedal`; else `gain_pedal`.
- `full-rig`, `outboard` → emit a `# TODO: <gear> not directly representable; pick type manually` comment, leave the field blank for the user.

**Parameter axes are MANDATORY — never a flat `model` dump.** The
capture `name` (and filename) encodes the real settings; decompose it
into meaningful axes. **It is FORBIDDEN to emit a single `model` axis
whose values are the raw capture names** (e.g. `model:
fender_57customdeluxe_clean_in1_700epochs`) — that produces an unusable
OpenRig picker and is the #1 import defect (OpenRig-plugins issue #64:
226 plugins had to be redone).

How to apply:
- If the plugin already exists in another architecture (an `_a1`/`_a2`
  sibling), MIRROR that sibling's axis names + values where the captures
  correspond.
- Strip the amp/brand, the plugin-id/slug tokens, and training noise
  (`700epochs`, `1000epochs`, `di`, `on`) from every value. Values:
  short, lowercase, snake_case, distinct, meaningful (`clean`, `crunch`,
  `od`, `in1`, `sm57`, `vol3`, `bridged`).
- Use MULTIPLE axes when names factor cleanly (e.g. `gain` + `input`).
  A SINGLE axis is the last resort, only for genuinely non-factorable
  packs — and even then with CLEAN stripped values, never raw filenames.
- Single-capture plugin → value `default`. NEVER emit an empty value:
  `pack_plugins` rejects it with "did not match any variant of untagged
  enum ParameterValue".
- Validate before the gate: every capture file mapped exactly once;
  every captures value declared in `parameters[].values`; value combos
  unique.
- At catalogue scale this is a per-plugin inference job — drive it with
  a multi-agent workflow (one agent per plugin, fed the capture names +
  the sibling manifest), not a single prefix-strip heuristic.

Dictionary to seed token classification:

- mic: `sm57`, `sm7b`, `md421`, `re20`, `beta52`, `c414`, `r121`, `r10`, `m160`, `u87`
- position: `cap edge` → `cap_edge`, `cone edge` → `cone_edge`, `cap`, `cone`, `distant`, `12 inch`/`12in` → `12_inch`, `24in` → `24_inch`
- speaker: `upper`, `lower`
- voicing: `hgt`, `hg`, `normal`, `clean`, `crunch`, `lead`
- numeric axes (regex): `gain`, `mids`/`mid`, `bass`, `treble` followed by a digit — e.g. `5g`, `g5`, `mids 5`, `mids:5`

For each capture, classify; for the manifest's `parameters:` block, aggregate the distinct values seen per axis. **If a capture has no recognised tokens**, emit instead:

```yaml
- values:
  # TODO: could not infer parameter axes for "<capture name>"
  file: <subdir>/<filename>
```

**Do NOT write `output_gain_db`** — that is computed by
`loudness_audit` in OpenRig-plugins.

#### 6 — Hand off to the user

Print:

```
Imported to $TARGET.
Next steps (run inside $WORK):
  1) Open $TARGET/manifest.yaml; resolve every '# TODO:' line.
  2) cargo build --release -p loudness-audit --bin qa_audit
  3) cargo run --release --bin pack_plugins
  4) git add . && git commit -m "feat(plugins): import tone3000 <id> (#$ISSUE)"
  5) gh issue comment $ISSUE --body "Push <sha>: pack_plugins gate: <result>."
  6) git push -u origin feature/issue-$ISSUE; gh pr create --base main --head feature/issue-$ISSUE
```

The skill stops here. The user owns the gate, the manifest cleanup, and the PR.

## Anti-patterns

- ❌ A single `model` parameter axis whose values are raw capture filenames — infer real axes from the names (see step 5). This is the #1 import defect.
- ❌ An empty parameter value (`- ` / `model: `) — breaks `pack_plugins` (ParameterValue enum). Single-capture → `default`.
- ❌ `git worktree add` for `.solvers/issue-N` — use an independent clone (worktrees share the parent `.git`).
- ❌ Writing into `$PLUGINS_REPO/plugins/source/` directly (must be `$WORK/…`).
- ❌ Re-running import over an existing `$TARGET` — refuse, surface the conflict; the user picks a different slug or removes the old dir intentionally.
- ❌ Pushing with `# TODO` comments still in the manifest.
- ❌ `QA_AUDIT_SKIP=1` to silence a real `qa_audit` failure — never. That env var exists only for when the audit tool itself is broken, not to dodge a finding (OpenRig-plugins LAW).
- ❌ Asking "does it sound better now?" — sonic verification is `qa_audit` thresholds; ear-validation is a methodology defect.
- ❌ Importing more than one tone per PR.
- ❌ Portuguese (or any non-English) in the generated manifest, in the commit message, or in the issue/PR body. Only the live chat stays in the user's language.
- ❌ Inventing a tone id "based on what's similar" when search returns no exact match — surface "no match", let the user choose.

## Related

- Data repo: [`jpfaria/OpenRig-plugins`](https://github.com/jpfaria/OpenRig-plugins) — where the imported pack lands. Holds the `tools/loudness_audit` and `tools/pack_plugins` binaries that gate the import.
- Repo discipline: the `openrig-code-quality` skill in OpenRig-plugins (`.claude/skills/openrig-code-quality/SKILL.md`) — same dev-flow LAW.
- Sibling skill: [`openrig-tone-builder`](../openrig-tone-builder/SKILL.md) — builds presets on the live rig; does not write files.
