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

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

__all__ = ["EQ_MODEL", "resolve", "main"]

_HERE = Path(__file__).resolve().parent
# The shipped native-model list, resolved relative to THIS file so the CLI is
# portable (no machine-tied path). Overridable with --native-models.
DEFAULT_NATIVE_MODELS = _HERE / "native_models.yaml"

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
            # `find` is native-aware, so a by-type FX (reverb/delay/...) resolves to
            # a NATIVE model id (e.g. `spring`) as readily as to a plugin id.
            hits = catalog.find(name, type=ftype)
            if hits:
                resolved = hits[0].model_id

        if resolved is None:
            # An fx MUST resolve to a real model (plugin OR native, via the
            # native-aware `find`, or an explicit known `model`). If nothing
            # resolves it goes to `unresolved` -- never a FIXED block with no
            # `model` (a model-less block is invalid and breaks validate).
            query = model if (model and not name) else (name or model)
            reason = (
                "fx model id is not in the catalog" if (model and not name)
                else "fx not found in the catalog"
            )
            unresolved.append({"slot": "fx", "query": query, "reason": reason})
            continue

        block: dict = {"type": ftype, "model": resolved, "enabled": True,
                       "params": params}
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


# --- standalone CLI ----------------------------------------------------------

def main(argv=None) -> int:
    """Turn a research JSON into a catalog-backed base-chain YAML.

    `resolve_gear.py --research <research.json> --plugins-root <dir>
       [--native-models <path>] [--out <base_chain.yaml>]`

    Loads the research JSON, builds the offline catalog (the native-model list
    defaults to the one shipped next to this script), and `resolve`s the research.
    The `chain` is written as YAML to `--out` (or stdout). Any `unresolved` slots
    are printed to stderr and make the exit code non-zero -- and NO base chain is
    written: the agent must fix the research, never guess a model id.
    """
    parser = argparse.ArgumentParser(
        description="Resolve a research JSON into a catalog-backed base-chain YAML."
    )
    parser.add_argument("--research", required=True, help="research JSON path")
    parser.add_argument("--plugins-root", required=True, help="plugin manifests root (or fixture dir)")
    parser.add_argument("--native-models", default=str(DEFAULT_NATIVE_MODELS),
                        help="native_models.yaml (defaults to the list shipped next to this script)")
    parser.add_argument("--out", default="", help="write the base-chain YAML here (default: stdout)")
    args = parser.parse_args(argv)

    # Imported here so the module imports without the catalog deps present; only
    # the CLI path needs the on-disk index.
    from scripts.catalog import load_catalog

    research = json.loads(Path(args.research).read_text(encoding="utf-8"))
    catalog = load_catalog(args.plugins_root, args.native_models)
    result = resolve(research, catalog)

    for u in result["unresolved"]:
        print(
            f"unresolved [{u.get('slot')}] {u.get('query')!r}: {u.get('reason')}",
            file=sys.stderr,
        )
    if result["unresolved"]:
        print(
            f"{len(result['unresolved'])} unresolved slot(s) -- fix the research; "
            "never guess a model id (no base chain written)",
            file=sys.stderr,
        )
        return 1

    chain_yaml = yaml.safe_dump(result["chain"], sort_keys=False, default_flow_style=False)
    if args.out:
        Path(args.out).write_text(chain_yaml, encoding="utf-8")
    else:
        sys.stdout.write(chain_yaml)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_HERE.parent))
    raise SystemExit(main())
