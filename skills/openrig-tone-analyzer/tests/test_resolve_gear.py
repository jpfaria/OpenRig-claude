"""Tests for the catalog-backed gear resolver (scripts/resolve_gear.py).

resolve_gear is the core ANTI-HALLUCINATION tool: it turns the agent's RESEARCH
(natural-language gear, cited) into a catalog-backed base-chain YAML, PINNING the
exact/signature capture so the agent NEVER types a model id. Every model id (and
every `candidates:` id) it emits comes from the offline Catalog -- a slot with no
catalog backing goes to `unresolved`, never to a guessed id.

These tests depend ONLY on the hand-written Task-1 fixtures under
fixtures/catalog/ -- never on the real OpenRig-plugins tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import resolve_gear
from scripts.catalog import load_catalog
from scripts.resolve_gear import EQ_MODEL, resolve

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"
NATIVE = FIXTURES / "native_models.yaml"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(FIXTURES, NATIVE)


# --- helpers ------------------------------------------------------------------

def _blocks(out: dict) -> list[dict]:
    return out["chain"]["blocks"]


def _first(out: dict, block_type: str) -> dict | None:
    for b in _blocks(out):
        if b.get("type") == block_type:
            return b
    return None


def _assert_no_guessed_ids(out: dict, catalog) -> None:
    """Every emitted model id (pinned OR candidate) must be catalog-known -- the
    resolver never types an id from memory."""
    for b in _blocks(out):
        if b.get("model") is not None:
            assert catalog.is_known(b["model"]), f"unknown pinned id {b['model']!r}"
        for cid in b.get("candidates") or []:
            assert catalog.is_known(cid), f"unknown candidate id {cid!r}"


# --- amp: signature capture is PINNED (a fixed model, not candidates) ---------

def test_signature_amp_is_pinned_to_the_exact_capture(catalog):
    research = {
        "id": "gravity", "name": "Gravity",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer", "sources": ["interview"]},
        "drives": [], "cab": None, "fx": [],
    }
    out = resolve(research, catalog)
    amp = _first(out, "amp")
    assert amp is not None
    # PINNED: a single fixed model, the signature capture...
    assert amp["model"] == "nam_dumble_ods_john_mayer_a2"
    # ...NOT a candidates list of other amp models (no second-guessing the pin)
    assert "candidates" not in amp
    assert out["unresolved"] == []
    _assert_no_guessed_ids(out, catalog)


# --- drive: exact pin, emitted as a `gain` block ------------------------------

def test_drive_is_pinned_as_a_gain_block(catalog):
    research = {
        "id": "x", "name": "X", "amp": None,
        "drives": [{"name": "Ibanez TS808"}], "cab": None, "fx": [],
    }
    out = resolve(research, catalog)
    gain = _first(out, "gain")
    assert gain is not None
    # catalog type is `gain_pedal`; the EMITTED block type is `gain`
    assert gain["type"] == "gain"
    assert gain["model"] == "nam_ibanez_ts808_a2"
    assert "candidates" not in gain
    _assert_no_guessed_ids(out, catalog)


# --- cab: a `type: cab` PLUGIN block, never a raw generic_ir ------------------

def test_cab_is_pinned_as_cab_plugin_not_generic_ir(catalog):
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [],
        "cab": {"name": "Marshall 4x12 V30"}, "fx": [],
    }
    out = resolve(research, catalog)
    cab = _first(out, "cab")
    assert cab is not None
    assert cab["type"] == "cab"
    assert cab["model"] == "ir_marshall_4x12_v30"
    # NEVER an off-catalog raw-IR escape
    assert cab["model"] != "generic_ir"
    assert not any(b.get("model") == "generic_ir" for b in _blocks(out))
    _assert_no_guessed_ids(out, catalog)


# --- no catalog match: unresolved, NEVER a guessed id ------------------------

def test_amp_with_no_match_goes_unresolved_with_no_guessed_id(catalog):
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Fender Twin Reverb", "brand": "fender",
                "sources": ["wiki"]},
        "drives": [], "cab": None, "fx": [],
    }
    out = resolve(research, catalog)
    # no amp/preamp block was invented
    assert _first(out, "amp") is None
    assert _first(out, "preamp") is None
    # the unmatched amp is surfaced as unresolved, with the query and a reason
    amp_unres = [u for u in out["unresolved"] if u["slot"] == "amp"]
    assert len(amp_unres) == 1
    assert "fender" in amp_unres[0]["query"].lower()
    assert amp_unres[0]["reason"]
    # and absolutely no guessed id leaked anywhere in the chain
    _assert_no_guessed_ids(out, catalog)


# --- fx: a FIXED block carrying params + provenance, AFTER the EQ -------------

def test_fx_reverb_is_fixed_block_after_eq_with_params_and_provenance(catalog):
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [], "cab": None,
        "fx": [{"type": "reverb", "name": "spring", "params": {"mix": 14},
                "provenance": "unverified"}],
    }
    out = resolve(research, catalog)
    blocks = _blocks(out)
    rev = _first(out, "reverb")
    assert rev is not None
    # the researched FX params + provenance ride through verbatim
    assert rev["params"] == {"mix": 14}
    assert rev["provenance"] == "unverified"
    # the FX tail sits AFTER the EQ TUNE slot
    eq_idx = next(i for i, b in enumerate(blocks) if b.get("model") == EQ_MODEL)
    rev_idx = next(i for i, b in enumerate(blocks) if b.get("type") == "reverb")
    assert eq_idx < rev_idx
    # a by-type builtin we could not back with a catalog id never gets a GUESSED id
    _assert_no_guessed_ids(out, catalog)


# --- EQ TUNE slot present, flat; full signal order ----------------------------

def test_eq_tune_slot_is_present_and_flat_and_signal_order(catalog):
    research = {
        "id": "gravity", "name": "Gravity",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [{"name": "Ibanez TS808"}],
        "cab": {"name": "Marshall 4x12 V30"},
        "fx": [{"type": "reverb", "name": "spring", "params": {"mix": 14},
                "provenance": "unverified"}],
    }
    out = resolve(research, catalog)
    blocks = _blocks(out)

    eq = _first(out, "filter")
    assert eq is not None
    assert eq["model"] == EQ_MODEL
    # flat: no band gains baked in (build_preset lays the grid)
    assert eq["params"] == {}

    types = [b["type"] for b in blocks]
    assert types == ["gain", "amp", "cab", "filter", "reverb"]
    _assert_no_guessed_ids(out, catalog)


# --- empty drives => no gain block --------------------------------------------

def test_empty_drives_yields_no_gain_block(catalog):
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    out = resolve(research, catalog)
    assert _first(out, "gain") is None
    # the chain still has the pinned amp + the EQ
    assert _first(out, "amp")["model"] == "nam_dumble_ods_john_mayer_a2"
    assert _first(out, "filter")["model"] == EQ_MODEL


# --- chain id/name come from research ----------------------------------------

def test_chain_id_and_name_come_from_research(catalog):
    research = {"id": "duality", "name": "Duality (Slipknot)",
                "amp": None, "drives": [], "cab": None, "fx": []}
    out = resolve(research, catalog)
    assert out["chain"]["id"] == "duality"
    assert out["chain"]["name"] == "Duality (Slipknot)"


# --- fx with a catalog-KNOWN model is used as-is ------------------------------

def test_fx_with_known_model_is_used_verbatim(catalog):
    # compressor_studio_clean is a NATIVE known id (no plugin manifest)
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [], "cab": None,
        "fx": [{"type": "dynamics", "model": "compressor_studio_clean",
                "params": {"ratio": 4}, "provenance": "sourced"}],
    }
    out = resolve(research, catalog)
    dyn = _first(out, "dynamics")
    assert dyn["model"] == "compressor_studio_clean"
    assert dyn["params"] == {"ratio": 4}
    assert dyn["provenance"] == "sourced"
    assert out["unresolved"] == []


# --- fx that TYPES an unknown model id (no name fallback) => unresolved -------

def test_fx_with_unknown_typed_model_and_no_name_goes_unresolved(catalog):
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [], "cab": None,
        "fx": [{"type": "delay", "model": "nam_made_up_delay_x",
                "params": {"time_ms": 343}}],
    }
    out = resolve(research, catalog)
    # the typed-but-unbacked id is rejected, not trusted into the chain
    assert _first(out, "delay") is None
    fx_unres = [u for u in out["unresolved"] if u["slot"] == "fx"]
    assert len(fx_unres) == 1
    _assert_no_guessed_ids(out, catalog)


# --- fx: a by-type FX resolves to a NATIVE model, never a model-less block -----

def test_fx_reverb_spring_resolves_to_native_model(catalog):
    # `spring` is a native reverb id -- the catalog (now native-aware) resolves it,
    # so the reverb block carries a real model rather than being emitted model-less.
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [], "cab": None,
        "fx": [{"type": "reverb", "name": "spring", "params": {"mix": 14},
                "provenance": "unverified"}],
    }
    out = resolve(research, catalog)
    rev = _first(out, "reverb")
    assert rev is not None
    assert rev["model"] == "spring"          # the native id, NOT model-less
    assert rev["params"] == {"mix": 14}
    assert rev["provenance"] == "unverified"
    assert not any(u["slot"] == "fx" for u in out["unresolved"])
    _assert_no_guessed_ids(out, catalog)


def test_fx_matching_nothing_goes_unresolved_and_emits_no_modelless_block(catalog):
    # an fx whose name matches NOTHING (plugin or native) must go to `unresolved`;
    # it must NOT fall through to a FIXED block with no `model`.
    research = {
        "id": "x", "name": "X", "amp": None, "drives": [], "cab": None,
        "fx": [{"type": "reverb", "name": "zzz nonexistent gizmo xyz",
                "params": {"mix": 9}}],
    }
    out = resolve(research, catalog)
    assert _first(out, "reverb") is None
    fx_unres = [u for u in out["unresolved"] if u["slot"] == "fx"]
    assert len(fx_unres) == 1
    # no block anywhere lacks BOTH a model and candidates (i.e. no model-less block)
    for b in _blocks(out):
        assert b.get("model") or b.get("candidates"), f"model-less block: {b}"
    _assert_no_guessed_ids(out, catalog)


def test_no_resolved_block_ever_lacks_a_model(catalog):
    # a full chain: every pinned block (amp/drive/cab/eq/fx) carries a real model.
    research = {
        "id": "gravity", "name": "Gravity",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [{"name": "Ibanez TS808"}],
        "cab": {"name": "Marshall 4x12 V30"},
        "fx": [{"type": "reverb", "name": "spring", "params": {"mix": 14}},
               {"type": "delay", "name": "tape echo", "params": {"time_ms": 343}},
               {"type": "dynamics", "model": "compressor_studio_clean",
                "params": {"ratio": 4}}],
    }
    out = resolve(research, catalog)
    assert out["unresolved"] == []
    for b in _blocks(out):
        assert b.get("model") or b.get("candidates"), f"block without model: {b}"
    # the by-type FX both resolved to their native ids
    assert _first(out, "reverb")["model"] == "spring"
    assert _first(out, "delay")["model"] == "tape_echo"
    _assert_no_guessed_ids(out, catalog)


# --- standalone CLI: research JSON -> base-chain YAML --------------------------

def _write_research(tmp_path: Path, research: dict) -> Path:
    path = tmp_path / "research.json"
    path.write_text(json.dumps(research), encoding="utf-8")
    return path


def test_cli_resolvable_writes_chain_yaml_and_exits_zero(tmp_path: Path):
    research = {
        "id": "gravity", "name": "Gravity",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out = tmp_path / "base.yaml"
    rc = resolve_gear.main([
        "--research", str(rj),
        "--plugins-root", str(FIXTURES),
        "--native-models", str(NATIVE),
        "--out", str(out),
    ])
    assert rc == 0
    chain = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert chain["id"] == "gravity"
    amp = next(b for b in chain["blocks"] if b.get("type") == "amp")
    # the exact signature capture is PINNED -- the agent never typed this id
    assert amp["model"] == "nam_dumble_ods_john_mayer_a2"


def test_cli_defaults_native_models_relative_to_script(tmp_path: Path):
    # omitting --native-models resolves the shipped list next to resolve_gear.py
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out = tmp_path / "base.yaml"
    rc = resolve_gear.main([
        "--research", str(rj),
        "--plugins-root", str(FIXTURES),
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()


def test_cli_unresolvable_amp_exits_nonzero_and_writes_no_chain(tmp_path: Path, capsys):
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Fender Twin Reverb", "brand": "fender"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out = tmp_path / "base.yaml"
    rc = resolve_gear.main([
        "--research", str(rj),
        "--plugins-root", str(FIXTURES),
        "--native-models", str(NATIVE),
        "--out", str(out),
    ])
    assert rc != 0
    # no usable base chain is written -- the agent must fix research, never guess
    assert not out.exists()
    # the unresolved amp slot is reported on stderr
    err = capsys.readouterr().err.lower()
    assert "amp" in err
    assert "fender" in err
