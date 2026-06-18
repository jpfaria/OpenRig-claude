"""Tests for the deterministic auto-EQ-match core (scripts/eq_match.py).

The module is a PURE function layer: given a reference WAV and a wet render,
plus the EQ's current band gains, it returns the next band gains that move
the render's normalised long-term spectral shape toward the reference's.
No rig, no network, no rendering happens here — the render+apply loop is
orchestrated by the openrig-tone-builder skill.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common, eq_match  # noqa: E402


SR = 48000


def _tone_bank(sr: int, seconds: float, level: float = 0.2) -> np.ndarray:
    """Broadband test signal: one partial inside every octave band (centres
    80..10240 Hz) so no band sits on the numerical floor — like a real
    guitar, not a sparse tone."""
    t = np.arange(int(sr * seconds)) / sr
    freqs = [82, 165, 330, 660, 1320, 2640, 5280, 10560]
    sig = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    return (level * sig / len(freqs)).astype(np.float64)


def _apply_band_gains_ltas(ltas: np.ndarray, gain_delta: np.ndarray) -> np.ndarray:
    """Model of what the EQ does to the measured shape: a gain delta on a band
    raises that band's LTAS value by the same dB. Used to simulate the loop."""
    return ltas + gain_delta


# --- normalized LTAS -------------------------------------------------------

def test_ltas_has_one_value_per_band():
    sig = _tone_bank(SR, 1.0)
    ltas = eq_match.normalized_ltas(sig, SR)
    assert len(ltas) == len(_common.BANDS_HZ) == 8


def test_ltas_is_level_invariant():
    """Shape, not level: scaling the signal must not change the normalised LTAS
    (this is why we NEVER match the reference RMS)."""
    sig = _tone_bank(SR, 1.0)
    quiet = eq_match.normalized_ltas(sig, SR)
    loud = eq_match.normalized_ltas(sig * 8.0, SR)
    assert np.allclose(quiet, loud, atol=1e-6)


def test_ltas_silence_is_trimmed():
    """A tone followed by a long silent tail measures ~the same as the tone
    alone — silent frames (< -45 dB RMS) are dropped before averaging."""
    tone = _tone_bank(SR, 1.0)
    padded = np.concatenate([tone, np.zeros(SR * 3)])
    a = eq_match.normalized_ltas(tone, SR)
    b = eq_match.normalized_ltas(padded, SR)
    assert np.allclose(a, b, atol=0.5)


# --- gap -------------------------------------------------------------------

def test_gap_zero_for_identical():
    sig = _tone_bank(SR, 1.0)
    ltas = eq_match.normalized_ltas(sig, SR)
    assert eq_match.gap_total_db(ltas, ltas) == 0.0


