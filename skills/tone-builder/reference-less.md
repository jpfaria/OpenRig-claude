# Reference-less build (no record to measure against)

Moved verbatim from the former SKILL.md. With a record, use the tone-builder plugin instead.

## ⛔ REFERENCE-LESS build — no WAV (or no render) → FLAT EQ, the gear carries the tone

Sometimes there is **no reference WAV** — the user asks for a GENERIC genre preset
("blues rhythm/lead", "a punk tone", "metal", "hard rock") with nothing to match — OR a
reference exists but **you cannot render** (no installed `openrig-render`, or a hook blocks
the dev-tree binary — Step 0b). The proximity loop, the EQ refine, and the `within` gate
**do not apply**: there is no number to optimise toward. That is NOT a licence to shape the
tone by ear.

> **A third entry is AUTOMATIC.** When a reference WAV *is* present and renderable but
> `build_preset` detects it is **degraded** (top-dead / low-mid fragment), the engine
> switches to this same flat-EQ, gear-driven treatment **itself** and reports
> **`mode: degraded-reference`** (not `reference-less`). Everything below — flat EQ,
> `output_db` 0, the ear-feedback procedure — applies identically. See "The
> degraded-reference trap".

> ⛔ **You have no ears. You NEVER author EQ band gains by ear, and you NEVER set
> `output_db`.** Hand-dialling a "genre EQ" is the documented failure of this session — it
> produced nasal, honky, unusable tones; the user confirmed that flattening the EQ to 0
> (and `output_db` to 0) is what made the presets usable. The researched **amp + drive +
> cab carry the tone**; the EQ stays **FLAT** (all band gains 0) and `output_db` stays **0**.

**The reference-less FORM:**
1. **Research + audit the gear exactly as usual** (Workflow Steps 1–2 — `gear-researcher`,
   then `research-auditor` PASS; Rule A, `resolve_gear` PINS the catalog ids). Gear choice
   is **unchanged**; that part works the same with or without a reference.
2. **Run `build_preset.py --research` WITHOUT `--ref`** (reference-less mode). It pins the
   gear, runs the validate + lint GATE, and emits the preset = pinned amp/drive/cab + a
   **FLAT `eq_eight_band_parametric`** (all band gains 0, `output_db` 0) + the FIXED FX.
   **NO proximity loop, NO EQ refine, NO render.** The report is marked
   `mode: reference-less`, `tunable: false`. (It still needs `--plugins-root` for
   `resolve_gear` to pin the gear — only `--ref`/`--render-bin`/`--di` are dropped.)
3. ⛔ **Do NOT author EQ band gains, do NOT set `output_db`.** The gear is the tone. Blind
   EQ is forbidden here exactly as everywhere else in this skill.
4. **State plainly to the user:** a reference-less preset is an **un-tunable STARTING
   POINT**. It can be refined ONLY by **(a)** the user providing a reference WAV → the
   normal proximity loop (THE FORM) then runs; OR **(b)** the user giving directional
   **ear** feedback (next section). Absent either, it stays exactly as built.

> "I built this from researched gear with a flat EQ — there was no reference to match, so I
> won't shape the EQ blind (I can't hear it). It's a solid starting point. Give me a
> reference WAV and I'll tune it to match, or tell me what's off by ear and I'll make ONE
> bounded move." *(render in the user's language at runtime — English documents structure)*

> **No invented genre EQ library.** Do NOT author a set of "canonical genre EQ targets" per
> session — inventing a genre curve IS the blind-EQ this section forbids (and a tone
> supposition the HARD RULES bar). A validated, *sourced* genre-curve library is a possible
> FUTURE item; until such curves are measured and cited, the EQ stays flat.

### Taking EAR feedback — the ONLY time you move a tone control by hand

The user's ear is the **only** override (the VALIDATION GATE rule, made concrete here). You
move a tone control by hand **only** on the user's **explicit directional word** — never on
your own verdict (you have none), never to "improve" a preset they have not complained
about. Map the complaint to ONE bounded, researched move, then STOP:

| User says | The ONE move you make |
|---|---|
| "too dark" / "too bright" | ONE gentle EQ shelf/band move, **≈ ±2–3 dB** on the relevant band, then stop. |
| "too much / too little gain or distortion" | change the **amp/drive gain-axis candidate** (a researched capture variant) or add/remove a **researched** drive — NOT blind EQ. |
| "too thin / boxy / no body" | try a different **researched** cab or amp candidate (or a small low-mid move, ≈ ±2–3 dB, on the explicit word). |

**NEVER move, ever:**
- **`output_db`** — stays **0**; a native dB control the user has no usable handle on, not
  a tone control.
- **the pinned amp model** — don't swap it unless the user **rejects the amp itself**.

**Absent a specific user complaint, you make NO tone move.** You do not invent one, do not
pre-emptively brighten/darken, do not "polish". One complaint → one bounded move → stop and
let them judge again.

