"""Tests for the offline preset-rebuild driver (scripts/rebuild_preset.py).

The module orchestrates the openrig-tone-builder render -> eq_match -> apply
loop entirely offline: it drives `openrig-render --chain <flat-preset.yaml>`
against the bundled DI and `eq_match.py` against a surviving reference, then
writes the converged flat preset YAML. The render and eq_match calls are
injected so the loop logic is testable without the Rust binary or large WAVs.

The PURE layer (grid setup, absolute-gain application, headroom
normalisation, YAML round-trip) is tested directly. The loop is tested with
fake render/eq_match callables that simulate convergence.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import rebuild_preset as rp  # noqa: E402


GRID = [80, 160, 320, 640, 1280, 2560, 5120, 10240]


def _base_preset() -> dict:
    return {
        "id": "demo",
        "name": "Demo (rhythm)",
        "blocks": [
            {"type": "amp", "model": "nam_demo_amp", "enabled": True, "params": {"output_db": -7.5}},
            {"type": "filter", "model": "eq_eight_band_parametric", "enabled": True, "params": {}},
            {"type": "dynamics", "model": "limiter_brickwall", "enabled": True, "params": {}},
        ],
    }


# --- pure layer ------------------------------------------------------------

def test_set_eq_grid_places_bands_on_the_eq_match_grid():
    p = _base_preset()
    rp.set_eq_grid(p)
    eq = rp.eq_block(p)["params"]
    assert eq["band1_type"] == "high_pass"
    assert eq["band8_type"] == "high_shelf"
    for i, f in enumerate(GRID, start=1):
        assert eq[f"band{i}_freq"] == float(f)
        assert eq[f"band{i}_gain"] == 0.0
    assert eq["output_db"] == 0.0


def test_band_gains_reads_eight_values_in_order():
    p = _base_preset()
    rp.set_eq_grid(p)
    rp.eq_block(p)["params"]["band3_gain"] = 4.0
    assert rp.band_gains(p) == [0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_apply_band_gains_sets_absolute_values_and_clamps_and_moves_hp():
    p = _base_preset()
    rp.set_eq_grid(p)
    rp.apply_band_gains(p, [99, 1.5, -2.0, 0, 0, 0, 0, -99], hp_hz=160)
    eq = rp.eq_block(p)["params"]
    assert eq["band1_gain"] == 24.0      # clamped to +24
    assert eq["band2_gain"] == 1.5
    assert eq["band8_gain"] == -24.0     # clamped to -24
    assert eq["band1_freq"] == 160.0     # high-pass cutoff moved


def test_normalize_for_headroom_is_cut_biased_with_makeup_on_output():
    p = _base_preset()
    rp.set_eq_grid(p)
    rp.apply_band_gains(p, [0, 8, 5, 2, 0, 4, 0, 0], hp_hz=80)
    offset = rp.normalize_for_headroom(p)
    eq = rp.eq_block(p)["params"]
    assert offset == 8.0
    # loudest band now sits at 0; nothing boosted into the limiter
    assert max(rp.band_gains(p)) <= 0.0 + 1e-9
    assert eq["band2_gain"] == 0.0
    assert eq["output_db"] == 8.0        # common-mode level recovered once


def test_set_block_enabled_toggles_by_model():
    p = _base_preset()
    rp.set_block_enabled(p, "limiter_brickwall", False)
    lim = [b for b in p["blocks"] if b["model"] == "limiter_brickwall"][0]
    assert lim["enabled"] is False


# --- loop orchestration (injected render / eq_match) -----------------------

def _fake_eqmatch_converging(floor=88.0):
    """Simulate eq_match: each call reports proximity climbing toward `floor`
    as the band gains approach a fixed target, and returns the next gains."""
    target = [0.0, 6.0, -3.0, -2.0, -5.0, 3.0, 0.0, 0.0]

    def fn(preset, gains, hp, it):
        dist = sum(abs(g - t) for g, t in zip(gains, target))
        prox = floor - dist  # converges to floor as gains -> target
        # next gains: move halfway to target (damped) -> monotone convergence
        nxt = [round(g + 0.5 * (t - g), 4) for g, t in zip(gains, target)]
        return {
            "proximity_pct": prox,
            "self_floor_pct": floor,
            "proximity_target_pct": floor - 3.0,
            "within_floor": prox >= floor - 3.0,
            "total_gap_db": max(0.0, dist),
            "new_gains": nxt,
            "new_highpass_hz": hp,
            "ref_top_octave_dead": True,
        }

    return fn


def test_rebuild_loop_stops_at_within_floor_and_picks_best():
    renders = []

    def fake_render(preset, it):
        renders.append(it)

    out = rp.rebuild(_base_preset(), fake_render, _fake_eqmatch_converging(), max_iters=10)
    assert out["within"] is True
    # best proximity is the last (monotone convergence), within the bar
    assert out["best_prox"] >= out["best_floor"] - 3.0
    # the loop did not run all 10 iters once within_floor was reached
    assert len(renders) < 10
    # final preset has the limiter re-enabled
    lim = [b for b in out["final_preset"]["blocks"] if b["model"] == "limiter_brickwall"][0]
    assert lim["enabled"] is True


def test_rebuild_disables_limiter_during_measurement():
    seen = {}

    def fake_render(preset, it):
        if it == 1:
            lim = [b for b in preset["blocks"] if b["model"] == "limiter_brickwall"][0]
            seen["limiter_enabled_iter1"] = lim["enabled"]

    rp.rebuild(_base_preset(), fake_render, _fake_eqmatch_converging(), max_iters=4)
    assert seen["limiter_enabled_iter1"] is False


def test_rebuild_stops_on_plateau_below_floor():
    def flat_eqmatch(preset, gains, hp, it):
        return {
            "proximity_pct": 70.0,           # never improves
            "self_floor_pct": 90.0,
            "proximity_target_pct": 87.0,
            "within_floor": False,
            "total_gap_db": 20.0,
            "new_gains": gains,              # no change -> plateau
            "new_highpass_hz": hp,
            "ref_top_octave_dead": False,
        }

    renders = []
    out = rp.rebuild(_base_preset(), lambda p, it: renders.append(it), flat_eqmatch, max_iters=8)
    assert out["within"] is False
    assert len(renders) < 8  # bailed early on plateau
