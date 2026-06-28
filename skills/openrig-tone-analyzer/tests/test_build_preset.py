"""Tests for the offline single-tone preset builder (scripts/build_preset.py).

build_preset is the deterministic "FORM" of the openrig-tone-builder skill as
ONE portable tool: measure the reference once, search amp x drive (+ cab IR
when the amp capture is DIRECT) for the best spectral proximity, refine the
8-band EQ with a CAPPED (+/-6 dB) trim that HOLDS the dead-top / out-of-range
bands at 0, set the headroom, and write a flat preset whose chain ENDS AT THE
EQ -- no limiter, no volume.

The pure layer (chain assembly, EQ grid, +/-6 cap, hold-mask, headroom
normalisation, YAML round-trip, direct-capture / cab detection) is tested
directly. The gear search and the EQ-refine loop are tested with injected fake
render/measurement callables that simulate gear ranking and convergence -- no
Rust binary, no real WAVs.
"""

from __future__ import annotations

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


def test_cab_block_uses_generic_ir_with_file_param():
    b = bp.cab_block("/abs/cab4x12.wav")
    assert b["type"] == "ir"
    assert b["model"] == "generic_ir"
    # the param key that points generic_ir at a wav is "file" (verified against
    # crates/block-ir/src/ir_generic_ir.rs in the OpenRig source).
    assert b["params"]["file"] == "/abs/cab4x12.wav"


def test_assemble_blocks_drive_amp_cab_eq_in_order():
    blocks = bp.assemble_blocks(["nam_od_a1"], "nam_amp_a1", amp_type="amp",
                                cab_ir="/abs/cab.wav")
    types = [b["type"] for b in blocks]
    assert types == ["gain", "amp", "ir", "filter"]
    # chain ENDS at the EQ filter
    assert blocks[-1]["model"] == bp.EQ_MODEL


def test_assemble_blocks_none_drive_is_omitted():
    blocks = bp.assemble_blocks(["none"], "nam_amp_a1", cab_ir=None)
    types = [b["type"] for b in blocks]
    assert "gain" not in types
    assert types == ["amp", "filter"]


def test_assemble_blocks_stacks_multiple_drives_in_order():
    blocks = bp.assemble_blocks(["a", "b"], "amp1", cab_ir=None)
    gains = [b["model"] for b in blocks if b["type"] == "gain"]
    assert gains == ["a", "b"]


def test_assemble_blocks_full_rig_never_gets_a_cab():
    blocks = bp.assemble_blocks([], "nam_rig_a1", amp_type="full_rig",
                                cab_ir="/abs/cab.wav")
    types = [b["type"] for b in blocks]
    assert "ir" not in types          # full_rig already has the cab
    assert types == ["full_rig", "filter"]


def test_assemble_blocks_direct_amp_gets_a_cab():
    blocks = bp.assemble_blocks([], "nam_amp_a1", amp_type="amp",
                                cab_ir="/abs/cab.wav")
    assert any(b["type"] == "ir" and b["model"] == "generic_ir" for b in blocks)


def test_chain_has_no_limiter_and_no_volume_block():
    blocks = bp.assemble_blocks(["od"], "amp1", cab_ir="/abs/cab.wav")
    models = [b.get("model") for b in blocks]
    types = [b["type"] for b in blocks]
    assert "limiter_brickwall" not in models
    assert "volume" not in types
    # nothing after the EQ
    assert blocks[-1]["model"] == bp.EQ_MODEL


def test_make_preset_shape():
    blocks = bp.assemble_blocks([], "amp1", cab_ir=None)
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
    blocks = bp.assemble_blocks([], "amp1", cab_ir=None)
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


def test_normalize_for_headroom_is_cut_biased_makeup_on_output():
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    bp.apply_band_gains(p, [0, 6, 5, 2, 0, 4, 0, 0], hp_hz=80)
    offset = bp.normalize_for_headroom(p)
    eq = bp.eq_block(p)["params"]
    assert offset == 6.0
    assert max(bp.band_gains(p)) <= 0.0 + 1e-9   # nothing boosted
    assert eq["band2_gain"] == 0.0
    assert eq["output_db"] == 6.0                # common-mode recovered once


# --- YAML round-trip -------------------------------------------------------

def test_yaml_round_trip(tmp_path: Path):
    p = _preset_with_eq()
    bp.set_eq_grid(p)
    path = tmp_path / "preset.yaml"
    bp.dump_yaml(p, str(path))
    back = bp.load_yaml(str(path))
    assert back == p


# --- direct-capture detection + hold mask ----------------------------------

