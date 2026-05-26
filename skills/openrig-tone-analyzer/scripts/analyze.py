#!/usr/bin/env python3
"""Analyze a single WAV file: emit fingerprint.json + spectrogram PNGs.

Pure function: in = audio path, out = JSON + PNGs on disk. No network, no
MCP, no project mutation. The output directory is printed on the last line.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# Allow `python scripts/analyze.py` invocation from anywhere by adjusting path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common  # noqa: E402

SCHEMA_VERSION = 2


def _seed_everything(seed: int = _common.SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)


def _slice_signal(signal: np.ndarray, sr: int, start_s: float, end_s: float) -> np.ndarray:
    start = int(start_s * sr)
    end = int(end_s * sr)
    if signal.ndim == 1:
        return signal[start:end]
    return signal[:, start:end]


def _build_section_fingerprint(
    signal_section: np.ndarray,
    sr: int,
    start_s: float,
    end_s: float,
    index: int,
    track_loudest_rms_db: float,
) -> dict[str, Any]:
    rms_db = _common.compute_rms_db(signal_section)
    peak_db = _common.compute_peak_db(signal_section)
    crest_db = _common.compute_crest_factor_db(signal_section)
    band_energy = _common.compute_band_energy_db(signal_section, sr)
    centroid = _common.compute_spectral_centroid_hz(signal_section, sr)
    rolloff = _common.compute_spectral_rolloff_hz(signal_section, sr)
    flatness = _common.compute_spectral_flatness(signal_section, sr)
    thd = _common.estimate_thd_pct(signal_section, sr)
    odd_even = _common.compute_odd_even_harmonic_ratio_db(signal_section, sr)
    tone_profile, tone_conf = _common.classify_gain_character(thd, crest_db, band_energy)
    rt60, rt60_conf = _common.estimate_rt60_s(signal_section, sr)
    delay_present, delay_time, delay_fb = _common.detect_delay(signal_section, sr)
    mod_present, mod_rate, mod_depth = _common.detect_modulation(signal_section, sr)

    onset_rate = _common.compute_onset_rate_per_s(signal_section, sr)
    rms_variance = _common.compute_rms_variance_db(signal_section, sr)
    labels = _common.label_section(
        rms_db=rms_db,
        crest_db=crest_db,
        onset_rate_per_s=onset_rate,
        rms_variance_db=rms_variance,
        tone_profile=tone_profile,
        track_loudest_rms_db=track_loudest_rms_db,
    )

    return {
        "id": f"section_{index}",
        "start_s": float(start_s),
        "end_s": float(end_s),
        "labels": labels,
        "loudness": {
            "rms_db": float(rms_db),
            "peak_db": float(peak_db),
            "crest_factor_db": float(crest_db),
        },
        "spectrum": {
            "bands_hz": list(_common.BANDS_HZ),
            "band_energy_db": [float(x) for x in band_energy],
            "spectral_centroid_hz": float(centroid),
            "spectral_rolloff_hz_85pct": float(rolloff),
            "spectral_flatness": float(flatness),
        },
        "distortion": {
            "thd_estimate_pct": float(thd),
            "odd_to_even_harmonic_ratio_db": float(odd_even),
            "gain_character": tone_profile,
            "gain_character_confidence": float(tone_conf),
        },
        "time_fx": {
            "reverb_rt60_s": float(rt60) if rt60 is not None else None,
            "reverb_rt60_confidence": float(rt60_conf),
            "delay_present": bool(delay_present),
            "delay_time_ms_estimate": int(delay_time) if delay_time is not None else None,
            "delay_feedback_estimate_pct": int(delay_fb) if delay_fb is not None else None,
            "modulation_present": bool(mod_present),
            "modulation_rate_hz": float(mod_rate) if mod_rate is not None else None,
            "modulation_depth_estimate": float(mod_depth) if mod_depth is not None else None,
        },
    }


def build_fingerprint(audio_path: Path, signal: np.ndarray, sr: int) -> dict[str, Any]:
    sections_ranges = _common.segment_track(signal, sr)
    n_channels = 1 if signal.ndim == 1 else signal.shape[0]
    duration_s = signal.shape[-1] / sr

    # Compute each section's RMS first to find the loudest (needed for relative
    # `presence` labels).
    section_signals = []
    section_rms = []
    for (start, end) in sections_ranges:
        sec = _slice_signal(signal, sr, start, end)
        section_signals.append(sec)
        section_rms.append(_common.compute_rms_db(sec))
    track_loudest_rms_db = float(max(section_rms))

    sections = []
    for i, ((start, end), sec) in enumerate(zip(sections_ranges, section_signals)):
        sections.append(
            _build_section_fingerprint(sec, sr, start, end, i, track_loudest_rms_db)
        )

    fingerprint = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "path": str(audio_path.resolve()),
            "sha256": _common.sha256_file(audio_path),
            "sample_rate_hz": int(sr),
            "channels": int(n_channels),
            "duration_s": float(duration_s),
        },
        "global": {
            "lufs_integrated": _common.compute_lufs_integrated(signal, sr),
            "peak_db": _common.compute_peak_db(signal),
            "stereo": _common.compute_stereo_features(signal),
        },
        "sections": sections,
    }
    return _common.round_for_json(fingerprint, ndigits=4)


# ---------------------------------------------------------------------------
# PNG rendering
# ---------------------------------------------------------------------------

def _render_specshow(
    signal: np.ndarray,
    sr: int,
    output_path: Path,
    title: str,
    section_boundaries: list[float] | None = None,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa
    import librosa.display

    sig = _common.mono_mixdown(signal).astype(np.float64)
    if len(sig) == 0:
        sig = np.zeros(sr, dtype=np.float64)
    # mel spectrogram
    mel = librosa.feature.melspectrogram(y=sig, sr=sr, n_mels=128, fmax=sr / 2)
    mel_db = librosa.power_to_db(mel, ref=np.max)

    fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
    img = librosa.display.specshow(
        mel_db,
        sr=sr,
        x_axis="time",
        y_axis="mel",
        fmax=sr / 2,
        ax=ax,
        cmap="magma",
    )
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set_title(title)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")

    if section_boundaries:
        for b in section_boundaries:
            if 0 < b < len(sig) / sr:
                ax.axvline(b, color="cyan", linestyle="--", linewidth=1.0, alpha=0.8)

    fig.tight_layout()
    fig.savefig(output_path, dpi=100)
    plt.close(fig)


def render_spec_global_png(
    signal: np.ndarray,
    sr: int,
    sections: list[tuple[float, float]],
    audio_path: Path,
    out_dir: Path,
) -> Path:
    output = out_dir / "spec_global.png"
    boundaries = [end for (_, end) in sections[:-1]]  # internal boundaries only
    _render_specshow(
        signal,
        sr,
        output,
        title=f"{audio_path.name} — global ({len(sections)} sections)",
        section_boundaries=boundaries,
    )
    return output


def render_spec_section_png(
    signal: np.ndarray,
    sr: int,
    section_start_s: float,
    section_end_s: float,
    section_id: str,
    audio_path: Path,
    out_dir: Path,
) -> Path:
    # focus on the loudest 4 s subwindow of the section (or the whole section if shorter)
    sec = _slice_signal(signal, sr, section_start_s, section_end_s)
    sec_mono = _common.mono_mixdown(sec)
    win_len = int(min(4.0, (section_end_s - section_start_s)) * sr)
    if win_len < int(0.5 * sr) or len(sec_mono) <= win_len:
        sub = sec
        offset_s = 0.0
    else:
        # sliding RMS to find the loudest window
        frame = max(1, int(0.1 * sr))
        rms_local = np.sqrt(np.convolve(sec_mono ** 2, np.ones(frame) / frame, mode="same"))
        best_center = int(np.argmax(rms_local))
        start = max(0, best_center - win_len // 2)
        start = min(start, len(sec_mono) - win_len)
        if sec.ndim == 1:
            sub = sec[start : start + win_len]
        else:
            sub = sec[:, start : start + win_len]
        offset_s = start / sr

    output = out_dir / f"spec_{section_id}.png"
    _render_specshow(
        sub,
        sr,
        output,
        title=f"{audio_path.name} — {section_id} (focus @ +{offset_s:.2f}s)",
    )
    return output


def write_fingerprint_json(fingerprint: dict[str, Any], out_dir: Path) -> Path:
    path = out_dir / "fingerprint.json"
    payload = json.dumps(fingerprint, indent=2, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    return path


def resolve_out_dir(user_provided: str | None) -> Path:
    if user_provided:
        out = Path(user_provided).expanduser().resolve()
    else:
        out = Path(f"/tmp/openrig-analyzer/{int(time.time())}")
    out.mkdir(parents=True, exist_ok=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze a guitar WAV file.")
    parser.add_argument("input", help="path to input WAV")
    parser.add_argument("--out-dir", default=None, help="output directory (default: /tmp/openrig-analyzer/<unix_ts>/)")
    args = parser.parse_args(argv)

    _seed_everything()

    audio_path = Path(args.input).expanduser().resolve()
    signal, sr = _common.load_audio(audio_path)

    fingerprint = build_fingerprint(audio_path, signal, sr)
    out_dir = resolve_out_dir(args.out_dir)

    write_fingerprint_json(fingerprint, out_dir)

    sections_ranges = [(s["start_s"], s["end_s"]) for s in fingerprint["sections"]]
    render_spec_global_png(signal, sr, sections_ranges, audio_path, out_dir)
    for s in fingerprint["sections"]:
        render_spec_section_png(
            signal, sr, s["start_s"], s["end_s"], s["id"], audio_path, out_dir,
        )

    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
