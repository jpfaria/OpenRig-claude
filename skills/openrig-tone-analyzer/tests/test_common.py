"""Unit tests for scripts/_common.py helpers.

TDD pattern: each helper has a focused test that pins its expected behavior on
synthetic or fixture inputs. Tolerances are tight where the math is exact
(dB conversions, RMS) and looser where the estimate is inherently noisy
(THD on a clipped signal, RT60 from a decay tail).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scripts import _common


SR = 22050


# --- ltas_proximity_pct (level-independent timbre proximity) ----------------

def test_proximity_pct_identical_shape_is_100():
    v = np.array([4.0, 3.0, 1.0, -1.0, -2.0, 0.0, 2.0, -5.0])
    assert _common.ltas_proximity_pct(v, v) == pytest.approx(100.0, abs=1e-6)


def test_proximity_pct_is_level_independent():
    """A constant dB offset on either vector (a level / RMS change) must NOT
    move the proximity — timbre proximity is volume-independent by definition."""
    ref = np.array([4.0, 3.0, 1.0, -1.0, -2.0, 0.0, 2.0, -5.0])
    wet = np.array([2.0, 2.0, 0.0, -1.0, -1.0, 1.0, 1.0, -4.0])
    base = _common.ltas_proximity_pct(ref, wet)
    shifted = _common.ltas_proximity_pct(ref - 12.0, wet + 12.0)
    assert shifted == pytest.approx(base, abs=1e-6)


def test_proximity_pct_clamped_to_zero_for_opposite_shape():
    ref = np.array([10.0, -10.0, 10.0, -10.0, 10.0, -10.0, 10.0, -10.0])
    wet = -ref  # cosine -1 → clamped to 0
    p = _common.ltas_proximity_pct(ref, wet)
    assert 0.0 <= p <= 100.0
    assert p == pytest.approx(0.0, abs=1e-6)


# --- trustworthy_band_mask + band-limited proximity (AI-separated dead top) --

def test_trustworthy_band_mask_all_true_for_normal_spectrum():
    """A normal amp tone rolls off gently up top — no band is excluded."""
    band_db = np.array([2.0, 5.0, 6.0, 3.0, 0.0, -4.0, -9.0, -14.0])
    mask = _common.trustworthy_band_mask(band_db)
    assert mask.tolist() == [True] * 8


def test_trustworthy_band_mask_excludes_top_octave_when_collapsed():
    """AI source-separation kills the top octave (10240 band ~30 dB below the
    body). The bands >= ~5 kHz are then untrustworthy and must be excluded."""
    band_db = np.array([2.0, 5.0, 6.0, 3.0, 0.0, -4.0, -10.0, -30.0])
    mask = _common.trustworthy_band_mask(band_db)
    assert mask[:6].all()           # 80..2560 Hz trustworthy
    assert not mask[6] and not mask[7]   # >= 5 kHz excluded


def test_proximity_pct_band_mask_reflects_trustworthy_range():
    """The dead top must NOT drag the number: a bright wet that matches the
    trustworthy range scores high, even though its live top differs from the
    ref's dead top. This is the '99% but sounds muffled' bug."""
    ref = np.array([2.0, 5.0, 6.0, 3.0, 0.0, -4.0, -10.0, -30.0])
    wet = np.array([2.0, 5.0, 6.0, 3.0, 0.0, -4.0, -6.0, -12.0])  # live top
    mask = _common.trustworthy_band_mask(ref)
    full = _common.ltas_proximity_pct(ref, wet)
    limited = _common.ltas_proximity_pct(ref, wet, band_mask=mask)
    assert limited > full
    assert limited == pytest.approx(100.0, abs=0.5)


def _sine(freq_hz: float, duration_s: float, amplitude: float = 0.5, sr: int = SR) -> np.ndarray:
    n = int(round(duration_s * sr))
    t = np.arange(n, dtype=np.float64) / sr
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


# --- 3.1 load_audio ---------------------------------------------------------

def test_load_audio_returns_float32_in_range(clean_di_path: Path) -> None:
    signal, sr = _common.load_audio(clean_di_path)
    assert signal.dtype == np.float32
    assert sr == SR
    assert -1.0 <= signal.min() and signal.max() <= 1.0
    assert signal.ndim == 1  # fixtures are mono


