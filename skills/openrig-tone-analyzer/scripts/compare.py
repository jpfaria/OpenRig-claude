#!/usr/bin/env python3
"""Compare a reference WAV with a wet/rendered WAV: emit diff.json + ab_spec.png.

Auto-picks the reference section whose tone profile best matches the wet's
primary section (override with --ref-section IDX). The diff is computed
against that single section. Recommendations are sorted by priority and
target a fixed enum of block kinds the orchestrator knows how to dispatch.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common, analyze  # noqa: E402

SCHEMA_VERSION = 2

WEIGHTS = {
    "band_energy": 0.40,
    "centroid":    0.15,
    "thd":         0.25,
    "rt60":        0.10,
    "delay":       0.10,
}

NORMALIZATION = {
    "band_energy_db": 12.0,
    "centroid_hz":    1500.0,
    "thd_pct":        20.0,
    "rt60_s":         2.0,
}

CONVERGENCE_THRESHOLD = {
    "match_score_min":         0.85,
    "max_abs_band_delta_db":   2.0,
}

CACHE_DIR = Path("/tmp/openrig-analyzer-cache")


def _seed_everything(seed: int = _common.SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)


# ---------------------------------------------------------------------------
# Cached analyze
# ---------------------------------------------------------------------------

def run_analyze_cached(path: Path) -> tuple[dict[str, Any], np.ndarray, int]:
    """Run analyze on path, returning (fingerprint, signal, sr).

    Uses a sha256-keyed cache for the fingerprint JSON to avoid re-running
    the spectrogram pipeline on repeated comparisons.
    """
    sha = _common.sha256_file(path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{sha}.json"

    signal, sr = _common.load_audio(path)
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("source", {}).get("sha256") == sha:
                return cached, signal, sr
        except Exception:
            pass

    fingerprint = analyze.build_fingerprint(path, signal, sr)
    cache_path.write_text(json.dumps(fingerprint, indent=2, sort_keys=True), encoding="utf-8")
    return fingerprint, signal, sr


# ---------------------------------------------------------------------------
# Section picking
# ---------------------------------------------------------------------------

def _section_similarity_no_timefx(ref_sec: dict, wet_sec: dict) -> float:
    """Similarity in [0,1] using only band_energy + centroid + thd terms."""
    ref_bands = np.array(ref_sec["spectrum"]["band_energy_db"], dtype=np.float64)
    wet_bands = np.array(wet_sec["spectrum"]["band_energy_db"], dtype=np.float64)
    band_rms = float(np.sqrt(np.mean((ref_bands - wet_bands) ** 2)))
    band_term = 1.0 - min(1.0, band_rms / NORMALIZATION["band_energy_db"])

    centroid_delta = abs(
        ref_sec["spectrum"]["spectral_centroid_hz"]
        - wet_sec["spectrum"]["spectral_centroid_hz"]
    )
    centroid_term = 1.0 - min(1.0, centroid_delta / NORMALIZATION["centroid_hz"])

    thd_delta = abs(
        ref_sec["distortion"]["thd_estimate_pct"]
        - wet_sec["distortion"]["thd_estimate_pct"]
    )
    thd_term = 1.0 - min(1.0, thd_delta / NORMALIZATION["thd_pct"])

    # rebalance weights since rt60+delay are dropped
    w_band, w_cent, w_thd = 0.50, 0.20, 0.30
    return float(w_band * band_term + w_cent * centroid_term + w_thd * thd_term)


def pick_ref_section(ref_fp: dict, wet_fp: dict, override_idx: int | None) -> tuple[dict, str]:
    wet_section = wet_fp["sections"][0]
    if override_idx is not None:
        if override_idx < 0 or override_idx >= len(ref_fp["sections"]):
            raise SystemExit(
                f"--ref-section {override_idx} out of range (have 0..{len(ref_fp['sections']) - 1})"
            )
        sec = ref_fp["sections"][override_idx]
        return sec, "user override via --ref-section"

    if len(ref_fp["sections"]) == 1:
        return ref_fp["sections"][0], "ref has a single section"

    scored = []
    for sec in ref_fp["sections"]:
        score = _section_similarity_no_timefx(sec, wet_section)
        # tie-break boost when tone_profile matches exactly
        if sec["labels"]["tone_profile"] == wet_section["labels"]["tone_profile"]:
            score += 0.05
        scored.append((sec, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0][0]
    return best, "best tone_profile + spectral match to wet"


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def _verdict_db(delta: float, asc_word: str, desc_word: str, near_thresh: float = 0.5) -> str:
    if abs(delta) <= near_thresh:
        return "match"
    return desc_word if delta > 0 else asc_word


def compute_delta(ref_sec: dict, wet_sec: dict, alignment_confidence: float) -> dict[str, Any]:
    rms_d = wet_sec["loudness"]["rms_db"] - ref_sec["loudness"]["rms_db"]
    centroid_d = wet_sec["spectrum"]["spectral_centroid_hz"] - ref_sec["spectrum"]["spectral_centroid_hz"]
    bands = []
    for i, band_hz in enumerate(_common.BANDS_HZ):
        delta_db = wet_sec["spectrum"]["band_energy_db"][i] - ref_sec["spectrum"]["band_energy_db"][i]
        bands.append({"band_hz": int(band_hz), "delta_db": float(delta_db)})
    thd_d = wet_sec["distortion"]["thd_estimate_pct"] - ref_sec["distortion"]["thd_estimate_pct"]
    ref_rt60 = ref_sec["time_fx"]["reverb_rt60_s"]
    wet_rt60 = wet_sec["time_fx"]["reverb_rt60_s"]
    rt60_d = None
    if ref_rt60 is not None and wet_rt60 is not None:
        rt60_d = wet_rt60 - ref_rt60

    return {
        "rms_db": {
            "wet_minus_ref": float(rms_d),
            "verdict": _verdict_db(rms_d, "wet quieter", "wet louder", near_thresh=0.5),
        },
        "spectral_centroid_hz": {
            "wet_minus_ref": float(centroid_d),
            "verdict": _verdict_db(centroid_d, "wet darker", "wet brighter", near_thresh=80.0),
        },
        "band_energy_db": bands,
        "thd_estimate_pct": {
            "wet_minus_ref": float(thd_d),
            "verdict": _verdict_db(thd_d, "wet less distorted", "wet more distorted", near_thresh=1.0),
        },
        "reverb_rt60_s": {
            "wet_minus_ref": float(rt60_d) if rt60_d is not None else None,
            "verdict": (
                "match" if rt60_d is None
                else _verdict_db(rt60_d, "wet shorter tail", "wet longer tail", near_thresh=0.2)
            ),
        },
        "delay_present": {
            "ref": bool(ref_sec["time_fx"]["delay_present"]),
            "wet": bool(wet_sec["time_fx"]["delay_present"]),
            "verdict": _delay_verdict(
                ref_sec["time_fx"]["delay_present"], wet_sec["time_fx"]["delay_present"]
            ),
        },
        "modulation_present": {
            "ref": bool(ref_sec["time_fx"]["modulation_present"]),
            "wet": bool(wet_sec["time_fx"]["modulation_present"]),
            "verdict": _mod_verdict(
                ref_sec["time_fx"]["modulation_present"], wet_sec["time_fx"]["modulation_present"]
            ),
        },
        "alignment_confidence": float(alignment_confidence),
    }


def _delay_verdict(ref: bool, wet: bool) -> str:
    if ref and not wet:
        return "wet missing delay"
    if wet and not ref:
        return "wet has extra delay"
    return "ok"


def _mod_verdict(ref: bool, wet: bool) -> str:
    if ref and not wet:
        return "wet missing modulation"
    if wet and not ref:
        return "wet has extra modulation"
    return "ok"


def compute_match_score(delta: dict) -> float:
    band_deltas = np.array([b["delta_db"] for b in delta["band_energy_db"]], dtype=np.float64)
    band_rms = float(np.sqrt(np.mean(band_deltas ** 2)))
    band_term = 1.0 - min(1.0, band_rms / NORMALIZATION["band_energy_db"])

    centroid_term = 1.0 - min(1.0, abs(delta["spectral_centroid_hz"]["wet_minus_ref"]) / NORMALIZATION["centroid_hz"])
    thd_term = 1.0 - min(1.0, abs(delta["thd_estimate_pct"]["wet_minus_ref"]) / NORMALIZATION["thd_pct"])

    rt60_d = delta["reverb_rt60_s"]["wet_minus_ref"]
    rt60_term = 1.0 if rt60_d is None else 1.0 - min(1.0, abs(rt60_d) / NORMALIZATION["rt60_s"])

    delay_match = delta["delay_present"]["ref"] == delta["delay_present"]["wet"]
    delay_term = 1.0 if delay_match else 0.0

    score = (
        WEIGHTS["band_energy"] * band_term
        + WEIGHTS["centroid"] * centroid_term
        + WEIGHTS["thd"] * thd_term
        + WEIGHTS["rt60"] * rt60_term
        + WEIGHTS["delay"] * delay_term
    )
    return float(max(0.0, min(1.0, score)))


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def build_recommendations(delta: dict, ref_sec: dict, wet_sec: dict) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    thd_d = delta["thd_estimate_pct"]["wet_minus_ref"]
    if abs(thd_d) > 3.0:
        if thd_d < 0:
            pct = int(round(min(50, max(5, abs(thd_d) * 4))))
            recs.append({
                "target": "amp",
                "action": f"increase gain by ~{pct}%",
                "rationale": f"THD lower by {abs(thd_d):.1f} pts — wet is cleaner than ref",
            })
        else:
            pct = int(round(min(50, max(5, thd_d * 4))))
            recs.append({
                "target": "amp",
                "action": f"decrease gain by ~{pct}%",
                "rationale": f"THD higher by {thd_d:.1f} pts — wet is hotter than ref",
            })

    # band-energy deltas → EQ recommendation on the worst band
    band_deltas = [(b["band_hz"], b["delta_db"]) for b in delta["band_energy_db"]]
    band_deltas.sort(key=lambda x: abs(x[1]), reverse=True)
    if band_deltas and abs(band_deltas[0][1]) > 2.0:
        worst_hz, worst_d = band_deltas[0]
        if worst_d < 0:
            recs.append({
                "target": "eq_eight_band_parametric",
                "action": f"boost {worst_hz} Hz band by +{abs(worst_d):.1f} dB (Q ~1.0)",
                "rationale": f"energy deficit of {abs(worst_d):.1f} dB at {worst_hz} Hz",
            })
        else:
            recs.append({
                "target": "eq_eight_band_parametric",
                "action": f"cut {worst_hz} Hz band by -{worst_d:.1f} dB (Q ~1.0)",
                "rationale": f"energy excess of {worst_d:.1f} dB at {worst_hz} Hz",
            })

    if delta["delay_present"]["ref"] and not delta["delay_present"]["wet"]:
        time_ms = ref_sec["time_fx"]["delay_time_ms_estimate"]
        fb = ref_sec["time_fx"]["delay_feedback_estimate_pct"]
        recs.append({
            "target": "delay",
            "action": (
                f"enable delay block, time ~{int(time_ms) if time_ms else 380} ms, "
                f"feedback ~{int(fb) if fb else 25}%, mix ~15%"
            ),
            "rationale": "reference shows periodic echo; wet has none",
        })

    rt60_d = delta["reverb_rt60_s"]["wet_minus_ref"]
    if rt60_d is not None and abs(rt60_d) > 0.5:
        if rt60_d < 0:
            recs.append({
                "target": "reverb",
                "action": f"increase room_size to extend tail by ~{abs(rt60_d):.1f} s",
                "rationale": f"RT60 deficit of {abs(rt60_d):.1f} s",
            })
        else:
            recs.append({
                "target": "reverb",
                "action": f"reduce room_size to shorten tail by ~{rt60_d:.1f} s",
                "rationale": f"RT60 excess of {rt60_d:.1f} s",
            })

    # Order: amp first, then EQ, then time-FX
    target_priority = {"amp": 1, "eq_eight_band_parametric": 2, "delay": 3, "reverb": 4}
    recs.sort(key=lambda r: target_priority.get(r["target"], 99))
    for i, r in enumerate(recs, start=1):
        r["priority"] = i
    # re-key with priority first
    return [
        {"priority": r["priority"], "target": r["target"], "action": r["action"], "rationale": r["rationale"]}
        for r in recs
    ]


def assemble_diff(
    ref_fp: dict,
    wet_fp: dict,
    matched_section: dict,
    matched_reason: str,
    delta: dict,
    match_score: float,
    recommendations: list[dict],
) -> dict[str, Any]:
    band_deltas = [abs(b["delta_db"]) for b in delta["band_energy_db"]]
    max_band_delta = max(band_deltas) if band_deltas else 0.0
    converged = (
        match_score >= CONVERGENCE_THRESHOLD["match_score_min"]
        and max_band_delta <= CONVERGENCE_THRESHOLD["max_abs_band_delta_db"]
    )

    diff = {
        "schema_version": SCHEMA_VERSION,
        "reference": {
            "fingerprint_sha256": ref_fp["source"]["sha256"],
            "matched_section_id": matched_section["id"],
            "matched_section_reason": matched_reason,
        },
        "rendered": {
            "fingerprint_sha256": wet_fp["source"]["sha256"],
            "section_id": wet_fp["sections"][0]["id"],
        },
        "match_score": float(match_score),
        "delta": delta,
        "recommendations": recommendations,
        "converged": bool(converged),
        "convergence_threshold": dict(CONVERGENCE_THRESHOLD),
    }
    return _common.round_for_json(diff, ndigits=4)


# ---------------------------------------------------------------------------
# A/B PNG
# ---------------------------------------------------------------------------

def render_ab_spec_png(
    ref_signal: np.ndarray,
    ref_sr: int,
    ref_section: dict,
    wet_signal: np.ndarray,
    wet_sr: int,
    wet_section: dict,
    out_dir: Path,
) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa
    import librosa.display

    def slice_section(sig, sr, start_s, end_s):
        a = int(start_s * sr)
        b = int(end_s * sr)
        return _common.mono_mixdown(sig[a:b] if sig.ndim == 1 else sig[:, a:b])

    ref_slice = slice_section(ref_signal, ref_sr, ref_section["start_s"], ref_section["end_s"])
    wet_slice = slice_section(wet_signal, wet_sr, wet_section["start_s"], wet_section["end_s"])

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=100)

    def mel_db(sig, sr):
        if len(sig) == 0:
            sig = np.zeros(sr, dtype=np.float64)
        mel = librosa.feature.melspectrogram(y=sig.astype(np.float64), sr=sr, n_mels=128, fmax=sr / 2)
        return librosa.power_to_db(mel, ref=np.max)

    ref_mel = mel_db(ref_slice, ref_sr)
    wet_mel = mel_db(wet_slice, wet_sr)

    vmin = min(ref_mel.min(), wet_mel.min())
    vmax = max(ref_mel.max(), wet_mel.max())

    librosa.display.specshow(
        ref_mel, sr=ref_sr, x_axis="time", y_axis="mel", fmax=ref_sr / 2,
        ax=axes[0], cmap="magma", vmin=vmin, vmax=vmax,
    )
    axes[0].set_title(f"REF — {ref_section['id']} ({ref_section['labels']['tone_profile']})")

    img = librosa.display.specshow(
        wet_mel, sr=wet_sr, x_axis="time", y_axis="mel", fmax=wet_sr / 2,
        ax=axes[1], cmap="magma", vmin=vmin, vmax=vmax,
    )
    axes[1].set_title(f"WET — {wet_section['id']} ({wet_section['labels']['tone_profile']})")

    fig.colorbar(img, ax=axes, format="%+2.0f dB")
    output = out_dir / "ab_spec.png"
    fig.savefig(output, dpi=100, bbox_inches="tight")
    plt.close(fig)
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_diff_json(diff: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "diff.json"
    path.write_text(json.dumps(diff, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B compare a reference WAV with a wet WAV.")
    parser.add_argument("reference", help="path to reference WAV")
    parser.add_argument("wet", help="path to wet/rendered WAV")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--ref-section", type=int, default=None,
                        help="force a specific reference section index (overrides auto-pick)")
    args = parser.parse_args(argv)

    _seed_everything()

    ref_path = Path(args.reference).expanduser().resolve()
    wet_path = Path(args.wet).expanduser().resolve()

    ref_fp, ref_signal, ref_sr = run_analyze_cached(ref_path)
    wet_fp, wet_signal, wet_sr = run_analyze_cached(wet_path)

    if not wet_fp["sections"]:
        raise SystemExit("wet file has no detectable sections")

    matched_section, matched_reason = pick_ref_section(ref_fp, wet_fp, args.ref_section)

    # alignment for time-domain confidence (advisory; deltas remain section-aggregated)
    lag, align_conf = _common.align_signals(ref_signal, wet_signal, ref_sr)

    wet_section = wet_fp["sections"][0]
    delta = compute_delta(matched_section, wet_section, align_conf)
    match_score = compute_match_score(delta)
    recommendations = build_recommendations(delta, matched_section, wet_section)
    diff = assemble_diff(ref_fp, wet_fp, matched_section, matched_reason,
                         delta, match_score, recommendations)

    out_dir = analyze.resolve_out_dir(args.out_dir)
    write_diff_json(diff, out_dir)
    render_ab_spec_png(ref_signal, ref_sr, matched_section, wet_signal, wet_sr, wet_section, out_dir)

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
