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


# --- amp-token parsing -----------------------------------------------------

def test_parse_amp_token_plain_model_is_amp():
    assert bp.parse_amp_token("nam_jcm800_a1") == ("nam_jcm800_a1", "amp")


def test_parse_amp_token_full_rig_suffix():
    assert bp.parse_amp_token("nam_rig_a1:full_rig") == ("nam_rig_a1", "full_rig")


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


# --- gear search (injected fakes) ------------------------------------------

def test_search_gear_picks_the_combo_closest_to_the_reference():
    ref_fine = _fine_ltas(20.0)  # an arbitrary but fixed reference shape
    target_amp = "good_amp"
    target_drive = "good_drive"

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        amp_ok = target_amp in models
        drive_ok = target_drive in models
        if amp_ok and drive_ok:
            return ref_fine                      # perfect match -> proximity 100
        return ref_fine + 12.0                   # worse on every band

    res = bp.search_gear(
        amp_candidates=[("good_amp", "amp"), ("bad_amp", "amp")],
        drive_candidates=["none", "good_drive"],
        cab_ir=None,
        ref_fine_ltas=ref_fine,
        measure_fn=measure_fn,
    )
    assert res["amp"] == target_amp
    assert res["drive"] == target_drive
    assert res["proximity_pct"] == pytest.approx(100.0, abs=1e-6)


def test_search_gear_full_rig_winner_carries_no_cab():
    ref_fine = _fine_ltas(20.0)

    # the full_rig amp is the perfect match; its amp-only must never be probed
    # for cab need, and the winning blocks must contain no ir/cab block.
    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        if "rig_amp" in models:
            return ref_fine
        return ref_fine + 15.0

    res = bp.search_gear(
        amp_candidates=[("rig_amp", "full_rig"), ("head_amp", "amp")],
        drive_candidates=["none"],
        cab_ir="/abs/cab.wav",
        ref_fine_ltas=ref_fine,
        measure_fn=measure_fn,
    )
    assert res["amp"] == "rig_amp"
    assert res["cab_ir"] is None
    assert not any(b["type"] == "ir" for b in res["blocks"])


def test_search_gear_direct_amp_winner_carries_a_cab():
    ref_fine = _fine_ltas(20.0)

    def measure_fn(blocks):
        models = [b.get("model") for b in blocks]
        types = [b["type"] for b in blocks]
        # amp-only probe for the direct head: bright top (direct)
        if "head_amp" in models and "ir" not in types and "gain" not in types:
            return _fine_ltas(4.0)               # direct capture
        if "head_amp" in models:
            return ref_fine                      # full chain matches well
        return ref_fine + 15.0

    res = bp.search_gear(
        amp_candidates=[("head_amp", "amp")],
        drive_candidates=["none"],
        cab_ir="/abs/cab.wav",
        ref_fine_ltas=ref_fine,
        measure_fn=measure_fn,
    )
    assert res["amp"] == "head_amp"
    assert res["direct"] is True
    assert res["cab_ir"] == "/abs/cab.wav"
    assert any(b["type"] == "ir" for b in res["blocks"])


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