def _fine_ltas(top_below_body_db: float) -> np.ndarray:
    """Synthetic fine LTAS: flat body, top octave sitting `top_below_body_db`
    below the body."""
    centers = np.asarray(FINE)
    v = np.full(len(centers), -10.0)
    v[centers >= 6300] = -10.0 - top_below_body_db
    return v


def test_is_direct_capture_true_when_top_near_body():
    # top only 5 dB below body -> a head with no cab (fizzy/direct)
    assert bp.is_direct_capture(_fine_ltas(5.0)) is True


def test_is_direct_capture_false_when_top_rolled_off():
    # top 30 dB below body -> a cabbed/full-rig roll-off, NOT direct
    assert bp.is_direct_capture(_fine_ltas(30.0)) is False


def test_decide_cab_full_rig_never_gets_cab():
    # measure_fn must never be consulted for a full_rig amp
    def boom(_blocks):
        raise AssertionError("full_rig must not be measured for cab need")

    direct, cab = bp.decide_cab("nam_rig_a1", "full_rig", "/abs/cab.wav", boom)
    assert direct is False
    assert cab is None


def test_decide_cab_direct_amp_gets_the_cab():
    direct, cab = bp.decide_cab("nam_amp_a1", "amp", "/abs/cab.wav",
                                lambda _b: _fine_ltas(4.0))
    assert direct is True
    assert cab == "/abs/cab.wav"


def test_decide_cab_cabbed_amp_gets_no_cab():
    direct, cab = bp.decide_cab("nam_amp_a1", "amp", "/abs/cab.wav",
                                lambda _b: _fine_ltas(35.0))
    assert direct is False
    assert cab is None


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
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_ir="/abs/cab.wav")
    assert res["amp"] == "rig_amp"
    assert res["amp_type"] == "full_rig"
    assert res["cab_ir"] is None
    assert not any(b["type"] == "ir" for b in res["blocks"])
    # the chosen block carries the real full_rig type
    assert any(b["type"] == "full_rig" and b["model"] == "rig_amp" for b in res["blocks"])


def test_search_chain_direct_amp_inserts_cab_right_after_amp():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        types = [b["type"] for b in blocks]
        # the amp-only probe (no cab IR, no drive) reads as a direct head
        if "head_amp" in models and "ir" not in types and "gain" not in types:
            return _fine_ltas(4.0)
        return ref

    blocks = [
        {"type": "amp", "candidates": ["head_amp"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_ir="/abs/cab.wav")
    assert res["direct"] is True
    assert res["cab_ir"] == "/abs/cab.wav"
    out = res["blocks"]
    types = [b["type"] for b in out]
    assert "ir" in types
    assert types.index("ir") == types.index("amp") + 1   # cab right after the amp


def test_search_chain_researched_cab_blocks_auto_insert():
    ref = _fine_ltas(20.0)

    # a researched cab (type ir) already in the chain: even a direct amp must
    # not get a second auto-inserted cab.
    def measure_fn(blocks):
        return ref

    blocks = [
        {"type": "amp", "candidates": ["head_amp"]},
        {"type": "ir", "model": "generic_ir", "params": {"file": "/abs/researched.wav"}},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_ir="/abs/other.wav")
    irs = [b for b in res["blocks"] if b["type"] == "ir"]
    assert len(irs) == 1
    assert irs[0]["params"]["file"] == "/abs/researched.wav"


def test_search_chain_body_core_searched_like_amp_and_never_cabbed():
    ref = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        return ref if "body_good" in models else ref + 12.0

    blocks = [
        {"type": "body", "candidates": ["body_good", "body_bad"]},
        {"type": "filter", "model": bp.EQ_MODEL},
    ]
    res = bp.search_chain(bp.classify_chain(blocks), ref, measure_fn, cab_ir="/abs/cab.wav")
    assert res["core"] == "body_good"
    # an acoustic body core never gets a guitar cab, even with --cab-ir given
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
                          cab_ir="/abs/cab.wav")
    assert res["amp"] == "rig_amp"
    assert res["amp_type"] == "full_rig"
    assert res["cab_ir"] is None
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
    p = bp.make_preset("demo", "Demo", bp.assemble_blocks([], "amp1", cab_ir=None))
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


# --- headroom pass (injected fake render) ----------------------------------

def test_headroom_pass_lands_peak_in_window():
    p = _winning_preset()

    # fake: peak tracks output_db with a fixed offset; start far below target
    state = {"out": 0.0}

    def render_peak_fn(preset):
        out = bp.eq_block(preset)["params"]["output_db"]
        state["out"] = out
        return -20.0 + out   # so out=+13 -> -7 dBFS

    peak = bp.headroom_pass(p, render_peak_fn, max_iters=8)
    assert bp.PEAK_LO_DB <= peak <= bp.PEAK_HI_DB
