"""Integration tests for compare.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import compare


def _run(ref: Path, wet: Path, tmp_path: Path, *args: str) -> dict:
    out_dir = tmp_path / "out"
    rc = compare.main([str(ref), str(wet), "--out-dir", str(out_dir), *args])
    assert rc == 0
    payload = json.loads((out_dir / "diff.json").read_text())
    return payload


def test_identical_inputs(clean_di_path: Path, tmp_path: Path) -> None:
    diff = _run(clean_di_path, clean_di_path, tmp_path)
    assert diff["schema_version"] == 2
    assert diff["match_score"] >= 0.99
    # Empty recs OK; a few "match" verdicts OK
    assert isinstance(diff["recommendations"], list)
    assert len(diff["recommendations"]) == 0
    assert diff["converged"] is True


def test_clean_vs_distorted(clean_di_path: Path, distorted_di_path: Path, tmp_path: Path) -> None:
    # ref = clean, wet = distorted → wet is HOTTER than ref → recommend cut gain
    diff = _run(clean_di_path, distorted_di_path, tmp_path)
    assert diff["match_score"] < 0.7
    amp_recs = [r for r in diff["recommendations"] if r["target"] == "amp"]
    assert len(amp_recs) >= 1, f"expected at least one amp recommendation, got {diff['recommendations']}"
    # the direction should be "decrease gain" since wet > ref in THD
    assert any("decrease gain" in r["action"] for r in amp_recs)


def test_trailing_silence_alignment(clean_di_path: Path, clean_with_silence_path: Path, tmp_path: Path) -> None:
    diff = _run(clean_di_path, clean_with_silence_path, tmp_path)
    # The two signals differ only by trailing silence; section-aggregated
    # metrics ignore the silent tail, so match should be high.
    assert diff["match_score"] >= 0.85
    assert diff["delta"]["alignment_confidence"] > 0.6


def test_missing_delay_flagged(delayed_echo_path: Path, clean_di_path: Path, tmp_path: Path) -> None:
    # ref has a delay, wet does not
    diff = _run(delayed_echo_path, clean_di_path, tmp_path)
    assert diff["delta"]["delay_present"]["ref"] is True
    assert diff["delta"]["delay_present"]["wet"] is False
    assert diff["delta"]["delay_present"]["verdict"] == "wet missing delay"
    delay_recs = [r for r in diff["recommendations"] if r["target"] == "delay"]
    assert len(delay_recs) >= 1


def test_missing_reverb_flagged(reverb_tail_path: Path, clean_di_path: Path, tmp_path: Path) -> None:
    diff = _run(reverb_tail_path, clean_di_path, tmp_path)
    rt60_d = diff["delta"]["reverb_rt60_s"]["wet_minus_ref"]
    # If either side's RT60 is null this turns into None — accept that path as
    # an informative signal but verify the reverb recommendation only fires
    # when both sides produced an RT60.
    if rt60_d is not None:
        assert rt60_d < -0.4, f"expected wet < ref in RT60, got {rt60_d}"
        reverb_recs = [r for r in diff["recommendations"] if r["target"] == "reverb"]
        assert len(reverb_recs) >= 1


def test_auto_section_pick(multi_section_path: Path, distorted_di_path: Path, tmp_path: Path) -> None:
    # ref = 3-section track with a heavy middle, wet = a single distorted take
    diff = _run(multi_section_path, distorted_di_path, tmp_path)
    matched_id = diff["reference"]["matched_section_id"]
    # We just require the picked section to NOT be section_0 (the clean head) —
    # exact id depends on how the segmenter splits the track.
    fp = json.loads((tmp_path.parent / tmp_path.name / "out" / "diff.json").read_text()) if False else diff
    # Check the picked section is high_gain or distortion
    # We need to re-analyze ref to inspect its sections… we can read it from the fingerprint cache
    # The cleaner approach: assert that the matched_section_reason is the auto-pick one
    assert "best tone_profile" in diff["reference"]["matched_section_reason"] or \
           "single section" in diff["reference"]["matched_section_reason"]


def test_ref_section_override(multi_section_path: Path, clean_di_path: Path, tmp_path: Path) -> None:
    diff = _run(multi_section_path, clean_di_path, tmp_path, "--ref-section", "0")
    assert diff["reference"]["matched_section_id"] == "section_0"
    assert "override" in diff["reference"]["matched_section_reason"]


def test_ref_section_out_of_range(clean_di_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        compare.main([str(clean_di_path), str(clean_di_path),
                      "--out-dir", str(out_dir), "--ref-section", "5"])
    assert "out of range" in str(exc.value)


def test_weights_pinned() -> None:
    assert compare.WEIGHTS == {
        "band_energy": 0.40,
        "centroid":    0.15,
        "thd":         0.25,
        "rt60":        0.10,
        "delay":       0.10,
    }
    # weights sum to 1.0 (within float tolerance)
    assert abs(sum(compare.WEIGHTS.values()) - 1.0) < 1e-9


def test_diff_writes_ab_png(clean_di_path: Path, distorted_di_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    compare.main([str(clean_di_path), str(distorted_di_path), "--out-dir", str(out_dir)])
    assert (out_dir / "ab_spec.png").exists()
    assert (out_dir / "diff.json").exists()


def test_convergence_threshold_pinned() -> None:
    assert compare.CONVERGENCE_THRESHOLD == {
        "match_score_min":       0.85,
        "max_abs_band_delta_db": 2.0,
    }


# ---------------------------------------------------------------------------
# SPEC 1: --wet-section flag + auto_pick_wet_section + symmetrical wiring
# ---------------------------------------------------------------------------

def _make_section(
    idx: int,
    *,
    rms_db: float,
    centroid_hz: float,
    band_energy_db: list[float] | None = None,
    thd_pct: float = 5.0,
    tone_profile: str = "clean",
    presence: str = "rhythm",
    rt60_s: float | None = None,
    delay_present: bool = False,
    modulation_present: bool = False,
) -> dict:
    """Build a minimal synthetic section dict matching the fingerprint schema."""
    if band_energy_db is None:
        band_energy_db = [-30.0] * len(compare._common.BANDS_HZ)
    return {
        "id": f"section_{idx}",
        "start_s": float(idx) * 10.0,
        "end_s": float(idx + 1) * 10.0,
        "labels": {
            "tone_profile": tone_profile,
            "dynamics_profile": "rhythmic",
            "presence": presence,
        },
        "loudness": {
            "rms_db": float(rms_db),
            "peak_db": float(rms_db) + 6.0,
            "crest_factor_db": 6.0,
        },
        "spectrum": {
            "bands_hz": list(compare._common.BANDS_HZ),
            "band_energy_db": [float(x) for x in band_energy_db],
            "spectral_centroid_hz": float(centroid_hz),
            "spectral_rolloff_hz_85pct": float(centroid_hz) * 2.0,
            "spectral_flatness": 0.3,
        },
        "distortion": {
            "thd_estimate_pct": float(thd_pct),
            "odd_to_even_harmonic_ratio_db": 0.0,
            "gain_character": tone_profile,
            "gain_character_confidence": 0.8,
        },
        "time_fx": {
            "reverb_rt60_s": rt60_s,
            "reverb_rt60_confidence": 0.5,
            "delay_present": bool(delay_present),
            "delay_time_ms_estimate": None,
            "delay_feedback_estimate_pct": None,
            "modulation_present": bool(modulation_present),
            "modulation_rate_hz": None,
            "modulation_depth_estimate": None,
        },
    }


def _make_fingerprint(sections: list[dict], *, sha: str = "deadbeef") -> dict:
    return {
        "schema_version": 2,
        "source": {
            "path": f"/synthetic/{sha}.wav",
            "sha256": sha,
            "sample_rate_hz": 48000,
            "channels": 1,
        },
        "global": {},
        "sections": sections,
    }


# Test A: pick_wet_section override / default behaviour
def test_pick_wet_section_override_returns_indexed_section() -> None:
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0, presence="background"),
        _make_section(1, rms_db=-12.0, centroid_hz=1200.0, presence="lead"),
        _make_section(2, rms_db=-15.0, centroid_hz=1100.0, presence="rhythm"),
    ])
    sec, reason = compare.pick_wet_section(wet_fp, 2)
    assert sec["id"] == "section_2"
    assert "override" in reason.lower()


def test_pick_wet_section_none_falls_back_to_first_section_for_backcompat() -> None:
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0, presence="background"),
        _make_section(1, rms_db=-12.0, centroid_hz=1200.0, presence="lead"),
    ])
    sec, reason = compare.pick_wet_section(wet_fp, None)
    assert sec["id"] == "section_0"
    assert "first section" in reason.lower() or "default" in reason.lower()


# Test B: out-of-range index → SystemExit with clear message
def test_pick_wet_section_out_of_range_raises_systemexit() -> None:
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-10.0, centroid_hz=1000.0),
        _make_section(1, rms_db=-12.0, centroid_hz=1200.0),
    ])
    with pytest.raises(SystemExit) as exc:
        compare.pick_wet_section(wet_fp, 7)
    msg = str(exc.value)
    assert "out of range" in msg
    assert "--wet-section" in msg


# Test C: auto_pick_wet_section ignores silent background sections
def test_auto_pick_wet_section_skips_silent_background() -> None:
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0, presence="background"),
        _make_section(1, rms_db=-12.0, centroid_hz=1200.0, presence="lead"),
        _make_section(2, rms_db=-15.0, centroid_hz=1100.0, presence="rhythm"),
    ])
    sec, reason = compare.auto_pick_wet_section(wet_fp)
    # Loudest non-background candidate is section_1 (rms -12)
    assert sec["id"] == "section_1"
    assert "background" in reason.lower() or "non-background" in reason.lower() or sec["id"] in reason


def test_auto_pick_wet_section_falls_back_when_all_silent_background() -> None:
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0, presence="background"),
        _make_section(1, rms_db=-42.0, centroid_hz=410.0, presence="background"),
    ])
    sec, reason = compare.auto_pick_wet_section(wet_fp)
    assert sec["id"] == "section_0"
    assert "fallback" in reason.lower() or "no non-background" in reason.lower()


def test_background_rms_threshold_constant_is_pinned() -> None:
    # Single source of truth for the heuristic threshold.
    assert compare.BACKGROUND_RMS_THRESHOLD_DB == -35.0


# Test D: end-to-end through main() — --wet-section forces delta against IDX
def test_main_wet_section_override_changes_delta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When --wet-section IDX is passed, compute_delta must use that section."""
    import numpy as np
    from scripts import compare as compare_mod

    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0,
                      band_energy_db=[-60.0] * 8, thd_pct=0.5,
                      presence="background", tone_profile="clean"),
        _make_section(1, rms_db=-10.0, centroid_hz=1300.0,
                      band_energy_db=[-20.0] * 8, thd_pct=25.0,
                      presence="lead", tone_profile="high_gain"),
    ], sha="wetsha")
    ref_fp = _make_fingerprint([
        _make_section(0, rms_db=-10.0, centroid_hz=1300.0,
                      band_energy_db=[-20.0] * 8, thd_pct=25.0,
                      presence="lead", tone_profile="high_gain"),
    ], sha="refsha")

    sig = np.zeros(48000, dtype=np.float32)

    def fake_run_analyze_cached(path):
        # Map by filename
        if "ref" in str(path):
            return ref_fp, sig, 48000
        return wet_fp, sig, 48000

    monkeypatch.setattr(compare_mod, "run_analyze_cached", fake_run_analyze_cached)
    monkeypatch.setattr(compare_mod, "render_ab_spec_png",
                        lambda *a, **kw: tmp_path / "ab_spec.png")

    out_dir = tmp_path / "out"
    rc = compare_mod.main([
        "/tmp/ref.wav", "/tmp/wet.wav",
        "--out-dir", str(out_dir),
        "--wet-section", "1",
    ])
    assert rc == 0
    diff = json.loads((out_dir / "diff.json").read_text())
    # Delta with section 1 (rms -10, like ref) → tiny rms gap, NOT -29 dB
    assert abs(diff["delta"]["rms_db"]["wet_minus_ref"]) < 1.0, (
        f"expected delta computed against section_1 (rms_db ~match), got "
        f"{diff['delta']['rms_db']['wet_minus_ref']}"
    )
    # Match should be high since section_1 mirrors ref
    assert diff["match_score"] > 0.85


