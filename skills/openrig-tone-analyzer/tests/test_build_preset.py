"""Tests for the offline single-tone preset builder (scripts/build_preset.py).

build_preset is the deterministic "FORM" of the openrig-tone-builder skill as
ONE portable tool: measure the reference once, search amp x drive (+ a cab ONLY
when the chosen CORE is a `type: preamp`) for the best spectral proximity, refine
the 8-band EQ with a CAPPED (+/-6 dB) trim that HOLDS the dead-top / out-of-range
bands at 0, set the headroom, and write a flat preset whose chain ENDS AT THE
EQ -- no limiter, no volume.

The cab rule is a pure CATALOG-TYPE check: a `type: preamp` capture (preamp, no
power amp/speaker) needs a cab; a `type: amp` capture is a FULL amp -- a combo
(speaker baked in) OR a head+cab mic'd -- and is NEVER cabbed; a `type: body`
(acoustic) and a `:full_rig` are never cabbed either. There is NO top-octave /
"direct" heuristic and NO render-to-measure for the cab decision -- the type
decides.

The pure layer (chain assembly, EQ grid, +/-6 cap, hold-mask, headroom
normalisation, YAML round-trip, type-driven cab decision) is tested directly.
The gear search and the EQ-refine loop are tested with injected fake
render/measurement callables that simulate gear ranking and convergence -- no
Rust binary, no real WAVs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common  # noqa: E402
from scripts import build_preset as bp  # noqa: E402


GRID = [80, 160, 320, 640, 1280, 2560, 5120, 10240]
FINE = list(_common.THIRD_OCTAVE_CENTERS_HZ)

# Hand-written catalog fixtures (the SAME ones the catalog/validate/lint tests
# use): nam_dumble_ods_john_mayer_a2 (amp, gain axis [2,5,8,10]), nam_dumble_a2,
# ir_marshall_4x12_v30 (cab), nam_ibanez_ts808_a2 (gain). The native list the
# gate resolves relative to build_preset.py ships eq_eight_band_parametric, etc.
FIXTURES_CATALOG = _HERE / "fixtures" / "catalog"


# --- block builders & chain assembly ---------------------------------------

def test_drive_block_is_a_gain_block():
    b = bp.drive_block("nam_tubescreamer_a1")
    assert b["type"] == "gain"
    assert b["model"] == "nam_tubescreamer_a1"
    assert b["enabled"] is True


def test_amp_block_defaults_to_type_amp():
    b = bp.amp_block("nam_jcm800_a1")
    assert b["type"] == "amp"
    assert b["model"] == "nam_jcm800_a1"


def test_amp_block_full_rig_type():
    b = bp.amp_block("nam_rig_a1", block_type="full_rig")
    assert b["type"] == "full_rig"


def test_cab_block_is_a_cab_plugin_block():
    # the auto-insert cab is a `type: cab` PLUGIN block referencing a catalog cab
    # model id -> the render loads the plugin and applies its per-capture
    # output_gain_db, so the level is correct. It is NOT a raw generic_ir wav.
    b = bp.cab_block("ir_marshall_4x12_v30")
    assert b["type"] == "cab"
    assert b["model"] == "ir_marshall_4x12_v30"
    assert b["enabled"] is True
    assert b["params"] == {}


def test_generic_ir_block_is_off_catalog_raw_wav_escape():
    # the OFF-CATALOG escape: a RAW IR wav through the generic_ir loader
    # (params.file). It bypasses any catalog output_gain_db -> ONLY for a
    # genuinely off-catalog IR, NEVER a stand-in for a catalog cab.
    b = bp.generic_ir_block("/abs/cab4x12.wav")
    assert b["type"] == "ir"
    assert b["model"] == "generic_ir"
    # the param key that points generic_ir at a wav is "file" (verified against
    # crates/block-ir/src/ir_generic_ir.rs in the OpenRig source).
    assert b["params"]["file"] == "/abs/cab4x12.wav"


def test_assemble_blocks_drive_amp_cab_eq_in_order():
    blocks = bp.assemble_blocks(["nam_od_a1"], "nam_amp_a1", amp_type="amp",
                                cab_model="ir_marshall_4x12_v30")
    types = [b["type"] for b in blocks]
    assert types == ["gain", "amp", "cab", "filter"]
    # chain ENDS at the EQ filter
    assert blocks[-1]["model"] == bp.EQ_MODEL


def test_assemble_blocks_none_drive_is_omitted():
    blocks = bp.assemble_blocks(["none"], "nam_amp_a1", cab_model=None)
    types = [b["type"] for b in blocks]
    assert "gain" not in types
    assert types == ["amp", "filter"]


def test_assemble_blocks_stacks_multiple_drives_in_order():
    blocks = bp.assemble_blocks(["a", "b"], "amp1", cab_model=None)
    gains = [b["model"] for b in blocks if b["type"] == "gain"]
    assert gains == ["a", "b"]


def test_assemble_blocks_full_rig_never_gets_a_cab():
    blocks = bp.assemble_blocks([], "nam_rig_a1", amp_type="full_rig",
                                cab_model="ir_marshall_4x12_v30")
    types = [b["type"] for b in blocks]
    assert "cab" not in types         # full_rig already has the cab
    assert "ir" not in types
    assert types == ["full_rig", "filter"]


def test_assemble_blocks_direct_amp_gets_a_cab_plugin_not_generic_ir():
    blocks = bp.assemble_blocks([], "nam_amp_a1", amp_type="amp",
                                cab_model="ir_marshall_4x12_v30")
    # the auto-inserted cab is a `type: cab` plugin block (applies output_gain_db)
    assert any(b["type"] == "cab" and b["model"] == "ir_marshall_4x12_v30"
               for b in blocks)
    # and NEVER a raw generic_ir wav (that would skip the catalog normalization)
    assert not any(b.get("model") == "generic_ir" for b in blocks)


def test_chain_has_no_limiter_and_no_volume_block():
    blocks = bp.assemble_blocks(["od"], "amp1", cab_model="ir_marshall_4x12_v30")
    models = [b.get("model") for b in blocks]
    types = [b["type"] for b in blocks]
    assert "limiter_brickwall" not in models
    assert "volume" not in types
    # nothing after the EQ
    assert blocks[-1]["model"] == bp.EQ_MODEL


def test_make_preset_shape():
    blocks = bp.assemble_blocks([], "amp1", cab_model=None)
    p = bp.make_preset("slug", "Display Name", blocks)
    assert p["id"] == "slug"
    assert p["name"] == "Display Name"
    assert p["blocks"] is blocks


# --- candidate-token parsing -----------------------------------------------

def test_parse_candidate_plain_model():
    # a bare-string candidate carries NO per-candidate params (default render)
    assert bp.parse_candidate("nam_jcm800_a2") == ("nam_jcm800_a2", False, {})


def test_parse_candidate_none_token():
    assert bp.parse_candidate("none") == ("none", False, {})


def test_parse_candidate_full_rig_suffix():
    # a ':full_rig' candidate declares a capture that already has the cab
    assert bp.parse_candidate("nam_rig_a2:full_rig") == ("nam_rig_a2", True, {})


def test_parse_candidate_dict_with_params():
    # a mapping candidate carries per-candidate params (a capture's own axis)
    assert bp.parse_candidate({"model": "nam_marshall_1959_slp_a2", "params": {"gain": 8}}) == (
        "nam_marshall_1959_slp_a2", False, {"gain": 8})


def test_parse_candidate_dict_full_rig_true_equals_suffix():
    # `full_rig: true` on a mapping is equivalent to the ':full_rig' suffix
    assert bp.parse_candidate({"model": "nam_rig_a2", "full_rig": True}) == ("nam_rig_a2", True, {})


def test_parse_candidate_dict_without_params_is_empty():
    assert bp.parse_candidate({"model": "nam_amp_a1"}) == ("nam_amp_a1", False, {})


# --- EQ grid / gains / cap -------------------------------------------------

def _preset_with_eq() -> dict:
    blocks = bp.assemble_blocks([], "amp1", cab_model=None)
    return bp.make_preset("demo", "Demo", blocks)


def test_set_eq_grid_places_bands_flat_on_the_grid():
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    eq = bp.eq_block(p)["params"]
    assert eq["band1_type"] == "high_pass"
    assert eq["band8_type"] == "high_shelf"
    for i, f in enumerate(GRID, start=1):
        assert eq[f"band{i}_freq"] == float(f)
        assert eq[f"band{i}_gain"] == 0.0
    assert eq["output_db"] == 0.0


def test_apply_band_gains_caps_at_plus_minus_6():
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    bp.apply_band_gains(p, [99, 1.5, -2.0, 0, 0, 0, 0, -99], hp_hz=160)
    eq = bp.eq_block(p)["params"]
    assert eq["band1_gain"] == 6.0      # capped to +6 (NOT +24)
    assert eq["band2_gain"] == 1.5
    assert eq["band8_gain"] == -6.0     # capped to -6
    assert eq["band1_freq"] == 160.0    # high-pass moved


def test_apply_band_gains_leaves_output_db_at_zero_no_makeup():
    # Native plugins have NO usable dB-level control, so the EQ output_db stays
    # EXACTLY 0. apply_band_gains writes the tone trim (capped +/-6) to the BANDS
    # and NEVER a cut-bias makeup offset onto output_db (normalize_for_headroom is
    # removed). A positive band is kept as tone -- not cut-biased away.
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    bp.apply_band_gains(p, [0, 6, 5, 2, 0, 4, 0, 0], hp_hz=80)
    eq = bp.eq_block(p)["params"]
    assert eq["band2_gain"] == 6.0      # positive band kept as tone (no cut-bias)
    assert eq["output_db"] == 0.0       # never a makeup -- output_db stays 0


# --- YAML round-trip -------------------------------------------------------

def test_yaml_round_trip(tmp_path: Path):
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    path = tmp_path / "preset.yaml"
    bp.dump_yaml(p, str(path))
    back = bp.load_yaml(str(path))
    assert back == p


# --- type-driven cab decision + hold mask ----------------------------------

def _fine_ltas(top_below_body_db: float) -> np.ndarray:
    """Synthetic fine LTAS: flat body, top octave sitting `top_below_body_db`
    below the body. (Used as a synthetic reference spectrum across the search
    tests -- the cab decision no longer reads the spectrum at all.)"""
    centers = np.asarray(FINE)
    v = np.full(len(centers), -10.0)
    v[centers >= 6300] = -10.0 - top_below_body_db
    return v


# The cab decision is a PURE catalog-type check (no render, no measure):
#   cab auto-inserts  iff  core is `type: preamp`  AND  --cab-model given  AND
#   no researched cab already present.
# A `type: amp` capture is a FULL amp (combo or head+cab) -> NEVER cabbed; a
# `type: body` (acoustic) and a `type: full_rig` are never cabbed either.

def test_decide_cab_preamp_gets_the_cab():
    # a type: preamp (preamp only, no power amp/speaker) needs a cab
    assert bp.decide_cab("preamp", "ir_marshall_4x12_v30", False) == "ir_marshall_4x12_v30"


def test_decide_cab_amp_never_gets_cab():
    # a type: amp is a FULL amp (combo OR head+cab mic'd) -> NEVER cabbed
    assert bp.decide_cab("amp", "ir_marshall_4x12_v30", False) is None


def test_decide_cab_full_rig_never_gets_cab():
    assert bp.decide_cab("full_rig", "ir_marshall_4x12_v30", False) is None


def test_decide_cab_body_never_gets_cab():
    # an acoustic body core is never given a guitar cab
    assert bp.decide_cab("body", "ir_marshall_4x12_v30", False) is None


def test_decide_cab_preamp_with_researched_cab_gets_none():
    # a researched cab is already in the chain -> never double the cabinet
    assert bp.decide_cab("preamp", "ir_marshall_4x12_v30", True) is None


def test_decide_cab_preamp_without_cab_model_gets_none():
    # no --cab-model given -> nothing to auto-insert
    assert bp.decide_cab("preamp", None, False) is None


def test_coarse_hold_mask_excludes_dead_top_and_out_of_range():
    # 8-band ltas: body ~0, top band 30 dB down -> trustworthy_band_mask drops
    # the top 2 bands; reliable_range trims the extremes.
    ref8 = np.array([-5, 0, 0, 0, 0, -2, -10, -30], dtype=float)
    mask = bp.coarse_hold_mask(ref8, reliable_range_hz=[160, 2560])
    # band index 0 (80 Hz) out of range -> held
    assert mask[0] == False
    # top dead bands held
    assert mask[7] == False
    # a mid in-range trustworthy band kept
    assert mask[2] == True


# --- base-chain classification (SEARCH / TUNE / FIXED) ----------------------

def test_classify_chain_roles_and_order_preserved():
    blocks = [
        {"type": "dynamics", "model": "comp"},
        {"type": "gain", "candidates": ["none", "od"]},
        {"type": "amp", "candidates": ["a1", "a2"]},
        {"type": "filter", "model": bp.EQ_MODEL},
        {"type": "mod", "model": "chorus"},
        {"type": "delay", "model": "dig"},
        {"type": "reverb", "model": "hall"},
    ]
    slots = bp.classify_chain(blocks)
    assert [s.role for s in slots] == [
        "fixed", "search", "search", "tune", "fixed", "fixed", "fixed",
    ]
    # signal order is preserved verbatim
    assert slots[0].block["model"] == "comp"
    assert slots[3].block["model"] == bp.EQ_MODEL
    assert slots[-1].block["model"] == "hall"


def test_classify_chain_all_eleven_block_types():
    # SEARCH = preamp/amp/body/gain/cab (they carry candidates); TUNE = the eq
    # filter; everything else (incl. a NON-eq filter) is FIXED pass-through.
    blocks = [
        {"type": "preamp", "candidates": ["p1"]},
        {"type": "amp", "candidates": ["a1"]},
        {"type": "body", "candidates": ["b1"]},
        {"type": "gain", "candidates": ["od"]},
        {"type": "cab", "candidates": ["c1"]},
        {"type": "dynamics", "model": "comp"},
        {"type": "filter", "model": bp.EQ_MODEL},
        {"type": "filter", "model": "graphic_eq"},   # a non-EQ filter: FIXED
        {"type": "wah", "model": "crybaby"},
        {"type": "pitch", "model": "octaver"},
        {"type": "mod", "model": "phaser"},
        {"type": "delay", "model": "tape"},
        {"type": "reverb", "model": "spring"},
    ]
    slots = bp.classify_chain(blocks)
    assert [s.role for s in slots] == [
        "search", "search", "search", "search", "search",
        "fixed", "tune", "fixed", "fixed", "fixed", "fixed", "fixed", "fixed",
    ]


def test_classify_chain_drops_forbidden_blocks():
    blocks = [
        {"type": "amp", "candidates": ["a"]},
        {"type": "volume", "model": "vol"},
        {"type": "limiter", "model": "limiter_brickwall"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    slots = bp.classify_chain(blocks)
    models = [s.block.get("model") for s in slots]
    types = [s.block["type"] for s in slots]
    assert "limiter_brickwall" not in models
    assert "volume" not in types


def test_strip_forbidden_removes_limiter_and_volume():
    blocks = [
        {"type": "amp", "model": "a"},
        {"type": "limiter", "model": "limiter_brickwall"},
        {"type": "volume", "model": "vol"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    kept = bp.strip_forbidden(blocks)
    assert len(kept) == 2
    assert all(b.get("model") != "limiter_brickwall" for b in kept)
    assert all(b["type"] != "volume" for b in kept)


# --- model-id validation (render exits 0 on a dropped block) ----------------

def test_assert_no_dropped_blocks_passes_on_clean_output():
    bp.assert_no_dropped_blocks("rendered 480000 samples; wrote out.wav")  # no raise


def test_assert_no_dropped_blocks_raises_on_ignored_block():
    with pytest.raises(SystemExit):
        bp.assert_no_dropped_blocks("warn: ignoring unsupported or invalid block at preset:2")


def test_assert_no_dropped_blocks_raises_on_unsupported_nam_model():
    with pytest.raises(SystemExit):
        bp.assert_no_dropped_blocks("unsupported nam model 'nam_typo_x'")


# --- base-chain search (injected fakes) ------------------------------------

def test_search_chain_picks_highest_proximity_combo():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        if "good_amp" in models and "good_drive" in models:
            return ref                            # perfect match -> 100
        return ref + 12.0

    blocks = [
        {"type": "gain", "candidates": ["none", "good_drive"]},
        {"type": "amp", "candidates": ["good_amp", "bad_amp"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["amp"] == "good_amp"
    assert res["drives"] == ["good_drive"]
    assert res["proximity_pct"] == pytest.approx(100.0, abs=1e-6)


def test_search_chain_fixed_fx_survive_into_output_verbatim():
    comp = {"type": "dynamics", "model": "comp_studio", "enabled": True,
            "params": {"ratio": 4, "threshold": -18}}
    delay = {"type": "delay", "model": "digital_clean", "enabled": True,
             "params": {"time_ms": 343, "feedback": 28, "mix": 30}}
    blocks = [
        comp,
        {"type": "gain", "candidates": ["none"]},
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
        delay,
    ]
    res = bp.search_chain(bp.classify_chain(blocks), np.zeros(len(FINE)),
                          measure_fn=lambda b: np.zeros(len(FINE)))
    out = res["blocks"]
    # the researched FX blocks appear verbatim (same params), in signal order
    assert comp in out
    assert delay in out
    types = [b["type"] for b in out]
    assert types.index("dynamics") < types.index("amp") < types.index("filter") < types.index("delay")


def test_search_chain_none_drive_yields_empty_drive_slot():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "gain", "candidates": ["none"]},
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    assert res["drives"] == []
    assert not any(b["type"] == "gain" for b in res["blocks"])


def test_search_chain_multiple_gain_slots_form_a_stack_in_order():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "gain", "candidates": ["boost"]},
        {"type": "gain", "candidates": ["od"]},
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    gains = [b["model"] for b in res["blocks"] if b["type"] == "gain"]
    assert gains == ["boost", "od"]
    assert res["drives"] == ["boost", "od"]


def test_search_chain_full_rig_amp_gets_no_cab():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        # a full_rig amp must never be probed amp-only for cab need; here the
        # only render is the full chain.
        return ref

    blocks = [
        {"type": "amp", "candidates": ["rig_amp:full_rig"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_model="ir_x")
    assert res["amp"] == "rig_amp"
    assert res["amp_type"] == "full_rig"
    assert res["cab_model"] is None
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert not any(b["type"] == "ir" for b in res["blocks"])
    # the chosen block carries the real full_rig type
    assert any(b["type"] == "full_rig" and b["model"] == "rig_amp" for b in res["blocks"])


def test_search_chain_preamp_inserts_cab_plugin_right_after_preamp():
    # a `type: preamp` core (preamp only) needs a cab -> the --cab-model cab is
    # auto-inserted right after the preamp, as a `type: cab` PLUGIN block.
    ref = _fine_ltas(20.0)

    blocks = [
        {"type": "preamp", "candidates": ["nam_marshall_jcm_800_2203_a2"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref,
                          cab_model="ir_mesa_os_4x12_v30")
    assert res["cab_reason"] == "preamp"
    assert res["cab_model"] == "ir_mesa_os_4x12_v30"
    # the chosen cab model id is recorded in the gear history too
    assert res["history"][0]["cab_model"] == "ir_mesa_os_4x12_v30"
    out = res["blocks"]
    types = [b["type"] for b in out]
    # the auto cab is a `type: cab` PLUGIN block (applies output_gain_db), not a
    # raw generic_ir wav
    assert "cab" in types
    assert not any(b.get("model") == "generic_ir" for b in out)
    cab = [b for b in out if b["type"] == "cab"][0]
    assert cab["model"] == "ir_mesa_os_4x12_v30"
    assert types.index("cab") == types.index("preamp") + 1   # cab right after preamp


def test_search_chain_amp_core_never_cabbed_even_with_cab_model():
    # a `type: amp` capture is a FULL amp (combo OR head+cab mic'd) -> it is NEVER
    # auto-cabbed, even when --cab-model is given (no double-cab onto a combo).
    ref = _fine_ltas(20.0)

    blocks = [
        {"type": "amp", "candidates": ["nam_fender_deluxe_reverb_a2"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref,
                          cab_model="ir_x")
    assert res["cab_model"] is None
    assert res["cab_reason"] is None
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert not any(b["type"] == "ir" for b in res["blocks"])


def test_search_chain_preamp_cab_decision_makes_no_extra_probe_render():
    # the cab decision is a pure catalog-TYPE check -> NO amp-only probe render.
    # A single preamp combo must trigger exactly ONE render (the full chain), not
    # two (the old direct-detection added an extra amp-only probe render).
    ref = _fine_ltas(20.0)
    calls = {"n": 0}

    def measure_fn(blocks):
        calls["n"] += 1
        return ref

    blocks = [
        {"type": "preamp", "candidates": ["preamp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_model="ir_x")
    assert res["cab_reason"] == "preamp"
    assert calls["n"] == 1     # only the full-chain render; no amp-only probe


def test_search_chain_preamp_with_researched_ir_cab_blocks_auto_insert():
    ref = _fine_ltas(20.0)

    # an off-catalog researched cab (type ir, generic_ir) already in the chain:
    # even a preamp core must not get a second auto-inserted cab.
    def measure_fn(blocks):
        return ref

    blocks = [
        {"type": "preamp", "candidates": ["preamp_a"]},
        {"type": "ir", "model": "generic_ir", "params": {"file": "/abs/researched.wav"}},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_model="ir_other")
    irs = [b for b in res["blocks"] if b["type"] == "ir"]
    assert len(irs) == 1
    assert irs[0]["params"]["file"] == "/abs/researched.wav"
    # no auto cab plugin added either
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert res["cab_model"] is None
    assert res["cab_reason"] is None


def test_search_chain_preamp_with_researched_cab_plugin_blocks_auto_insert():
    ref = _fine_ltas(20.0)

    # a researched `type: cab` plugin already FIXED in the chain: a preamp core
    # must not get a second auto-inserted cab.
    blocks = [
        {"type": "preamp", "candidates": ["preamp_a"]},
        {"type": "cab", "model": "ir_marshall_1960av_4x12", "params": {}},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref,
                          cab_model="ir_other")
    cabs = [b for b in res["blocks"] if b["type"] == "cab"]
    assert len(cabs) == 1
    assert cabs[0]["model"] == "ir_marshall_1960av_4x12"
    assert res["cab_model"] is None
    assert res["cab_reason"] is None


def test_search_chain_cab_search_slot_searches_cab_plugins():
    ref = _fine_ltas(20.0)

    # a base-chain `type: cab` SEARCH slot: the tool searches the cab plugins and
    # picks the best one (and never auto-inserts a second cab on top).
    def measure_fn(blocks):
        cabs = [b for b in blocks if b["type"] == "cab"]
        return ref if (cabs and cabs[0]["model"] == "ir_good") else ref + 12.0

    blocks = [
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "cab", "candidates": ["ir_good", "ir_bad"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_model="ir_auto")
    chosen = [b for b in res["blocks"] if b["type"] == "cab"]
    assert len(chosen) == 1               # no auto-insert double cab
    assert chosen[0]["model"] == "ir_good"
    assert res["cab_model"] is None       # the auto-insert path did not fire


def test_search_chain_body_core_searched_like_amp_and_never_cabbed():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        return ref if "body_good" in models else ref + 12.0

    blocks = [
        {"type": "body", "candidates": ["body_good", "body_bad"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_model="ir_x")
    assert res["core"] == "body_good"
    # an acoustic body core never gets a guitar cab, even with --cab-model given
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert not any(b["type"] == "ir" for b in res["blocks"])


def test_search_chain_output_has_no_limiter_or_volume():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "gain", "candidates": ["od"]},
        {"type": "amp", "candidates": ["a"]},
        {"type": "volume", "model": "vol"},
        {"type": "limiter", "model": "limiter_brickwall"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    models = [b.get("model") for b in res["blocks"]]
    types = [b["type"] for b in res["blocks"]]
    assert "limiter_brickwall" not in models
    assert "volume" not in types


# --- param-bearing search candidates (the capture's own axis) --------------

def test_search_chain_dict_candidate_params_land_on_block_and_report():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "amp", "candidates": [{"model": "amp_a", "params": {"gain": 8}}]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    amp = [b for b in res["blocks"] if b["type"] == "amp"][0]
    # the mapping candidate's params are REAL block params -> land on the block
    assert amp["params"] == {"gain": 8}
    # the chosen-combo summary records the params...
    assert res["amp_params"] == {"gain": 8}
    # ...and so does the gear history (so the winning axis value is visible)
    assert res["history"][0]["amp_params"] == {"gain": 8}


def test_search_chain_bare_string_candidate_keeps_default_params():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    amp = [b for b in res["blocks"] if b["type"] == "amp"][0]
    assert amp["params"] == {}            # a bare string renders at default params
    assert res["amp_params"] == {}


def test_search_chain_cranks_capture_own_axis_and_higher_gain_wins():
    # the under-gained-modded-amp case: ONE capture exposes a `gain` axis; the
    # search sweeps it as distinct variants and the cranked variant wins.
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        amp = [b for b in blocks if b["type"] == "amp"]
        if amp and amp[0]["params"].get("gain") == 10:
            return ref                    # cranked to 10 -> perfect match
        return ref + 12.0                 # default / lower gain -> worse

    blocks = [
        {"type": "amp", "candidates": [
            "nam_marshall_1959_slp_a2",                              # default (low)
            {"model": "nam_marshall_1959_slp_a2", "params": {"gain": 8}},
            {"model": "nam_marshall_1959_slp_a2", "params": {"gain": 10}},
        ]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["amp"] == "nam_marshall_1959_slp_a2"
    assert res["amp_params"] == {"gain": 10}
    amp = [b for b in res["blocks"] if b["type"] == "amp"][0]
    assert amp["params"]["gain"] == 10
    # all three variants of the same model were searched
    assert len(res["history"]) == 3


def test_search_chain_mixes_string_and_dict_candidates_in_one_slot():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        amp = [b for b in blocks if b["type"] == "amp"]
        if amp and amp[0]["model"] == "amp_b" and amp[0]["params"].get("gain") == 5:
            return ref
        return ref + 9.0

    blocks = [
        {"type": "amp", "candidates": [
            "amp_a",                                       # bare string
            {"model": "amp_b", "params": {"gain": 5}},     # mapping
        ]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["amp"] == "amp_b"
    assert res["amp_params"] == {"gain": 5}
    assert len(res["history"]) == 2


def test_search_chain_drive_dict_candidate_records_per_drive_params():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        g = [b for b in blocks if b["type"] == "gain"]
        return ref if (g and g[0]["params"].get("drive") == 9) else ref + 12.0

    blocks = [
        {"type": "gain", "candidates": ["od_a", {"model": "od_a", "params": {"drive": 9}}]},
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["drives"] == ["od_a"]
    assert res["drive_params"] == [{"drive": 9}]
    gain = [b for b in res["blocks"] if b["type"] == "gain"][0]
    assert gain["params"]["drive"] == 9


def test_search_chain_dict_full_rig_true_skips_cab_like_suffix():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "amp", "candidates": [{"model": "rig_amp", "full_rig": True}]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref,
                          cab_model="ir_x")
    assert res["amp"] == "rig_amp"
    assert res["amp_type"] == "full_rig"
    assert res["cab_model"] is None
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert not any(b["type"] == "ir" for b in res["blocks"])
    assert any(b["type"] == "full_rig" and b["model"] == "rig_amp" for b in res["blocks"])


def test_search_chain_none_still_yields_empty_slot_alongside_dicts():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "gain", "candidates": ["none", {"model": "od_a", "params": {"drive": 3}}]},
        {"type": "amp", "candidates": ["amp_a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    # 'none' wins (fake reward for the empty-drive render)
    def measure_fn(blocks):
        return ref if not any(b["type"] == "gain" for b in blocks) else ref + 12.0

    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["drives"] == []
    assert res["drive_params"] == []
    assert not any(b["type"] == "gain" for b in res["blocks"])


# --- pinned core (fixed model = CORE, no `candidates:` needed) --------------
# The CORE is identified by TYPE (amp/preamp/body), NOT by the presence of a
# `candidates:` list. A fixed-model core is PINNED: a single variant used
# verbatim, but still the searchable/cabbable core. The number REGULATES (EQ,
# gain-axis, drive, cab, level) -- it never swaps a pinned amp MODEL.

def test_classify_chain_pinned_amp_is_core_not_fixed():
    # a `type: amp` block with a fixed model and NO candidates is the CORE
    # (ROLE_SEARCH), never a FIXED pass-through.
    blocks = [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    slots = bp.classify_chain(blocks)
    assert [s.role for s in slots] == ["search", "tune"]


def test_classify_chain_pinned_preamp_and_body_are_core_not_fixed():
    blocks = [
        {"type": "preamp", "model": "nam_preamp_x"},
        {"type": "body", "model": "nam_body_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    assert [s.role for s in bp.classify_chain(blocks)] == ["search", "search", "tune"]


def test_search_chain_pinned_amp_combo_is_core_and_never_cabbed():
    # the Fender Deluxe Reverb case: a PINNED `type: amp` is a FULL combo amp
    # (speaker baked in). It must be the recorded CORE, used verbatim, but it
    # NEVER takes a cab -- even with --cab-model given (the old direct-detection
    # was double-cabbing a combo).
    ref = _fine_ltas(20.0)

    blocks = [
        {"type": "amp", "model": "nam_fender_deluxe_reverb_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref,
                          cab_model="ir_mesa_os_4x12_v30")
    assert res["amp"] == "nam_fender_deluxe_reverb_a2"
    assert res["amp_type"] == "amp"
    assert res["cab_model"] is None
    assert res["cab_reason"] is None
    # a single pinned variant -> exactly one combo searched, never swapped
    assert len(res["history"]) == 1
    out = res["blocks"]
    assert not any(b["type"] == "cab" for b in out)
    amps = [b for b in out if b["type"] == "amp"]
    assert len(amps) == 1 and amps[0]["model"] == "nam_fender_deluxe_reverb_a2"


def test_search_chain_pinned_preamp_is_core_and_gets_cab():
    # a PINNED `type: preamp` (e.g. nam_marshall_jcm_800_2203_a2 -- preamp, no
    # power amp/speaker) is the recorded CORE and DOES take the --cab-model cab,
    # inserted right after the preamp.
    ref = _fine_ltas(20.0)

    blocks = [
        {"type": "preamp", "model": "nam_marshall_jcm_800_2203_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref,
                          cab_model="ir_mesa_os_4x12_v30")
    assert res["amp"] == "nam_marshall_jcm_800_2203_a2"
    assert res["amp_type"] == "preamp"
    assert res["cab_reason"] == "preamp"
    assert res["cab_model"] == "ir_mesa_os_4x12_v30"
    assert len(res["history"]) == 1
    out = res["blocks"]
    types = [b["type"] for b in out]
    assert types.index("cab") == types.index("preamp") + 1   # cab right after preamp


def test_search_chain_pinned_amp_with_params_lands_on_block_and_report():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "amp", "model": "amp_x", "params": {"gain": 6}},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn=lambda b: ref)
    amp = [b for b in res["blocks"] if b["type"] == "amp"][0]
    assert amp["model"] == "amp_x"
    assert amp["params"] == {"gain": 6}
    assert res["amp_params"] == {"gain": 6}


def test_search_chain_pinned_preamp_is_core():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "preamp", "model": "nam_preamp_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref, cab_model=None)
    assert res["amp"] == "nam_preamp_x"
    assert res["amp_type"] == "preamp"


def test_search_chain_pinned_body_core_is_searched_and_never_cabbed():
    ref = _fine_ltas(20.0)
    blocks = [
        {"type": "body", "model": "nam_body_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, lambda b: ref, cab_model="ir_x")
    assert res["core"] == "nam_body_x"
    # a body core is never given a guitar cab even with --cab-model present
    assert not any(b["type"] == "cab" for b in res["blocks"])
    assert not any(b["type"] == "ir" for b in res["blocks"])


def test_search_chain_pinned_amp_gain_axis_picks_higher_never_swaps_model():
    # pinned-but-gain-regulated: ONE model, two gain variants given as
    # candidates. The number picks the higher-proximity gain but never a
    # different amp model.
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        amp = [b for b in blocks if b["type"] == "amp"]
        if amp and amp[0]["params"].get("gain") == 8:
            return ref
        return ref + 12.0

    blocks = [
        {"type": "amp", "candidates": [
            {"model": "nam_dumble_ods_john_mayer_a2", "params": {"gain": 5}},
            {"model": "nam_dumble_ods_john_mayer_a2", "params": {"gain": 8}},
        ]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["amp"] == "nam_dumble_ods_john_mayer_a2"
    assert res["amp_params"] == {"gain": 8}
    assert len(res["history"]) == 2


def test_search_chain_multi_model_stand_in_still_searches_distinct_models():
    # the multi-model stand-in case: 2+ distinct amp models as candidates still
    # search as before (the number picks the best model when authorised to).
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        return ref if "amp_good" in models else ref + 12.0

    blocks = [
        {"type": "amp", "candidates": ["amp_bad", "amp_good"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn)
    assert res["amp"] == "amp_good"
    assert len(res["history"]) == 2


# --- param provenance (Rule B: sourced / derived / unverified) -------------

def test_block_provenance_reads_marker():
    assert bp.block_provenance({"type": "delay", "model": "d", "provenance": "sourced"}) == "sourced"
    assert bp.block_provenance({"type": "delay", "model": "d", "provenance": "derived"}) == "derived"
    assert bp.block_provenance({"type": "delay", "model": "d", "provenance": "unverified"}) == "unverified"


def test_block_provenance_absent_is_unverified():
    # a default presented with NO source must NEVER read as sourced (Rule B core)
    assert bp.block_provenance({"type": "dynamics", "model": "comp"}) == "unverified"


def test_block_provenance_unknown_value_is_unverified():
    # a garbage marker is conservatively treated as unverified, never trusted
    assert bp.block_provenance({"type": "delay", "model": "d", "provenance": "guessed"}) == "unverified"


def test_param_provenance_report_classifies_fixed_and_lists_unverified():
    blocks = [
        {"type": "dynamics", "model": "comp", "provenance": "sourced"},
        {"type": "gain", "candidates": ["od"]},               # SEARCH -> not here
        {"type": "amp", "candidates": ["a1"]},                # SEARCH -> not here
        {"type": "filter", "model": bp.EQ_MODEL},             # TUNE   -> not here
        {"type": "delay", "model": "dig", "provenance": "derived"},
        {"type": "reverb", "model": "hall"},                  # absent -> unverified
    ]
    rep = bp.param_provenance_report(bp.classify_chain(blocks))
    by_model = {e["model"]: e["provenance"] for e in rep["blocks"]}
    assert by_model == {"comp": "sourced", "dig": "derived", "hall": "unverified"}
    # SEARCH amp/drive and the TUNE EQ are reported elsewhere, not as FX provenance
    assert "a1" not in by_model and "od" not in by_model and bp.EQ_MODEL not in by_model
    # the explicit unverified list surfaces exactly the unsourced FX block(s)
    assert {e["model"] for e in rep["unverified"]} == {"hall"}


def test_search_chain_strips_provenance_from_fixed_block():
    delay = {"type": "delay", "model": "dig", "enabled": True,
             "params": {"time_ms": 343}, "provenance": "derived"}
    blocks = [
        {"type": "amp", "candidates": ["a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
        delay,
    ]
    res = bp.search_chain(bp.classify_chain(blocks), np.zeros(len(FINE)),
                          measure_fn=lambda b: np.zeros(len(FINE)))
    emitted = [b for b in res["blocks"] if b.get("model") == "dig"][0]
    # the helper key is metadata, NOT a real OpenRig param -> stripped from output
    assert "provenance" not in emitted
    # the rest of the FIXED block survives verbatim
    assert emitted["params"] == {"time_ms": 343}


def test_search_chain_strips_provenance_from_search_block():
    blocks = [
        {"type": "amp", "candidates": ["a"], "provenance": "sourced"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), np.zeros(len(FINE)),
                          measure_fn=lambda b: np.zeros(len(FINE)))
    amp = [b for b in res["blocks"] if b.get("model") == "a"][0]
    assert "provenance" not in amp


def test_emitted_preset_never_contains_a_provenance_key():
    blocks = [
        {"type": "dynamics", "model": "comp", "provenance": "sourced"},
        {"type": "gain", "candidates": ["od"], "provenance": "sourced"},
        {"type": "amp", "candidates": ["a"]},
        {"type": "filter", "model": bp.EQ_MODEL},
        {"type": "reverb", "model": "hall"},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), np.zeros(len(FINE)),
                          measure_fn=lambda b: np.zeros(len(FINE)))
    assert all("provenance" not in b for b in res["blocks"])


# --- EQ-refine loop (injected fakes) ---------------------------------------

def _winning_preset() -> dict:
    p = bp.make_preset("demo", "Demo", bp.assemble_blocks([], "amp1", cab_model=None))
    bp.set_eq_grid(p)
    return p


def test_refine_eq_converges_within_floor_and_stops_early():
    floor = 90.0
    ref8 = np.zeros(8)

    # proximity climbs 80 -> 100 across iterations; within floor by iter 3
    seq = iter([80.0, 86.0, 92.0, 95.0, 97.0, 98.0])

    def measure_fn(preset, it):
        return {"wet_8band_ltas": np.zeros(8), "proximity_pct": next(seq)}

    out = bp.refine_eq(_winning_preset(), ref8, np.ones(8, dtype=bool), floor,
                       measure_fn, max_iters=6)
    assert out["within"] is True
    assert out["best_prox"] >= floor - bp.SELF_FLOOR_MARGIN_PCT
    assert len(out["history"]) < 6        # stopped before the cap


def test_refine_eq_bails_on_plateau_below_floor():
    floor = 95.0
    ref8 = np.zeros(8)

    def measure_fn(preset, it):
        return {"wet_8band_ltas": np.full(8, 5.0), "proximity_pct": 70.0}

    out = bp.refine_eq(_winning_preset(), ref8, np.ones(8, dtype=bool), floor,
                       measure_fn, max_iters=8)
    assert out["within"] is False
    assert len(out["history"]) < 8        # bailed on plateau


def test_refine_eq_never_exceeds_plus_minus_6_and_holds_excluded_bands():
    floor = 99.0
    # reference wants band index 2 way up (+30) and band 5 way down (-30)
    ref8 = np.array([0, 0, 30.0, 0, 0, -30.0, 0, 0])
    # hold mask EXCLUDES band 2 (so it must stay 0 despite the +30 demand)
    hold = np.array([True, True, False, True, True, True, True, True])

    # proximity rises (so the best snapshot keeps advancing through the applied
    # iterations) but never reaches the floor and never plateaus -> the loop
    # runs to the cap and the final preset carries the accumulated trim.
    seq = iter([80.0, 85.0, 89.0, 92.0, 94.0, 96.0, 97.0, 98.0])

    def measure_fn(preset, it):
        # wet sits flat at 0 -> deltas are exactly ref8
        return {"wet_8band_ltas": np.zeros(8), "proximity_pct": next(seq)}

    out = bp.refine_eq(_winning_preset(), ref8, hold, floor, measure_fn,
                       max_iters=8)
    eq = bp.eq_block(out["final_preset"])["params"]
    gains = [eq[f"band{i}_gain"] for i in range(1, 9)]
    assert max(gains) <= 6.0 + 1e-9
    assert min(gains) >= -6.0 - 1e-9
    assert gains[2] == 0.0                # held band stayed at 0
    assert gains[5] == -6.0               # unheld band drove to the -6 cap


# --- level: the EQ is LEVEL-NEUTRAL, output_db ALWAYS 0 ----------------------
# Native plugins have NO usable dB-level control, so build_preset NEVER writes a
# non-zero EQ output_db (nor any other native-block dB level/output param). There
# is NO headroom_pass (the bundled-DI render is hotter than a live input, so
# calibrating the trim to the render's peak left live playback far too quiet) and
# NO normalize_for_headroom (native blocks can't host a makeup dB anyway). The
# refine band gains ship as the tone trim; output_db stays EXACTLY 0. Loudness is
# the user's rig master.

def test_no_level_calibration_functions_or_constants():
    # the render-peak headroom calibration AND the cut-bias makeup are REMOVED:
    # none of these level-calibration symbols may exist anymore.
    assert not hasattr(bp, "headroom_pass")
    assert not hasattr(bp, "normalize_for_headroom")
    assert not hasattr(bp, "PEAK_TARGET_DB")
    assert not hasattr(bp, "PEAK_LO_DB")
    assert not hasattr(bp, "PEAK_HI_DB")


def _hot_wav_factory(tmp_path: Path, scale: float = 2.0):
    import soundfile as sf

    rng = np.random.default_rng(7)

    def _wav(path: Path) -> str:
        # scale 2.0 -> |samples| up to ~8 -> peak ~ +18 dBFS (a HOT render, the
        # case the removed headroom_pass would have CUT to chase a -1 dBFS peak).
        sf.write(str(path), (rng.standard_normal(48000) * scale).astype("float32"), 48000)
        return str(path)

    return _wav


def test_main_ships_eq_output_db_exactly_zero_moderate(tmp_path: Path):
    _noise = _noise_wav_factory(tmp_path)
    _noise(tmp_path / "ref.wav")
    _noise(tmp_path / "di.wav")

    def fake_render(_preset) -> str:
        return _noise(tmp_path / "r.wav")

    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    out_preset = tmp_path / "out.yaml"
    bp.main(_main_args(base, tmp_path, **{"max-iters": 2}), render_fn=fake_render)

    eq = bp.eq_block(bp.load_yaml(str(out_preset)))["params"]
    assert eq["output_db"] == 0.0       # EXACTLY 0 -- no makeup, no calibration


def test_main_hot_chain_is_not_cut_output_db_stays_zero(tmp_path: Path):
    # a chain whose injected render peaks HOT (~ +18 dBFS). The REMOVED
    # headroom_pass would cut output_db to chase a -1 dBFS render peak (pegging at
    # the old OUTPUT_MIN=-24 for a hot chain). output_db must now stay EXACTLY 0 --
    # never -24, never -7, never a makeup; the band gains still carry the tone.
    _hot = _hot_wav_factory(tmp_path)
    _hot(tmp_path / "ref.wav")
    _hot(tmp_path / "di.wav")

    def fake_render(_preset) -> str:
        return _hot(tmp_path / "r.wav")

    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    out_preset = tmp_path / "out.yaml"
    bp.main(_main_args(base, tmp_path, **{"max-iters": 2}), render_fn=fake_render)

    eq = bp.eq_block(bp.load_yaml(str(out_preset)))["params"]
    assert eq["output_db"] == 0.0       # hot chain NOT cut -- ships at natural level
    assert eq["output_db"] != -24.0     # never pegged at the old OUTPUT_MIN
    # the band gains still carry the tone trim (level untouched, tone shaped)
    assert all(-6.0 <= eq[f"band{i}_gain"] <= 6.0 for i in range(1, 9))


# --- Part A: pre-render validate + lint gate --------------------------------

def test_gate_chain_clean_returns_warn_keys():
    raw = [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    out = bp.gate_chain(raw, str(FIXTURES_CATALOG))
    assert "lint" in out and "validation_warnings" in out
    assert isinstance(out["lint"], list)
    assert isinstance(out["validation_warnings"], list)


def test_gate_chain_aborts_on_unknown_model():
    raw = [
        {"type": "amp", "model": "made_up_amp_x"},   # invented -> unknown id
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    with pytest.raises(SystemExit):
        bp.gate_chain(raw, str(FIXTURES_CATALOG))


def test_gate_chain_aborts_on_forbidden_lint_block():
    raw = [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "limiter", "model": "limiter_brickwall"},   # block-level lint
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    with pytest.raises(SystemExit):
        bp.gate_chain(raw, str(FIXTURES_CATALOG))


def test_gate_chain_validates_candidate_model_ids():
    # candidates are expanded and validated -> an invented candidate id aborts
    raw = [
        {"type": "amp", "candidates": ["nam_dumble_ods_john_mayer_a2", "made_up_cand"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    with pytest.raises(SystemExit):
        bp.gate_chain(raw, str(FIXTURES_CATALOG))


def test_gate_chain_validates_plugin_param_axis():
    # an off-axis plugin param value on a candidate aborts (the gain=26 bug)
    raw = [
        {"type": "amp", "candidates": [
            {"model": "nam_dumble_ods_john_mayer_a2", "params": {"gain": 26}},
        ]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    with pytest.raises(SystemExit):
        bp.gate_chain(raw, str(FIXTURES_CATALOG))


def test_gate_chain_no_plugins_root_skips_gate():
    # older invocation with no --plugins-root: skip the gate (don't crash)
    raw = [
        {"type": "amp", "model": "whatever_unknown"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    out = bp.gate_chain(raw, "")
    assert out == {"lint": [], "validation_warnings": []}


# --- Part A: gate wired into main() (aborts BEFORE any render) ---------------

def _write_base(tmp_path: Path, blocks: list[dict], pid: str = "x", name: str = "X") -> Path:
    path = tmp_path / "base.yaml"
    bp.dump_yaml({"id": pid, "name": name, "blocks": blocks}, str(path))
    return path


def _main_args(base: Path, tmp_path: Path, **extra) -> list[str]:
    args = [
        "--base-chain", str(base),
        "--ref", str(tmp_path / "ref.wav"),
        "--render-bin", "render-bin",
        "--di", str(tmp_path / "di.wav"),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    for k, v in extra.items():
        args += [f"--{k}", str(v)]
    return args


def test_main_aborts_before_render_on_unknown_model(tmp_path: Path):
    calls: list = []
    base = _write_base(tmp_path, [
        {"type": "amp", "model": "made_up_amp_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    with pytest.raises(SystemExit):
        bp.main(_main_args(base, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []          # the gate aborted before any render


def test_main_aborts_before_render_on_block_lint_finding(tmp_path: Path):
    calls: list = []
    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "limiter", "model": "limiter_brickwall"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    with pytest.raises(SystemExit):
        bp.main(_main_args(base, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []


def test_main_clean_chain_renders_and_report_has_gate_keys(tmp_path: Path):
    import soundfile as sf

    rng = np.random.default_rng(0)

    def _noise_wav(path: Path) -> str:
        sf.write(str(path), (rng.standard_normal(48000) * 0.05).astype("float32"), 48000)
        return str(path)

    _noise_wav(tmp_path / "ref.wav")
    _noise_wav(tmp_path / "di.wav")

    state = {"n": 0}

    def fake_render(_preset) -> str:
        state["n"] += 1
        return _noise_wav(tmp_path / f"r{state['n']}.wav")

    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    out_preset = tmp_path / "out.yaml"
    rc = bp.main(_main_args(base, tmp_path, **{"max-iters": 2}), render_fn=fake_render)

    assert rc == 0
    assert state["n"] > 0                       # the clean chain rendered
    report = json.loads(out_preset.with_suffix(".report.json").read_text())
    assert "lint" in report
    assert "validation_warnings" in report


# --- Part B: one-command --research pipeline (research -> resolve -> gate ----
# -> search -> render). The agent's ONLY input is the research JSON; it never
# types a model id -- resolve_gear pins it from the catalog.

def _write_research(tmp_path: Path, research: dict, name: str = "research.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(research), encoding="utf-8")
    return path


def _research_args(research: Path, tmp_path: Path, **extra) -> list[str]:
    args = [
        "--research", str(research),
        "--ref", str(tmp_path / "ref.wav"),
        "--render-bin", "render-bin",
        "--di", str(tmp_path / "di.wav"),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    for k, v in extra.items():
        args += [f"--{k}", str(v)]
    return args


def _noise_wav_factory(tmp_path: Path):
    import soundfile as sf

    rng = np.random.default_rng(0)

    def _noise_wav(path: Path) -> str:
        sf.write(str(path), (rng.standard_normal(48000) * 0.05).astype("float32"), 48000)
        return str(path)

    return _noise_wav


def test_main_research_pins_amp_and_reaches_render(tmp_path: Path):
    _noise = _noise_wav_factory(tmp_path)
    _noise(tmp_path / "ref.wav")
    _noise(tmp_path / "di.wav")

    rendered: list = []

    def fake_render(_preset) -> str:
        rendered.append(1)
        return _noise(tmp_path / f"r{len(rendered)}.wav")

    research = {
        "id": "gravity", "name": "Gravity",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out_preset = tmp_path / "out.yaml"
    rc = bp.main(_research_args(rj, tmp_path, **{"max-iters": 2}), render_fn=fake_render)

    assert rc == 0
    assert rendered                             # the resolved chain reached the render
    out = bp.load_yaml(str(out_preset))
    # the amp is the PINNED capture resolve_gear found from the research -- the
    # agent never typed this id
    amp = next(b for b in out["blocks"] if b.get("type") == "amp")
    assert amp["model"] == "nam_dumble_ods_john_mayer_a2"
    report = json.loads(out_preset.with_suffix(".report.json").read_text())
    assert report["amp"] == "nam_dumble_ods_john_mayer_a2"


def test_main_research_unresolvable_amp_aborts_before_any_render(tmp_path: Path):
    calls: list = []
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Fender Twin Reverb", "brand": "fender"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    with pytest.raises(SystemExit) as exc:
        bp.main(_research_args(rj, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []                          # no render before the research is fixed
    # the abort message names the unresolved amp slot
    assert "amp" in str(exc.value).lower()


def test_main_research_resolved_chain_still_passes_through_the_gate(tmp_path: Path, monkeypatch):
    # even if resolve somehow emitted an unknown id, the validate+lint gate must
    # still abort the build BEFORE any render (defense in depth).
    calls: list = []

    def fake_resolve(_research, _catalog):
        return {
            "chain": {"id": "x", "name": "X", "blocks": [
                {"type": "amp", "model": "totally_made_up_amp", "enabled": True, "params": {}},
                {"type": "filter", "model": bp.EQ_MODEL, "params": {}},
            ]},
            "unresolved": [],
        }

    monkeypatch.setattr(bp.resolve_gear, "resolve", fake_resolve)
    rj = _write_research(tmp_path, {"id": "x", "name": "X", "amp": None,
                                    "drives": [], "cab": None, "fx": []})
    with pytest.raises(SystemExit):
        bp.main(_research_args(rj, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []


def test_main_research_and_base_chain_together_is_arg_error(tmp_path: Path):
    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    rj = _write_research(tmp_path, {"id": "x", "name": "X", "amp": None,
                                    "drives": [], "cab": None, "fx": []})
    args = [
        "--base-chain", str(base),
        "--research", str(rj),
        "--ref", str(tmp_path / "ref.wav"),
        "--render-bin", "render-bin",
        "--di", str(tmp_path / "di.wav"),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    with pytest.raises(SystemExit):
        bp.main(args, render_fn=lambda _p: "x.wav")


def test_main_neither_research_nor_base_chain_is_arg_error(tmp_path: Path):
    args = [
        "--ref", str(tmp_path / "ref.wav"),
        "--render-bin", "render-bin",
        "--di", str(tmp_path / "di.wav"),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    with pytest.raises(SystemExit):
        bp.main(args, render_fn=lambda _p: "x.wav")


# --- Part C: reference-less mode (no --ref, or no render binary) -------------
# A generic / example preset ("blues rhythm", "metal", ...) has NO reference WAV
# to match, and openrig-render may not be installed at all. build_preset must
# NOT blind-EQ: it PINS the researched gear, leaves the EQ FLAT (every band gain
# 0, output_db 0), renders NOTHING, and writes a report marked
# mode=reference-less / tunable=false -- an un-tunable starting point until a
# reference WAV or ear feedback is given. The cab auto-insert is the SAME pure
# catalog-type decision (no render). Triggered by: --research / --base-chain
# WITHOUT --ref, OR (with --ref) when --render-bin does not resolve to a runnable
# binary (graceful fallback instead of a crash).

def _refless_research_args(research: Path, tmp_path: Path, **extra) -> list[str]:
    # reference-less: NO --ref, NO --render-bin, NO --di (it never renders)
    args = [
        "--research", str(research),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    for k, v in extra.items():
        args += [f"--{k}", str(v)]
    return args


def _refless_base_args(base: Path, tmp_path: Path, **extra) -> list[str]:
    args = [
        "--base-chain", str(base),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(tmp_path / "out.yaml"),
    ]
    for k, v in extra.items():
        args += [f"--{k}", str(v)]
    return args


def _render_must_not_be_called(_preset):
    raise AssertionError("reference-less mode must never render")


# -- pure assembler: pinned chain + FLAT EQ, no search, no render -------------

def test_assemble_reference_less_pinned_amp_is_flat_eq_no_proximity():
    slots = bp.classify_chain([
        {"type": "amp", "model": "amp_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    res = bp.assemble_reference_less(slots)
    assert res["amp"] == "amp_x"
    eq = bp.eq_block({"blocks": res["blocks"]})["params"]
    assert all(eq[f"band{i}_gain"] == 0.0 for i in range(1, 9))   # FLAT
    assert eq["output_db"] == 0.0
    # there is no reference -> no proximity / history is produced
    assert "proximity_pct" not in res
    assert "history" not in res


def test_assemble_reference_less_preamp_gets_cab_pure_type_decision():
    slots = bp.classify_chain([
        {"type": "preamp", "model": "preamp_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    res = bp.assemble_reference_less(slots, cab_model="ir_cab")
    assert res["cab_model"] == "ir_cab"
    assert res["cab_reason"] == "preamp"
    types = [b["type"] for b in res["blocks"]]
    assert types.index("cab") == types.index("preamp") + 1


def test_assemble_reference_less_amp_combo_never_cabbed():
    slots = bp.classify_chain([
        {"type": "amp", "model": "combo_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    res = bp.assemble_reference_less(slots, cab_model="ir_cab")
    assert res["cab_model"] is None
    assert not any(b["type"] == "cab" for b in res["blocks"])


# -- main(): --research / --base-chain WITHOUT --ref --------------------------

def test_main_research_no_ref_is_reference_less_pinned_flat_eq(tmp_path: Path):
    research = {
        "id": "blues", "name": "Blues Rhythm",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out_preset = tmp_path / "out.yaml"
    # inject a render that EXPLODES if called -> proves nothing is rendered
    rc = bp.main(_refless_research_args(rj, tmp_path), render_fn=_render_must_not_be_called)
    assert rc == 0
    out = bp.load_yaml(str(out_preset))
    amp = next(b for b in out["blocks"] if b.get("type") == "amp")
    # the amp is the PINNED capture resolve_gear found -- the agent never typed it
    assert amp["model"] == "nam_dumble_ods_john_mayer_a2"
    eq = bp.eq_block(out)["params"]
    assert all(eq[f"band{i}_gain"] == 0.0 for i in range(1, 9))   # FLAT, never blind-EQ'd
    assert eq["output_db"] == 0.0
    report = json.loads(out_preset.with_suffix(".report.json").read_text())
    assert report["mode"] == "reference-less"
    assert report["tunable"] is False
    assert report["amp"] == "nam_dumble_ods_john_mayer_a2"
    # there is no reference -> no proximity / within in the report
    assert "proximity_pct" not in report
    assert "within" not in report


def test_main_base_chain_no_ref_is_reference_less_flat_eq(tmp_path: Path):
    base = _write_base(tmp_path, [
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    out_preset = tmp_path / "out.yaml"
    rc = bp.main(_refless_base_args(base, tmp_path), render_fn=_render_must_not_be_called)
    assert rc == 0
    eq = bp.eq_block(bp.load_yaml(str(out_preset)))["params"]
    assert all(eq[f"band{i}_gain"] == 0.0 for i in range(1, 9))
    assert eq["output_db"] == 0.0
    report = json.loads(out_preset.with_suffix(".report.json").read_text())
    assert report["mode"] == "reference-less"
    assert report["tunable"] is False


def test_main_reference_less_runs_gate_unresolved_amp_aborts(tmp_path: Path):
    # reference-less STILL pins via resolve_gear: an unresolvable amp aborts (no
    # render, no preset) -- never guess an id just because there is no reference.
    calls: list = []
    research = {
        "id": "x", "name": "X",
        "amp": {"name": "Fender Twin Reverb", "brand": "fender"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    with pytest.raises(SystemExit) as exc:
        bp.main(_refless_research_args(rj, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []
    assert "amp" in str(exc.value).lower()


def test_main_reference_less_runs_gate_unknown_id_aborts(tmp_path: Path):
    # reference-less STILL runs the validate+lint gate: an unknown model id aborts
    calls: list = []
    base = _write_base(tmp_path, [
        {"type": "amp", "model": "made_up_amp_x"},
        {"type": "filter", "model": bp.EQ_MODEL},
    ])
    with pytest.raises(SystemExit):
        bp.main(_refless_base_args(base, tmp_path),
                render_fn=lambda _p: (calls.append(1), "x.wav")[1])
    assert calls == []


# -- main(): --research + --ref but render binary doesn't resolve -> fallback --

def test_main_research_ref_no_render_binary_falls_back_to_reference_less(tmp_path: Path):
    # research + ref present, but --render-bin does not resolve to a runnable
    # binary AND no render is injected -> FALL BACK to reference-less (no crash):
    # pinned gear, flat EQ, report mode=reference-less / reason="no render binary".
    _noise = _noise_wav_factory(tmp_path)
    _noise(tmp_path / "ref.wav")
    research = {
        "id": "g", "name": "G",
        "amp": {"name": "Dumble Overdrive Special", "brand": "dumble",
                "signature": "john mayer"},
        "drives": [], "cab": None, "fx": [],
    }
    rj = _write_research(tmp_path, research)
    out_preset = tmp_path / "out.yaml"
    args = [
        "--research", str(rj),
        "--ref", str(tmp_path / "ref.wav"),
        "--render-bin", str(tmp_path / "does-not-exist-render"),
        "--plugins-root", str(FIXTURES_CATALOG),
        "--out-preset", str(out_preset),
    ]
    rc = bp.main(args)   # NO render_fn -> the binary-runnable check decides the mode
    assert rc == 0
    report = json.loads(out_preset.with_suffix(".report.json").read_text())
    assert report["mode"] == "reference-less"
    assert report["reason"] == "no render binary"
    eq = bp.eq_block(bp.load_yaml(str(out_preset)))["params"]
    assert all(eq[f"band{i}_gain"] == 0.0 for i in range(1, 9))
    assert eq["output_db"] == 0.0
