"""Offline anti-hallucination gate for a tone chain (Option A).

Given a chain dict (the `blocks:` list build_preset emits) and a `Catalog`
(catalog.py), HARD-FAIL on anything the catalog can't vouch for OFFLINE:

* an unknown `model` id -> ERROR (an invented id can never reach the render);
* a PLUGIN block (`catalog.params(model)` is a dict — NAM/IR, with manifest
  axes) whose `params` carry an undeclared param NAME or an off-axis VALUE
  -> ERROR. This is the `air=26`-on-a-plugin / wrong-amp-class bug.
* a forbidden block (`limiter_brickwall` model, or a `type: volume` block)
  -> ERROR. The engine strips these; authoring one is a bug.

NATIVE blocks (`is_known` true but `catalog.params(model)` is None) have NO
offline param schema, so their params are WARN-only — never an error. There is
no manifest to validate them against (Option A); they are checked best-effort
downstream by the live engine.

`validate(chain, catalog) -> {"ok": bool, "errors": [str], "warnings": [str]}`.
The CLI `main()` loads the chain (YAML/JSON) + builds the catalog from args,
prints every error and warning, and exits 1 if not ok, 0 if ok.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from scripts.catalog import Catalog, load_catalog

__all__ = ["validate", "main"]

# Blocks the chain must NEVER carry: a brickwall limiter or a volume block. They
# are stripped by the engine, so authoring one is a bug (mirrors build_preset).
FORBIDDEN_MODELS = {"limiter_brickwall"}
FORBIDDEN_TYPES = {"volume"}


def _values_equal(a: object, b: object) -> bool:
    """Equality that tolerates int/float spelling (8 == 8.0) for numeric axes,
    and falls back to plain equality for everything else (e.g. `mic: sm57`)."""
    if a == b:
        return True
    try:
        return float(a) == float(b)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _in_axis(value: object, allowed: list) -> bool:
    return any(_values_equal(value, a) for a in allowed)


def validate(chain: dict, catalog: Catalog) -> dict:
    """Validate every block of `chain` against `catalog`. See module docstring."""
    errors: list[str] = []
    warnings: list[str] = []

    for block in chain.get("blocks") or []:
        model = block.get("model")
        block_type = block.get("type")

        # 1. Forbidden blocks — never legal to author.
        if model in FORBIDDEN_MODELS:
            errors.append(f"forbidden model '{model}' (the engine strips it)")
            continue
        if block_type in FORBIDDEN_TYPES:
            errors.append(f"forbidden block type '{block_type}' (the engine strips it)")
            continue

        # 2. Unknown model id — an invented id can never reach the render.
        if not catalog.is_known(model):
            errors.append(f"unknown model id '{model}'")
            continue

        schema = catalog.params(model)
        params = block.get("params") or {}

        # 3a. NATIVE block — no offline schema, params are WARN-only.
        if schema is None:
            for name in params:
                warnings.append(
                    f"native param '{name}' on '{model}' not offline-validated"
                )
            continue

        # 3b. PLUGIN block — HARD-validate name + value against the manifest axes.
        for name, value in params.items():
            if name not in schema:
                allowed = ", ".join(str(k) for k in schema) or "(none)"
                errors.append(
                    f"param '{name}'='{value}' not valid for '{model}' "
                    f"(allowed: {allowed})"
                )
                continue
            axis = schema[name]
            if not _in_axis(value, axis):
                allowed = ", ".join(str(v) for v in axis)
                errors.append(
                    f"param '{name}'='{value}' not valid for '{model}' "
                    f"(allowed: {allowed})"
                )

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline anti-hallucination gate for a tone chain."
    )
    parser.add_argument("--chain", required=True, help="chain YAML/JSON file")
    parser.add_argument("--plugins-root", required=True, help="plugin manifests root")
    parser.add_argument("--native-models", required=True, help="native_models.yaml")
    args = parser.parse_args(argv)

    with Path(args.chain).open("r", encoding="utf-8") as fh:
        chain = yaml.safe_load(fh)
    if not isinstance(chain, dict):
        print("error: chain file is not a mapping")
        return 1

    catalog = load_catalog(args.plugins_root, args.native_models)
    result = validate(chain, catalog)

    for warning in result["warnings"]:
        print(f"warning: {warning}")
    for error in result["errors"]:
        print(f"error: {error}")

    if result["ok"]:
        print("ok: chain validated")
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
