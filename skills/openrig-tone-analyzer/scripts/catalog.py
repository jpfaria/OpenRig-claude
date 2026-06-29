"""Deterministic, offline catalog index for OpenRig model ids.

Reads the on-disk OpenRig plugin manifests (under a `plugins_root`) plus a
committed list of NATIVE (non-plugin) model ids, and exposes a queryable index.
The point is anti-hallucination: later tools RESOLVE and VALIDATE every model id
and parameter against this index OFFLINE, so the agent never types a model id
from memory.

Two kinds of model id live here:

* PLUGIN ids — declared by a `manifest.yaml` under `plugins_root` (NAM amps/drives,
  IR cabs, ...). These carry a full offline param schema (the manifest's
  `parameters` axes). The catalog indexes the SOURCE manifest ids (with their
  arch suffix, e.g. `..._a2`) — those are what the render registers.
* NATIVE ids — built into the OpenRig app (Rust), enumerated in
  `native_models.yaml`. These are `is_known` but have NO offline param schema
  (`params(...)` is None); their params are validated best-effort downstream.

Public API (later tasks depend on these EXACT names):

    load_catalog(plugins_root, native_models_path) -> Catalog
    Catalog.is_known(model_id) -> bool
    Catalog.params(model_id)   -> dict | None
    Catalog.meta(model_id)     -> dict | None
    Catalog.find(query, type=None) -> list[Match]
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = ["Catalog", "Match", "load_catalog"]


@dataclass(frozen=True)
class Match:
    """A ranked search hit returned by `Catalog.find`."""

    model_id: str
    type: str | None
    brand: str | None
    display_name: str | None
    score: int


def _strip_accents(text: str) -> str:
    """Lower-case + drop combining marks, so `Ibáñez` -> `ibanez`."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.casefold()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Accent-stripped, case-folded alphanumeric tokens."""
    return _TOKEN_RE.findall(_strip_accents(text))


class Catalog:
    """Queryable index over plugin manifests + native model ids."""

    def __init__(self) -> None:
        # model_id -> {"type", "brand", "display_name", "backend", "params"}
        self._plugins: dict[str, dict] = {}
        # model_id -> {"type"}
        self._native: dict[str, dict] = {}
        # model_id -> set of search tokens (plugins only)
        self._search_tokens: dict[str, set[str]] = {}

    # -- construction ---------------------------------------------------------

    def _add_plugin(self, manifest: dict) -> None:
        model_id = manifest.get("id")
        if not model_id:
            return
        params: dict[str, list] = {}
        for axis in manifest.get("parameters") or []:
            name = axis.get("name")
            if name is None:
                continue
            params[name] = list(axis.get("values") or [])
        meta = {
            "type": manifest.get("type"),
            "brand": manifest.get("brand"),
            "display_name": manifest.get("display_name"),
            "backend": manifest.get("backend"),
            "params": params,
        }
        self._plugins[model_id] = meta
        haystack = " ".join(
            str(v)
            for v in (
                model_id,
                meta["display_name"],
                meta["brand"],
            )
            if v
        )
        self._search_tokens[model_id] = set(_tokenize(haystack))

    def _add_native(self, entry: dict) -> None:
        model_id = entry.get("id")
        if not model_id:
            return
        self._native[model_id] = {"type": entry.get("type")}

    # -- queries --------------------------------------------------------------

    def is_known(self, model_id: str) -> bool:
        return model_id in self._plugins or model_id in self._native

    def params(self, model_id: str) -> dict | None:
        """Manifest param axes for a plugin id; None for native/unknown ids."""
        plugin = self._plugins.get(model_id)
        if plugin is None:
            return None
        # return a copy so callers can't mutate the index
        return {k: list(v) for k, v in plugin["params"].items()}

    def meta(self, model_id: str) -> dict | None:
        """{type, brand, display_name, backend} for a plugin id.

        Native ids return their `type` with the other fields None (no manifest);
        unknown ids return None.
        """
        plugin = self._plugins.get(model_id)
        if plugin is not None:
            return {
                "type": plugin["type"],
                "brand": plugin["brand"],
                "display_name": plugin["display_name"],
                "backend": plugin["backend"],
            }
        native = self._native.get(model_id)
        if native is not None:
            return {
                "type": native["type"],
                "brand": None,
                "display_name": None,
                "backend": "native",
            }
        return None

    def find(self, query: str, type: str | None = None) -> list[Match]:
        """Rank plugin ids by how many query tokens they match.

        Matching is case- and accent-insensitive over `id + display_name + brand`.
        Score = number of DISTINCT query tokens found in the candidate's tokens,
        so a signature phrase (`dumble john mayer`) ranks the signature capture
        above a generic one of the same brand. `type` (e.g. `amp`) filters first.
        Deterministic: sorted by descending score, ties broken by model_id.
        """
        q_tokens = set(_tokenize(query))
        if not q_tokens:
            return []

        hits: list[Match] = []
        for model_id, plugin in self._plugins.items():
            if type is not None and plugin["type"] != type:
                continue
            score = len(q_tokens & self._search_tokens[model_id])
            if score == 0:
                continue
            hits.append(
                Match(
                    model_id=model_id,
                    type=plugin["type"],
                    brand=plugin["brand"],
                    display_name=plugin["display_name"],
                    score=score,
                )
            )

        hits.sort(key=lambda m: (-m.score, m.model_id))
        return hits


def load_catalog(plugins_root: str | Path, native_models_path: str | Path) -> Catalog:
    """Build a Catalog from a plugins tree + a native-model list.

    `plugins_root` is walked recursively for `manifest.yaml` files (so it works
    on both the OpenRig-plugins source tree and a fixture dir). `native_models_path`
    is a YAML list of `{id, type}`. Nothing is machine-tied: both come from args.
    """
    catalog = Catalog()

    root = Path(plugins_root)
    if root.is_dir():
        for manifest_path in sorted(root.rglob("manifest.yaml")):
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = yaml.safe_load(fh)
            if isinstance(manifest, dict):
                catalog._add_plugin(manifest)

    native_path = Path(native_models_path)
    if native_path.is_file():
        with native_path.open("r", encoding="utf-8") as fh:
            native = yaml.safe_load(fh)
        for entry in native or []:
            if isinstance(entry, dict):
                catalog._add_native(entry)

    return catalog