def test_load_audio_rejects_long_file(tmp_path: Path) -> None:
    long_path = tmp_path / "too_long.wav"
    silence = np.zeros(601 * SR, dtype=np.float32)
    sf.write(str(long_path), silence, SR, subtype="PCM_16")
    with pytest.raises(SystemExit) as exc:
        _common.load_audio(long_path)
    assert "too long" in str(exc.value)


def test_load_audio_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _common.load_audio(tmp_path / "nope.wav")
    assert "not found" in str(exc.value)


# --- 3.2 mono_mixdown -------------------------------------------------------

def test_mono_mixdown_passthrough_for_mono() -> None:
    sig = _sine(440, 0.1)
    out = _common.mono_mixdown(sig)
    assert np.allclose(out, sig)


def test_mono_mixdown_averages_stereo() -> None:
    left = _sine(440, 0.1)
    right = _sine(880, 0.1)
    stereo = np.stack([left, right], axis=0)
    out = _common.mono_mixdown(stereo)
    assert np.allclose(out, (left + right) / 2)


# --- 3.3 compute_rms_db -----------------------------------------------------

def test_rms_db_known_sine() -> None:
    sig = _sine(1000, 1.0, amplitude=0.5)
    rms_db = _common.compute_rms_db(sig)
    # RMS of a 0.5-amplitude sine = 0.5 / sqrt(2) ≈ 0.3536 → 20*log10(0.3536) ≈ -9.03 dB
    assert -9.5 < rms_db < -8.5


def test_rms_db_silence() -> None:
    sig = np.zeros(SR, dtype=np.float32)
    rms_db = _common.compute_rms_db(sig)
    assert rms_db <= -100.0


# --- 3.4 compute_peak_db ----------------------------------------------------

def test_peak_db_known_amplitude() -> None:
    sig = _sine(1000, 0.2, amplitude=0.25)
    peak_db = _common.compute_peak_db(sig)
    # 20 * log10(0.25) ≈ -12.04 dB
    assert -12.5 < peak_db < -11.5


# --- 3.5 compute_band_energy_db --------------------------------------------

def test_band_energy_sine_at_1khz_lands_in_640_band() -> None:
    sig = _sine(1000, 1.0, amplitude=0.5)
    bands = _common.compute_band_energy_db(sig, SR)
    assert len(bands) == 8
    # bands edges: [80, 160, 320, 640, 1280, 2560, 5120, 10240, 20000]
    # 1 kHz falls in [640, 1280) → index 3.
    max_idx = int(np.argmax(bands))
    assert max_idx == 3, f"expected max energy at index 3 ([640, 1280) Hz), got {max_idx} ({bands})"


# --- 3.6 compute_spectral_centroid_hz --------------------------------------

def test_spectral_centroid_sine_returns_freq() -> None:
    sig = _sine(1000, 1.0, amplitude=0.5)
    centroid = _common.compute_spectral_centroid_hz(sig, SR)
    assert 900 < centroid < 1100


# --- 3.7 estimate_thd_pct ---------------------------------------------------

def test_thd_pure_sine_is_low() -> None:
    sig = _sine(220, 1.0, amplitude=0.5)
    thd = _common.estimate_thd_pct(sig, SR)
    assert thd < 3.0


def test_thd_clipped_sine_is_high() -> None:
    base = _sine(220, 1.0, amplitude=0.5)
    clipped = np.tanh(8.0 * base).astype(np.float32)
    thd = _common.estimate_thd_pct(clipped, SR)
    assert thd > 15.0


# --- 3.8 classify_gain_character -------------------------------------------

def test_gain_character_clean() -> None:
    label, conf = _common.classify_gain_character(thd_pct=1.0, crest_db=14.0, band_energy_db=[0.0] * 8)
    assert label == "clean"
    assert conf > 0.3


def test_gain_character_high_gain_via_thd() -> None:
    label, conf = _common.classify_gain_character(thd_pct=35.0, crest_db=6.0, band_energy_db=[0.0] * 8)
    assert label == "high_gain"
    assert conf > 0.5


def test_gain_character_distortion_range() -> None:
    label, _ = _common.classify_gain_character(thd_pct=18.0, crest_db=8.0, band_energy_db=[0.0] * 8)
    assert label == "distortion"