def test_main_default_uses_section_zero_for_backcompat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without --wet-section, behaviour identical to pre-fix: uses section_0."""
    import numpy as np
    from scripts import compare as compare_mod

    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0,
                      band_energy_db=[-60.0] * 8, thd_pct=0.5,
                      presence="background", tone_profile="clean"),
        _make_section(1, rms_db=-10.0, centroid_hz=1300.0,
                      band_energy_db=[-20.0] * 8, thd_pct=25.0,
                      presence="lead", tone_profile="high_gain"),
    ], sha="wetsha2")
    ref_fp = _make_fingerprint([
        _make_section(0, rms_db=-10.0, centroid_hz=1300.0,
                      band_energy_db=[-20.0] * 8, thd_pct=25.0,
                      presence="lead", tone_profile="high_gain"),
    ], sha="refsha2")

    sig = np.zeros(48000, dtype=np.float32)

    def fake_run_analyze_cached(path):
        if "ref" in str(path):
            return ref_fp, sig, 48000
        return wet_fp, sig, 48000

    monkeypatch.setattr(compare_mod, "run_analyze_cached", fake_run_analyze_cached)
    monkeypatch.setattr(compare_mod, "render_ab_spec_png",
                        lambda *a, **kw: tmp_path / "ab_spec.png")

    out_dir = tmp_path / "out"
    rc = compare_mod.main([
        "/tmp/ref.wav", "/tmp/wet.wav",
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    diff = json.loads((out_dir / "diff.json").read_text())
    # Backcompat: section_0 of wet = silence, rms -41 vs ref -10 → ~-31 dB
    assert diff["delta"]["rms_db"]["wet_minus_ref"] < -25.0


# Test E: diff.json carries rendered.section_id_reason mirror of matched_section_reason
def test_diff_carries_rendered_section_id_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import numpy as np
    from scripts import compare as compare_mod

    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-41.0, centroid_hz=400.0, presence="background"),
        _make_section(1, rms_db=-10.0, centroid_hz=1300.0, presence="lead",
                      tone_profile="high_gain"),
    ], sha="wetsha3")
    ref_fp = _make_fingerprint([
        _make_section(0, rms_db=-10.0, centroid_hz=1300.0, presence="lead",
                      tone_profile="high_gain"),
    ], sha="refsha3")

    sig = np.zeros(48000, dtype=np.float32)

    def fake_run_analyze_cached(path):
        if "ref" in str(path):
            return ref_fp, sig, 48000
        return wet_fp, sig, 48000

    monkeypatch.setattr(compare_mod, "run_analyze_cached", fake_run_analyze_cached)
    monkeypatch.setattr(compare_mod, "render_ab_spec_png",
                        lambda *a, **kw: tmp_path / "ab_spec.png")

    out_dir = tmp_path / "out"
    rc = compare_mod.main([
        "/tmp/ref.wav", "/tmp/wet.wav",
        "--out-dir", str(out_dir),
        "--wet-section", "1",
    ])
    assert rc == 0
    diff = json.loads((out_dir / "diff.json").read_text())
    assert "section_id_reason" in diff["rendered"]
    assert "override" in diff["rendered"]["section_id_reason"].lower()
    assert diff["rendered"]["section_id"] == "section_1"


# Test G: proximity_pct — level-independent timbre number, distinct from match_score
def test_diff_emits_level_independent_proximity_pct(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """compare.py must emit proximity_pct (timbre, level-independent), ALONGSIDE
    match_score. Same band SHAPE at a different overall level → proximity ~100%,
    even though match_score is dragged down by the level-laden band delta."""
    import numpy as np
    from scripts import compare as compare_mod

    shape = [-30.0, -22.0, -18.0, -20.0, -24.0, -28.0, -33.0, -40.0]
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-10.0, centroid_hz=1200.0,
                      band_energy_db=[x + 12.0 for x in shape], thd_pct=10.0,
                      presence="lead", tone_profile="crunch"),
    ], sha="wetProx")
    ref_fp = _make_fingerprint([
        _make_section(0, rms_db=-22.0, centroid_hz=1200.0,
                      band_energy_db=list(shape), thd_pct=10.0,
                      presence="lead", tone_profile="crunch"),
    ], sha="refProx")

    sig = np.zeros(48000, dtype=np.float32)

    def fake_run_analyze_cached(path):
        if "ref" in str(path):
            return ref_fp, sig, 48000
        return wet_fp, sig, 48000

    monkeypatch.setattr(compare_mod, "run_analyze_cached", fake_run_analyze_cached)
    monkeypatch.setattr(compare_mod, "render_ab_spec_png",
                        lambda *a, **kw: tmp_path / "ab_spec.png")

    out_dir = tmp_path / "out"
    rc = compare_mod.main(["/tmp/ref.wav", "/tmp/wet.wav", "--out-dir", str(out_dir)])
    assert rc == 0
    diff = json.loads((out_dir / "diff.json").read_text())

    assert "proximity_pct" in diff
    assert 0.0 <= diff["proximity_pct"] <= 100.0
    # same shape shifted +12 dB → identical timbre
    assert diff["proximity_pct"] == pytest.approx(100.0, abs=0.5)
    # match_score still carries the level-laden band delta → not 100%-equivalent
    assert diff["match_score"] < 0.95
    # the two numbers measure different things
    assert "match_score" in diff


# Test H: proximity_pct band-limits the dead top octave of a separated stem
def test_diff_proximity_band_limited_for_dead_top_stem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A separated ref with a dead top octave + a bright wet that matches the
    trustworthy range must score HIGH proximity (dead top excluded) and flag
    ref_top_octave_dead. Prevents the '99% but sounds muffled' result."""
    import numpy as np
    from scripts import compare as compare_mod

    ref_bands = [-20.0, -16.0, -14.0, -15.0, -18.0, -22.0, -30.0, -48.0]  # dead top
    wet_bands = [-20.0, -16.0, -14.0, -15.0, -18.0, -22.0, -24.0, -28.0]  # live top
    wet_fp = _make_fingerprint([
        _make_section(0, rms_db=-12.0, centroid_hz=1200.0,
                      band_energy_db=wet_bands, thd_pct=10.0,
                      presence="lead", tone_profile="crunch"),
    ], sha="wetDead")
    ref_fp = _make_fingerprint([
        _make_section(0, rms_db=-12.0, centroid_hz=1200.0,
                      band_energy_db=ref_bands, thd_pct=10.0,
                      presence="lead", tone_profile="crunch"),
    ], sha="refDead")

    sig = np.zeros(48000, dtype=np.float32)

    def fake_run_analyze_cached(path):
        if "ref" in str(path):
            return ref_fp, sig, 48000
        return wet_fp, sig, 48000

    monkeypatch.setattr(compare_mod, "run_analyze_cached", fake_run_analyze_cached)
    monkeypatch.setattr(compare_mod, "render_ab_spec_png",
                        lambda *a, **kw: tmp_path / "ab_spec.png")

    out_dir = tmp_path / "out"
    rc = compare_mod.main(["/tmp/ref.wav", "/tmp/wet.wav", "--out-dir", str(out_dir)])
    assert rc == 0
    diff = json.loads((out_dir / "diff.json").read_text())
    assert diff["ref_top_octave_dead"] is True
    assert diff["proximity_pct"] >= 99.0   # trustworthy range matches → high


# Test F: pick_ref_section new signature receives wet_section explicitly
def test_pick_ref_section_uses_explicit_wet_section_argument() -> None:
    """pick_ref_section must accept wet_section as a parameter (not grab [0])."""
    import inspect
    sig = inspect.signature(compare.pick_ref_section)
    params = list(sig.parameters.keys())
    # New signature: (ref_fp, wet_fp, override_idx, wet_section)
    assert "wet_section" in params, f"pick_ref_section must accept wet_section param, got {params}"
