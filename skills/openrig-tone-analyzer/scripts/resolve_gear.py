#!/usr/bin/env python3
"""Catalog-backed gear resolver -- the core ANTI-HALLUCINATION tool.

The agent RESEARCHES the original signal chain in natural language (cited: an
amp, drive pedals, a cab, FX, with sources). This tool turns that research into a
catalog-backed **base-chain YAML** -- the exact shape `build_preset.py` consumes
-- by RESOLVING every gear name against the offline `Catalog` (catalog.py) and
PINNING the exact / signature capture. The agent NEVER types a model id: every
`model:` and every `candidates:` id emitted here comes from the catalog, and any
slot with no catalog backing goes to `unresolved` (never to a guessed id).

How each slot resolves (signal order: drives -> amp -> cab -> EQ -> fx):

* **amp** -- search the catalog (`amp` + `preamp`) for `name + brand + signature`.
  A signature/exact hit (>=2 distinct query tokens INCLUDING the brand, and a
  clear winner over the runner-up) is PINNED: a single fixed `model:` of the
  matched type -- NOT a `candidates:` list of other amps (no second-guessing the
  pin). A weak/family match or a near-tie emits `candidates:` of the top (<=3)
  documented stand-ins. No match at all -> `unresolved` (no invented id).
* **drives** -- each researched drive searches `gain_pedal`; pinned exact (a
  `gain` block) or `candidates:`; an empty `drives` list emits no gain block.
* **cab** -- searches `cab`; emits a `type: cab` PLUGIN block (catalog model id)
  whose manifest `output_gain_db` makes the level right -- NEVER a raw
  `generic_ir` wav. Absent -> omitted (the engine auto-inserts via `--cab-model`).
* **EQ** -- always one FLAT `eq_eight_band_parametric` filter (the TUNE slot
  build_preset trims), appended before the FX tail.
* **fx** -- each researched FX becomes a FIXED block carrying its `params:` and
  `provenance:`. A `model:` the catalog knows is used as-is; otherwise its `name`
  is searched. A FX that NAMES a builtin we cannot back with a catalog id is still
  placed (by type, no invented id); a FX that TYPES an unknown model id with no
  name fallback is rejected to `unresolved` (a typed id we cannot back is never
  trusted into the chain).

`resolve(research, catalog) -> {"chain": {id, name, blocks}, "unresolved": [...]}`.

PORTABLE BY CONSTRUCTION: the catalog is injected (built by the caller from a
plugins root + native-model list); this module ties to no machine path.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["EQ_MODEL", "resolve"]

# The one parametric EQ build_preset TUNES (a NATIVE id). Emitted FLAT here.
EQ_MODEL = "eq_eight_band_parametric"

# Catalog `type` we search each researched slot under. The EMITTED block type can
# differ: a drive is a `gain_pedal` capture in the catalog but a `gain` block in
# the chain.
CATALOG_AMP_TYPES = ("amp", "preamp")
CATALOG_DRIVE_TYPE = "gain_pedal"
CATALOG_CAB_TYPE = "cab"

BLOCK_GAIN = "gain"
BLOCK_CAB = "cab"
BLOCK_FILTER = "filter"

# A pin needs at least this many DISTINCT query tokens matched (one of which is
# the brand) AND a clear win over the runner-up -- otherwise it is a weak/family
# match and we offer `candidates:` instead of guessing one capture.
PIN_MIN_SCORE = 2
MAX_CANDIDATES = 3


# --- tokenization (mirrors catalog.py, kept local so this module is standalone) -

def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.casefold()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(_strip_accents(text or "")))


# --- search + pin/candidates/unresolved decision -----------------------------

def _find_amp(catalog, query: str) -> list:
    """Search amp + preamp captures and merge into one ranked list (deterministic
    by descending score, then model_id)."""
    merged: list = []
    for t in CATALOG_AMP_TYPES:
        merged.extend(catalog.find(query, type=t))
    merged.sort(key=lambda m: (-m.score, m.model_id))
    return merged


def _decide(matches: list, query_tokens: set[str]) -> tuple[str, object]:
    """Classify a ranked match list into a resolution decision.

    Returns one of:
      ("pin", match)          -- a signature/exact hit: a single fixed model;
      ("candidates", matches) -- a weak/family match or near-tie: top <=3 ids;
      ("unresolved", None)    -- nothing matched: never invent an id.
    """
    if not matches:
        return ("unresolved", None)
    top = matches[0]
    clear_winner = len(matches) == 1 or top.score > matches[1].score
    # "incl. brand": the matched capture's brand must appear in the query. A
    # brand-less catalog entry falls back to the score/clarity test alone.
    brand_ok = (not top.brand) or bool(_tokens(top.brand) & query_tokens)
    if top.score >= PIN_MIN_SCORE and clear_winner and brand_ok:
        return ("pin", top)
    return ("candidates", matches[:MAX_CANDIDATES])


# --- block builders ----------------------------------------------------------

def _pinned_block(block_type: str, model_id: str) -> dict:
    return {"type": block_type, "model": model_id, "enabled": True, "params": {}}


def _candidates_block(block_type: str, matches: list) -> dict:
    return {"type": block_type, "candidates": [m.model_id for m in matches],
            "enabled": True}


def _flat_eq_block() -> dict:
    # FLAT: no band params baked in -- build_preset lays the grid on the TUNE slot.
    return {"type": BLOCK_FILTER, "model": EQ_MODEL, "params": {}}


# --- the resolver ------------------------------------------------------------

def resolve(research: dict, catalog) -> dict:
    """Resolve the agent's cited research into a catalog-backed base chain.

    `research` is the agent's judgment (see module docstring / the FORM); `catalog`
    is an offline `Catalog`. Returns `{"chain": {id, name, blocks}, "unresolved":
    [{slot, query, reason}, ...]}`. Every emitted model id is catalog-known; an
    unresolvable slot is surfaced in `unresolved`, never guessed.
    """
    blocks: list[dict] = []
    unresolved: list[dict] = []

    # -- drives (signal order: first) ----------------------------------------
    for drive in research.get("drives") or []:
        query = " ".join(p for p in (drive.get("name"), drive.get("brand")) if p)
        decision, payload = _decide(
            catalog.find(query, type=CATALOG_DRIVE_TYPE), _tokens(query)
        )
        if decision == "pin":
            blocks.append(_pinned_block(BLOCK_GAIN, payload.model_id))
        elif decision == "candidates":
            blocks.append(_candidates_block(BLOCK_GAIN, payload))
        else:
            unresolved.append({"slot": "drive", "query": query,
                               "reason": "no catalog match for this drive pedal"})

    # -- amp / preamp --------------------------------------------------------
    amp = research.get("amp")
    if amp:
        query = " ".join(
            p for p in (amp.get("name"), amp.get("brand"), amp.get("signature")) if p
        )
        decision, payload = _decide(_find_amp(catalog, query), _tokens(query))
        if decision == "pin":
            block_type = (catalog.meta(payload.model_id) or {}).get("type") or "amp"
            blocks.append(_pinned_block(block_type, payload.model_id))
        elif decision == "candidates":
            block_type = (catalog.meta(payload[0].model_id) or {}).get("type") or "amp"
            blocks.append(_candidates_block(block_type, payload))
        else:
            unresolved.append({"slot": "amp", "query": query,
                               "reason": "no catalog amp/preamp match -- research "
                                         "a stand-in or add the capture"})

    # -- cab (a `type: cab` plugin, never a raw generic_ir) ------------------
    cab = research.get("cab")
    if cab and cab.get("name"):
        query = cab["name"]
        matches = catalog.find(query, type=CATALOG_CAB_TYPE)
        if matches:
            blocks.append(_pinned_block(BLOCK_CAB, matches[0].model_id))
        else:
            unresolved.append({"slot": "cab", "query": query,
                               "reason": "no catalog cab match"})

    # -- EQ TUNE slot (always present, flat, before the FX tail) -------------
    blocks.append(_flat_eq_block())

    # -- fx tail -------------------------------------------------------------
    for fx in research.get("fx") or []:
        ftype = fx.get("type")
        name = fx.get("name")
        model = fx.get("model")
        params = dict(fx.get("params") or {})
        provenance = fx.get("provenance")

        resolved = None
        if model and catalog.is_known(model):
            resolved = model
        elif name:
            hits = catalog.find(name, type=ftype)
            if hits:
                resolved = hits[0].model_id

        if resolved is None and model and not name:
            # the agent TYPED a model id the catalog cannot back and gave no name
            # to fall back on -- never trust a typed id we cannot verify.
            unresolved.append({"slot": "fx", "query": model,
                               "reason": "fx model id is not in the catalog"})
            continue
        if resolved is None and model and name:
            # typed id unknown AND the name did not resolve either -> unresolved.
            unresolved.append({"slot": "fx", "query": name or model,
                               "reason": "fx not found in the catalog"})
            continue

        block: dict = {"type": ftype, "enabled": True, "params": params}
        if resolved is not None:
            block["model"] = resolved
        # provenance rides through as a build-time helper key (build_preset reads
        # it; it is stripped from the final emitted preset). Default conservatively
        # to unverified so a sourceless FX never reads as sourced downstream.
        block["provenance"] = provenance if provenance is not None else "unverified"
        blocks.append(block)

    return {
        "chain": {
            "id": research.get("id"),
            "name": research.get("name"),
            "blocks": blocks,
        },
        "unresolved": unresolved,
    }
