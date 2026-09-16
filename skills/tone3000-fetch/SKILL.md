---
name: tone3000-fetch
description: "Use when the user asks to discover, search, or import IR/NAM packs from tone3000.com into OpenRig-plugins (\"novidades do tone3000\", \"latest tone3000 packs\", \"procura IR de Mesa Rectifier no tone3000\", \"import tone3000 <id>\", \"traz o pack <id>\"). Drives the Supabase API of tone3000.com directly via curl + writes the draft manifest into a caller-provided directory. API and draft manifest only — nothing else."
---

# tone3000 fetch

Discover, search, and import IR / NAM packs from
[tone3000.com](https://www.tone3000.com) as a draft
[OpenRig-plugins](https://github.com/jpfaria/OpenRig-plugins) manifest,
written into a directory the caller provides. The caller owns the
dev-flow (issue, clone, gate, PR) — this skill does not.

No native binary. The work is **curl** against the tone3000 Supabase
API (public anon JWT, no user account) plus **Write** for the draft
`manifest.yaml`. The `playwright` MCP that this plugin already wires
is a **fallback** for steps where the API surface is insufficient (rare).

## Iron rules

1. **NEVER write into the OpenRig-plugins working tree.** The skill
   writes the draft into a directory passed by the caller (`$SOURCE`);
   the caller owns where that directory lives (a clone, a `.solvers/`
   dir — not this skill's concern) and everything git-related.
2. **The user picks the tone.** Even when listing "novidades", show
   the candidates and let the user choose; never import a guess.
3. **Inference misses become `# TODO:` YAML comments** in the
   generated manifest. The user must resolve them before running
   the gate. Do not silently fabricate parameter axes.
4. **Never validate by ear.** Asking the user "does it sound better
   now?" is forbidden. The acceptance signal is the OpenRig-plugins
   gate, which the **caller** runs (see the `openrig-code-quality`
   skill in OpenRig-plugins) — not this skill.
5. **English everywhere** in the generated manifest (id, comments) —
   repo LAW. Live chat stays in the user's language.

## Required inputs

Ask the user once per session, then remember:

- **`$SOURCE`** — the caller-provided OpenRig-plugins `plugins/source`
  directory to write the draft pack into (e.g. a fresh clone at
  `/…/OpenRig-plugins/plugins/source`, or a `.solvers/issue-N/…` path the
  caller set up). The skill writes ONLY under `$SOURCE/<kind>/<slug>` and
  reads it to mark candidates `imported`/`new`. It never creates that
  directory's clone, branch, or issue — the caller owns all of that.

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
grep -rl "tone3000.com/tones/<id>$" "$SOURCE"
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

### Cab IR candidates — pre-filter BEFORE proposing an import

Most community cab IRs on tone3000 will **fail the OpenRig-plugins gate**
and are not worth an import issue. `tools/loudness_audit` enforces
`SPECTRAL_PEAK_CEILING_DB = 0.5` — after the audit normalises the IR, its
worst-case frequency-response peak must be ≤ 0.5 dB. Voiced/room-captured
IRs routinely show 15–27 dB peaks and get rejected. Screen candidates
first:

- **Size:** a clean cab IR is < 200 ms (≈ 30 KB at 48 kHz mono 24-bit).
  Anything > 1 s is cab+room and carries modes that spike the peak.
- **Prefer** titles tagged `Mix Ready` / `Calibrated` / `Flat` — these
  are usually spectrally flattened. **Avoid** intentionally voiced names
  (`Bright`, `Treble No Bass`, `Warm and Bassy`, `Cone Edge`, `Off Axis`):
  the name announces the violation.
- If no candidate passes these, the honest answer is **"no usable
  import"**, not lowering the threshold — the ceiling encodes a project
  invariant (a 15 dB narrow-band peak is an audible resonance defect).

NAM amp/pedal captures are not subject to this — it is a cab-IR concern.

### Import (full flow)

#### 1 — Confirm intent

Print the tone title, gear, model count, and the chosen slug to the
user. Ask for confirmation before downloading. One tone = one draft.

#### 2 — Destination

The caller provides the target path (`$SOURCE`); the skill writes there.
It never creates an issue, clone, or branch, and never touches anything
outside `$SOURCE`.

#### 3 — Resolve `kind` and `slug`

- `kind` = `nam` if the first `model_url` ends with `.nam`, else `ir`.
- `slug` = `<brand>_<short-model>`, lowercased, non-alphanumerics → `_`, collapsed. Brand = first word of `makes[0]` from the tone detail, or first word of `title` if `makes` is empty.
- Resolve the pack dir `TARGET="$SOURCE/$kind/$slug"`; if it exists, suffix `_2`, `_3`, … All writes below happen under `$TARGET` — nothing else is touched.

#### 4 — Download captures

**Always prefer the newest `architecture_version`.** A tone3000 NAM
capture is often re-trained on a newer NAM architecture and re-uploaded
as a *new* `models` row that sits **alongside** the old one — same
`name`, same `position`, same `size`, higher `architecture_version`.
Downloading every row would ship both the stale and the current capture.
So before downloading, collapse each capture group to a single winner:

- **Group key** = `(name, position, size)`. Rows that differ only by
  `architecture_version` are the *same* capture; rows that differ in
  `size` (`standard` / `lite` / `feather` / …) are distinct deliverables
  and are each kept.
- **Winner** = highest `architecture_version` in the group. Tie-break on
  newest `created_at`. `architecture_version` is treated numerically when
  it parses as a number, else lexically (then `created_at` decides).
- **Only NAM** (`kind = nam`) is versioned this way. For `kind = ir`,
  skip this step and download every row — IRs carry no architecture.

**A model with `model_url: null` is still TRAINING, not a failed
import — skip it, do not treat it as missing.** When `/models` returns a
row with `model_url: null` (usually `size: null`, `model_json: null`
too), the `.nam` does not exist yet: the uploader queued a training that
hasn't finished. Confirm with
`GET /rest/v1/trainings?id=eq.<training_id>&select=*` — `status_text:
"Task queued"` / `is_success: null` means not-yet-generated. Filter these
out before grouping (`jq 'map(select(.model_url != null))'`) and, when
deciding whether a local plugin is "incomplete" vs the remote tone,
**discount null-url models from the remote count** — they are not
downloadable. Revisit when the urls populate.
SUBDIR=$([ "$kind" = "ir" ] && echo "ir" || echo "captures")
mkdir -p "$TARGET/$SUBDIR"

# MODELS_JSON = the raw array from /rest/v1/models?tone_id=eq.<id>
if [ "$kind" = "nam" ]; then
  # keep only the newest architecture_version per (name, position, size)
  SELECTED=$(jq -c '
    group_by([.name, .position, .size])
    | map(sort_by([(.architecture_version|tonumber? // -1), .created_at]) | last)
  ' <<<"$MODELS_JSON")
else
  SELECTED="$MODELS_JSON"
fi

# Surface what was superseded — never drop silently (repo LAW).
DROPPED=$(jq -nr --argjson all "$MODELS_JSON" --argjson keep "$SELECTED" \
  '$all - $keep | .[] | "\(.name) pos=\(.position) size=\(.size) arch=\(.architecture_version) (\(.model_url|split("/")|last))"')
[ -n "$DROPPED" ] && printf 'Superseded by a newer architecture_version, NOT downloaded:\n%s\n' "$DROPPED"

# Download only the winners:
jq -r '.[].model_url' <<<"$SELECTED" | while read -r MODEL_URL; do
  curl -sS -o "$TARGET/$SUBDIR/$(basename "$MODEL_URL")" "$MODEL_URL"
done
```

The bucket URL is direct and unauthenticated. Reject any download
that yields HTTP ≠ 200 or 0 bytes — surface the failure, don't
continue silently. The `captures:` block of the manifest (step 5) maps
**only the downloaded winners** — never reference a superseded file.

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

**REQUIRED SUB-SKILL:** derive this block per `manifest-parameters`
(the canonical method). Summary below.

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
  the packer rejects it with "did not match any variant of untagged
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
- values: {}
  # TODO: could not infer parameter axes for "<capture name>"
  file: <subdir>/<filename>
```

**`values:` MUST parse as a map — write `values: {}`, never a bare
`values:`.** A bare `values:` followed by a comment (or nothing) is
`null` in YAML, and the OpenRig plugin-loader types the field as a map
(`BTreeMap<String, String>`), so it rejects the manifest with
`invalid type: unit value, expected a map` (the SPA logs
`plugin-loader: skipping package: invalid manifest.yaml`). The same
applies to any axis-less capture (`parameters: []`): the empty map is
`{}`, written explicitly.

**Do NOT write `output_gain_db`** — that is computed by
`loudness_audit` in OpenRig-plugins.

#### 6 — Hand off

Print:

```
Draft written to $TARGET. Resolve every '# TODO:' line in
$TARGET/manifest.yaml before the gate.
```

The skill stops here. The caller owns the rest of the dev-flow — the
manifest cleanup, the gate, and the PR (see the `openrig-code-quality`
skill in OpenRig-plugins).

## Anti-patterns

- ❌ A single `model` parameter axis whose values are raw capture filenames — infer real axes from the names (see step 5). This is the #1 import defect.
- ❌ An empty parameter value (`- ` / `model: `) — breaks the packer (ParameterValue enum). Single-capture → `default`.
- ❌ Writing anywhere outside `$TARGET` (the caller-provided destination).
- ❌ Re-running import over an existing `$TARGET` — refuse, surface the conflict; the user picks a different slug or removes the old dir intentionally.
- ❌ Presenting the draft as done while `# TODO:` comments still remain in the manifest — the caller resolves them before the gate.
- ❌ Asking "does it sound better now?" — ear-validation is a methodology defect; the OpenRig-plugins gate (run by the caller) is the acceptance signal.
- ❌ Bundling more than one tone per draft — one tone per import.
- ❌ Downloading every `models` row for a NAM tone when several share the same `(name, position, size)` and differ only by `architecture_version` — that ships a stale capture next to the current one. Keep only the highest `architecture_version` per group (step 4); IRs are exempt.
- ❌ Portuguese (or any non-English) in the generated manifest. Only the live chat stays in the user's language.
- ❌ Inventing a tone id "based on what's similar" when search returns no exact match — surface "no match", let the user choose.

## Related

- Data repo: [`jpfaria/OpenRig-plugins`](https://github.com/jpfaria/OpenRig-plugins) — where the imported pack lands. Holds the `tools/loudness_audit` and `tools/pack_plugins` binaries that gate the import.
- Repo discipline: the `openrig-code-quality` skill in OpenRig-plugins (`.claude/skills/openrig-code-quality/SKILL.md`) — same dev-flow LAW.
- Sibling skill: [`tone-builder`](../tone-builder/SKILL.md) — builds presets on the live rig; does not write files.