def test_gap_is_sum_of_absolute_band_deltas():
    ref = np.array([0.0, 1.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    wet = np.zeros(8)
    assert eq_match.gap_total_db(ref, wet) == 3.0


# --- per-band correction ---------------------------------------------------

def test_correction_is_additive():
    """new_gain = current_gain + (ref_band - wet_band)."""
    current = [0.0] * 8
    ref = np.array([0.0, 0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0])
    wet = np.zeros(8)
    new = eq_match.next_band_gains(current, ref, wet)
    assert new[3] == 6.0
    assert all(new[i] == 0.0 for i in range(8) if i != 3)


def test_correction_clamped_to_plus_minus_24():
    current = [0.0] * 8
    ref = np.array([99.0, -99.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    wet = np.zeros(8)
    new = eq_match.next_band_gains(current, ref, wet)
    assert new[0] == 24.0
    assert new[1] == -24.0


def test_correction_accumulates_on_current_gain():
    current = [3.0, 0, 0, 0, 0, 0, 0, 0]
    ref = np.array([2.0, 0, 0, 0, 0, 0, 0, 0])
    wet = np.zeros(8)
    new = eq_match.next_band_gains(current, ref, wet)
    assert new[0] == 5.0  # 3 + (2 - 0)


# --- convergence (the acceptance criterion, in simulation) -----------------

def test_loop_converges_on_a_tilted_render():
    """Simulate the full loop deterministically: a render that is spectrally
    tilted away from the ref must converge to a small gap within a few
    iterations, with NO per-band hand-tuning."""
    ref = np.array([4.0, 3.0, 1.0, -1.0, -2.0, 0.0, 2.0, -5.0])
    ref = ref - ref.mean()
    wet = np.zeros(8)              # flat render
    gains = [0.0] * 8
    gap0 = eq_match.gap_total_db(ref, wet)
    for _ in range(6):
        new = eq_match.next_band_gains(gains, ref, wet)
        wet = _apply_band_gains_ltas(wet, np.array(new) - np.array(gains))
        wet = wet - wet.mean()    # normalised shape, level removed each pass
        gains = new
    gap_final = eq_match.gap_total_db(ref, wet)
    assert gap0 > 10.0
    assert gap_final < 0.5 * gap0
    assert gap_final < 2.0


# --- high-pass (band 1) ----------------------------------------------------

def test_highpass_raises_cutoff_when_render_has_excess_lows():
    """b1 is a high-pass: if the render has MORE low-band energy than the ref,
    push the cutoff up the ladder to remove the excess bass."""
    ladder = eq_match.HIGHPASS_LADDER_HZ
    ref = np.array([-6.0, 0, 0, 0, 0, 0, 0, 0])   # ref is thin in the lows
    wet = np.array([0.0, 0, 0, 0, 0, 0, 0, 0])    # render has more lows
    new_hz = eq_match.next_highpass_hz(ladder[2], ref, wet)
    assert new_hz > ladder[2]


def test_highpass_holds_when_lows_already_match():
    ladder = eq_match.HIGHPASS_LADDER_HZ
    ltas = np.array([0.0, 0, 0, 0, 0, 0, 0, 0])
    assert eq_match.next_highpass_hz(ladder[2], ltas, ltas) == ladder[2]


# --- CLI -------------------------------------------------------------------

def test_cli_emits_correction_json(tmp_path):
    ref_sig = _tone_bank(SR, 1.5)
    # wet = ref with the high partials attenuated → a real spectral gap
    t = np.arange(len(ref_sig)) / SR
    dark = ref_sig - 0.5 * np.sin(2 * np.pi * 7040 * t) / 7
    ref_p = tmp_path / "ref.wav"
    wet_p = tmp_path / "wet.wav"
    sf.write(ref_p, ref_sig, SR)
    sf.write(wet_p, dark, SR)
    out = tmp_path / "eqfix.json"
    script = _HERE.parent / "scripts" / "eq_match.py"
    res = subprocess.run(
        [sys.executable, str(script), str(ref_p), str(wet_p),
         "--gains", "0,0,0,0,0,0,0,0", "--output", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(out.read_text())
    assert len(data["new_gains"]) == 8
    assert len(data["band_gap_db"]) == 8
    assert data["total_gap_db"] >= 0.0


# --- proximity_pct (level-independent timbre proximity, the acceptance bar) -

def test_cli_emits_proximity_pct(tmp_path):
    ref_sig = _tone_bank(SR, 1.5)
    t = np.arange(len(ref_sig)) / SR
    dark = ref_sig - 0.5 * np.sin(2 * np.pi * 7040 * t) / 7
    ref_p = tmp_path / "ref.wav"
    wet_p = tmp_path / "wet.wav"
    sf.write(ref_p, ref_sig, SR)
    sf.write(wet_p, dark, SR)
    out = tmp_path / "eqfix.json"
    script = _HERE.parent / "scripts" / "eq_match.py"
    res = subprocess.run(
        [sys.executable, str(script), str(ref_p), str(wet_p),
         "--gains", "0,0,0,0,0,0,0,0", "--output", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(out.read_text())
    assert "proximity_pct" in data
    assert 0.0 <= data["proximity_pct"] <= 100.0


def test_proximity_pct_unchanged_when_render_scaled_12db(tmp_path):
    """The user's core invariant: the SAME render at +12 dB and -12 dB must
    yield the SAME proximity_pct against the same reference. Volume must not
    move the timbre number."""
    ref_sig = _tone_bank(SR, 1.5)
    t = np.arange(len(ref_sig)) / SR
    wet_sig = ref_sig - 0.5 * np.sin(2 * np.pi * 7040 * t) / 7
    g = 10.0 ** (12.0 / 20.0)  # +12 dB
    ref_p = tmp_path / "ref.wav"
    sf.write(ref_p, ref_sig, SR)

    def prox(wet: np.ndarray, name: str) -> float:
        wp = tmp_path / name
        sf.write(wp, wet, SR)
        return eq_match.build_correction(ref_p, wp, [0.0] * 8)["proximity_pct"]

    base = prox(wet_sig, "w0.wav")
    louder = prox(wet_sig * g, "wl.wav")
    quieter = prox(wet_sig / g, "wq.wav")
    assert louder == pytest.approx(base, abs=0.5)
    assert quieter == pytest.approx(base, abs=0.5)


# --- dead-top guard: never low-pass to chase a separation artifact ---------

def test_next_band_gains_holds_dead_top_bands():
    """When the ref's top octave is excluded (AI-separation dead top), the
    correction must HOLD the top bands — never cut them toward the dead ref.
    Cutting them is the low-pass that kills the amp's natural brilho."""
    current = [0.0] * 8
    ref = np.array([2.0, 5.0, 6.0, 3.0, 0.0, -4.0, -10.0, -30.0])
    wet = np.array([2.0, 5.0, 4.0, 3.0, 0.0, -4.0, 0.0, 0.0])  # live, bright top
    mask = _common.trustworthy_band_mask(ref)
    new = eq_match.next_band_gains(current, ref, wet, band_mask=mask)
    assert new[6] == 0.0 and new[7] == 0.0          # dead top HELD, no low-pass
    assert new[2] == pytest.approx(2.0)             # trustworthy band still corrected


def test_build_correction_band_limits_dead_top_stem(tmp_path):
    """End-to-end: a ref with a dead top octave and a wet with a live, bright
    top must score HIGH proximity (dead top excluded), flag the dead top, and
    NOT cut the top bands toward the artifact."""
    ref_sig = _tone_bank(SR, 1.5)
    t = np.arange(len(ref_sig)) / SR
    # cancel the ref's own 10560 Hz partial exactly (its amplitude is
    # level/len(freqs) = 0.2/8) → dead 10240 Hz octave, the separation artifact
    dead_top = ref_sig - (0.2 / 8) * np.sin(2 * np.pi * 10560 * t)
    ref_p = tmp_path / "ref.wav"
    wet_p = tmp_path / "wet.wav"
    sf.write(ref_p, dead_top, SR)
    sf.write(wet_p, ref_sig, SR)   # wet keeps the live top
    d = eq_match.build_correction(ref_p, wet_p, [0.0] * 8)
    assert d["ref_top_octave_dead"] is True
    assert d["new_gains"][7] == 0.0          # top held, not cut to chase artifact
    assert d["proximity_pct"] >= 95.0        # trustworthy range matches → high
