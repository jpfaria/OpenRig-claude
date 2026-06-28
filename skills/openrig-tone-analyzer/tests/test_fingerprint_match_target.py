"""Functional tests for the honest match-target in the fingerprint (schema 3)."""
import numpy as np
import pytest

from scripts import _common


def _tone(sr=44100, dur=3.0, freqs=(110, 220, 440, 880), top_hz=None, top_amp=0.0):
    t = np.arange(int(sr * dur)) / sr
    sig = sum(np.sin(2 * np.pi * f * t) for f in freqs).astype(np.float32)
    if top_hz:
        sig = sig + top_amp * np.sin(2 * np.pi * top_hz * t).astype(np.float32)
    return (sig / (np.max(np.abs(sig)) + 1e-9)).astype(np.float32), sr


def test_match_target_has_required_fields():
    sig, sr = _tone()
    mt = _common.fingerprint_match_target(sig, sr)
    for k in ("third_octave_centers_hz", "ltas_norm_db", "reliable_mask",
              "reliable_range_hz", "top_octave_dead", "self_floor_pct"):
        assert k in mt, f"missing {k}"
    n = len(mt["third_octave_centers_hz"])
    assert len(mt["ltas_norm_db"]) == n
    assert len(mt["reliable_mask"]) == n


def test_normalized_envelope_peaks_at_zero():
    sig, sr = _tone()
    mt = _common.fingerprint_match_target(sig, sr)
    # level-normalized: loudest band is 0 dB, the rest <= 0
    assert max(mt["ltas_norm_db"]) == pytest.approx(0.0, abs=1e-6)
    assert all(x <= 1e-6 for x in mt["ltas_norm_db"])


def test_dead_top_excluded_from_reliable_range():
    # a band-limited signal (nothing above ~1 kHz) → the high bands are dead and
    # must be marked unreliable, so matching never chases them.
    sig, sr = _tone(freqs=(110, 220, 440))
    mt = _common.fingerprint_match_target(sig, sr)
    centers = mt["third_octave_centers_hz"]
    mask = mt["reliable_mask"]
    hi_idx = [i for i, c in enumerate(centers) if c >= 8000]
    assert hi_idx, "expected high bands in the grid"
    assert not any(mask[i] for i in hi_idx), "dead top bands must be unreliable"
    assert mt["reliable_range_hz"][1] < 8000