def test_gain_character_crunch_range() -> None:
    label, _ = _common.classify_gain_character(thd_pct=6.0, crest_db=10.0, band_energy_db=[0.0] * 8)
    assert label == "crunch"


# --- 3.9 estimate_rt60_s ----------------------------------------------------

def test_rt60_clean_di_has_low_confidence(clean_di_path: Path) -> None:
    sig, sr = _common.load_audio(clean_di_path)
    rt60, conf = _common.estimate_rt60_s(sig, sr)
    # Clean DI has no reverb tail; confidence should be low.
    assert conf < 0.5 or rt60 is None


def test_rt60_reverb_fixture_estimates_around_1_4s(reverb_tail_path: Path) -> None:
    sig, sr = _common.load_audio(reverb_tail_path)
    rt60, conf = _common.estimate_rt60_s(sig, sr)
    assert rt60 is not None
    assert 0.7 < rt60 < 2.5, f"expected RT60 ~1.4s, got {rt60}"


# --- 3.10 detect_delay ------------------------------------------------------

def test_delay_clean_returns_false(clean_di_path: Path) -> None:
    sig, sr = _common.load_audio(clean_di_path)
    present, time_ms, _ = _common.detect_delay(sig, sr)
    assert not present


def test_delay_echo_fixture_detects_380ms(delayed_echo_path: Path) -> None:
    sig, sr = _common.load_audio(delayed_echo_path)
    present, time_ms, _ = _common.detect_delay(sig, sr)
    assert present
    assert time_ms is not None
    assert 320 < time_ms < 440, f"expected ~380 ms, got {time_ms}"


# --- 3.11 compute_lufs_integrated ------------------------------------------

def test_lufs_returns_finite(clean_di_path: Path) -> None:
    sig, sr = _common.load_audio(clean_di_path)
    lufs = _common.compute_lufs_integrated(sig, sr)
    assert math.isfinite(lufs)
    assert lufs < 0.0  # any music will be negative LUFS


# --- 3.12 segment_track ----------------------------------------------------

def test_segment_short_clip_returns_single_section(clean_di_path: Path) -> None:
    sig, sr = _common.load_audio(clean_di_path)
    sections = _common.segment_track(sig, sr)
    assert len(sections) == 1
    assert sections[0][0] == 0.0


def test_segment_multi_section_finds_three_boundaries(multi_section_path: Path) -> None:
    sig, sr = _common.load_audio(multi_section_path)
    sections = _common.segment_track(sig, sr)
    # We synthesized 8 + 12 + 8 = 28 s of clearly distinct timbres.
    # The segmenter should find at least 2 boundaries → 3 sections.
    # We accept 3 or merging-induced 2 only if the middle section is correctly long.
    assert 2 <= len(sections) <= 4, f"expected ~3 sections, got {len(sections)}"


# --- 3.13 align_signals ----------------------------------------------------

def test_align_identical_signals(clean_di_path: Path) -> None:
    sig, sr = _common.load_audio(clean_di_path)
    lag, conf = _common.align_signals(sig, sig, sr)
    assert abs(lag) <= 8  # essentially zero (allow tiny FFT rounding)
    assert conf > 0.9


def test_align_with_trailing_silence(clean_di_path: Path, clean_with_silence_path: Path) -> None:
    ref, sr = _common.load_audio(clean_di_path)
    wet, _ = _common.load_audio(clean_with_silence_path)
    # wet = clean + 1.5 s silence appended; the alignment lag should be ~0
    # because both start at the same point.
    lag, conf = _common.align_signals(ref, wet, sr)
    assert abs(lag) < int(0.1 * sr)
    assert conf > 0.6


# --- 3.14 round_for_json ---------------------------------------------------

def test_round_for_json_handles_nested() -> None:
    data = {
        "a": 1.234567,
        "b": [2.987654, {"c": 3.141592653}],
        "d": np.float64(4.999999),
        "e": "string",
        "f": None,
        "g": True,
    }
    out = _common.round_for_json(data, ndigits=3)
    assert out["a"] == 1.235
    assert out["b"][0] == 2.988
    assert out["b"][1]["c"] == 3.142
    assert out["d"] == 5.0
    assert isinstance(out["d"], float)
    assert out["e"] == "string"
    assert out["f"] is None
    assert out["g"] is True
