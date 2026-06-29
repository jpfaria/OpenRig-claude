"""Enforce the tone POLICY as code — so the agent can't skip it in prose.

The tone-builder skill encodes several non-negotiable habits (research for the
time-domain FX, gate a noisy NAM chain, PIN an amp when an exact capture exists,
never author a limiter/volume the engine will strip). Stated as prose in a
SKILL.md they are easy to "forget". Here they are a function over the chain dict
plus the offline catalog, returning structured findings:

    lint(chain, catalog, research=None) -> list[Finding]

A Finding is a plain dict ``{"level", "code", "message"}`` where ``level`` is
``"block"`` (a hard policy violation — CLI exits 1) or ``"warn"`` (a near-certain
miss the author should justify). The CLI ``main()`` loads a chain JSON + the
catalog (plugins root + native list, both passed as args — nothing machine-tied)
and prints every finding.

The linter never mutates the chain and never touches the network. It reuses the
Task-1 ``scripts.catalog.Catalog`` (read-only) to answer the one question it
can't answer from the chain alone: does an exact capture for the researched amp
already exist?
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Strength threshold for "an exact/signature capture EXISTS for this amp": the
# top catalog hit must match at least this many DISTINCT query tokens. A single
# generic brand token (score 1) is NOT enough to call a multi-model contest a
# mistake; a signature query like "dumble ods john mayer" scores far higher.
_STRONG_MATCH_SCORE = 2

Finding = dict[str, str]


# --- block helpers ------------------------------------------------------------

def _blocks(chain: dict) -> list[dict]:
    blocks = chain.get("blocks") if isinstance(chain, dict) else None
    return [b for b in (blocks or []) if isinstance(b, dict)]


def _has_type(blocks: list[dict], block_type: str) -> bool:
    return any(b.get("type") == block_type for b in blocks)


def _candidate_model(candidate: Any) -> str | None:
    """The base model id of a `candidates:` entry (a bare string or a dict)."""
    if isinstance(candidate, str):
        return candidate
    if isinstance(candidate, dict):
        model = candidate.get("model")
        return model if isinstance(model, str) else None
    return None


def _distinct_candidate_models(block: dict) -> set[str]:
    """Distinct BASE model ids among a slot's candidates.

    The gain axis lives in each candidate's `params`, never in the model id, so
    candidates that differ only in their gain value share one `model` string and
    collapse here — that is how a single amp swept across gain is told apart from
    a genuine contest between 2+ different amp models.
    """
    models: set[str] = set()
    for cand in block.get("candidates") or []:
        model = _candidate_model(cand)
        if model:
            models.add(model)
    return models


# --- individual checks --------------------------------------------------------

def _check_zero_time_fx(blocks: list[dict]) -> list[Finding]:
    if _has_type(blocks, "reverb") or _has_type(blocks, "delay"):
        return []
    return [
        {
            "level": "warn",
            "code": "zero-time-fx",
            "message": (
                "no reverb and no delay — almost always a research miss; "
                "re-research or cite the part is dry"
            ),
        }
    ]


def _check_ungated_high_gain_nam(blocks: list[dict]) -> list[Finding]:
    has_nam_core = any(
        isinstance(b.get("model"), str)
        and b["model"].startswith("nam_")
        and b.get("type") in {"amp", "gain"}
        for b in blocks
    )
    if not has_nam_core:
        return []
    has_gate = any(
        b.get("type") == "dynamics"
        and isinstance(b.get("model"), str)
        and "gate" in b["model"]
        for b in blocks
    )
    if has_gate:
        return []
    return [
        {
            "level": "warn",
            "code": "ungated-high-gain-nam",
            "message": (
                "a NAM (often noisy) chain has no noise gate — add one if "
                "research or the measured noise floor calls for it"
            ),
        }
    ]


def _researched_amp_query(research: dict | None) -> str | None:
    if not isinstance(research, dict):
        return None
    amp = research.get("amp")
    if not isinstance(amp, dict):
        return None
    parts = [
        str(amp.get(key))
        for key in ("name", "brand", "signature")
        if amp.get(key)
    ]
    query = " ".join(parts).strip()
    return query or None


def _check_amp_not_pinned(blocks: list[dict], catalog, research: dict | None) -> list[Finding]:
    query = _researched_amp_query(research)
    if query is None:
        return []
    matches = catalog.find(query, type="amp")
    if not matches or matches[0].score < _STRONG_MATCH_SCORE:
        return []

    findings: list[Finding] = []
    for b in blocks:
        if b.get("type") not in {"amp", "preamp"}:
            continue
        if len(_distinct_candidate_models(b)) >= 2:
            findings.append(
                {
                    "level": "block",
                    "code": "amp-not-pinned",
                    "message": (
                        "an exact capture exists for the researched amp "
                        f"({matches[0].model_id}) — PIN it, don't run a "
                        "number-contest among amp models"
                    ),
                }
            )
    return findings


def _check_forbidden_block(blocks: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for b in blocks:
        if b.get("model") == "limiter_brickwall" or b.get("type") == "volume":
            findings.append(
                {
                    "level": "block",
                    "code": "forbidden-block",
                    "message": (
                        "the chain ends at the EQ; the engine strips "
                        "limiter/volume — do not author them"
                    ),
                }
            )
    return findings


# --- public API ---------------------------------------------------------------

def lint(chain: dict, catalog, research: dict | None = None) -> list[Finding]:
    """Return every policy finding for `chain`, given the offline `catalog`.

    `research` (optional) is the researched-gear dict; only `amp-not-pinned`
    consumes it, and only when an exact capture for the researched amp exists.
    """
    blocks = _blocks(chain)
    findings: list[Finding] = []
    findings += _check_zero_time_fx(blocks)
    findings += _check_ungated_high_gain_nam(blocks)
    findings += _check_amp_not_pinned(blocks, catalog, research)
    findings += _check_forbidden_block(blocks)
    return findings


# --- CLI ----------------------------------------------------------------------

def _format(finding: Finding) -> str:
    return f"[{finding['level']}] {finding['code']}: {finding['message']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a tone chain against the policy.")
    parser.add_argument("--chain", required=True, help="path to the chain JSON")
    parser.add_argument("--plugins-root", required=True, help="plugins tree (or fixture dir)")
    parser.add_argument("--native", required=True, help="native_models.yaml path")
    parser.add_argument("--research", default=None, help="optional researched-gear JSON path")
    args = parser.parse_args(argv)

    # Imported here so the module imports even if catalog deps are absent at
    # import time; the CLI is the only path that needs the index.
    from scripts.catalog import load_catalog

    chain = json.loads(Path(args.chain).read_text(encoding="utf-8"))
    research = None
    if args.research:
        research = json.loads(Path(args.research).read_text(encoding="utf-8"))
    catalog = load_catalog(args.plugins_root, args.native)

    findings = lint(chain, catalog, research=research)
    for finding in findings:
        print(_format(finding))

    blocked = any(f["level"] == "block" for f in findings)
    if not findings:
        print("ok: no policy findings")
    return 1 if blocked else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
