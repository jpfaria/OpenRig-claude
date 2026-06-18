#!/usr/bin/env python3
"""Deterministic auto-EQ-match core for the openrig-tone-builder loop.

Given a reference WAV (isolated guitar) and a wet render of the preset
through the bundled DI, plus the EQ's current 8 band gains, compute the
next band gains that move the render's normalised long-term spectral
SHAPE toward the reference's. This is a PURE measurement+arithmetic layer:
it does NOT render, does NOT touch the rig, does NOT hit the network. The
render -> apply -> re-render loop is orchestrated by the openrig-tone-builder
skill, which feeds the current gains in and applies `new_gains` out via
`set_block_parameter_number`.

Why SHAPE and not raw match_score: the bundled DI is a different
performance from a real recording, so note onsets/silence/level make a raw
score non-convergent. The normalised LTAS (silence trimmed, level removed,
sampled at the 8 `eq_eight_band_parametric` octave centres) isolates tonal
balance, which DOES converge as the EQ matches it band by band.

Level is never matched here (the LTAS is mean-subtracted, so loudness is
removed by construction) — output level is maximised separately by the
skill's Step 7.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common  # noqa: E402

SCHEMA_VERSION = 1

# The 8 octave centres of eq_eight_band_parametric (== analyzer BANDS_HZ).
BAND_CENTERS_HZ: list[int] = list(_common.BANDS_HZ)

# Frames quieter than this (dB relative to the loudest frame) are silence
# and are dropped before averaging — a sparse stem is mostly silence.
SILENCE_FLOOR_DB = -45.0

# Parametric-EQ gain range; corrections never exceed it.
GAIN_CLAMP = (-24.0, 24.0)

# Candidate high-pass cutoffs for band 1 (b1), low to high.
HIGHPASS_LADDER_HZ: list[float] = [20.0, 30.0, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0]

_HALF_OCTAVE = 2.0 ** 0.5  # octave-band edges around each centre
_EPS = 1e-12


def normalized_ltas(
    signal: np.ndarray,
    sr: int,
    silence_floor_db: float = SILENCE_FLOOR_DB,
    centers: list[int] | None = None,
) -> np.ndarray:
    """Normalised long-term average spectrum sampled at the band centres.

    Returns one dB value per band, mean-subtracted so overall level is
    removed (the SHAPE). Silent frames are dropped first.
    """
    centers = BAND_CENTERS_HZ if centers is None else centers
    f, mag = _common._stft_mag(signal, sr)  # [bins], [bins, frames]

    # drop silent frames (energy far below the loudest frame)
    frame_power = (mag ** 2).sum(axis=0)
    if frame_power.max() <= 0.0:
        kept = mag
    else:
        frame_db = 10.0 * np.log10(frame_power / frame_power.max() + _EPS)
        keep = frame_db > silence_floor_db
        kept = mag[:, keep] if keep.any() else mag

    power = (kept ** 2).mean(axis=1)  # average power per frequency bin

    band_db = np.empty(len(centers), dtype=np.float64)
    for i, c in enumerate(centers):
        lo, hi = c / _HALF_OCTAVE, c * _HALF_OCTAVE
        mask = (f >= lo) & (f < hi)
        if mask.any():
            band_power = float(power[mask].sum())
        else:  # window narrower than the bin spacing — nearest bin
            band_power = float(power[int(np.argmin(np.abs(f - c)))])
        band_db[i] = 10.0 * np.log10(band_power + _EPS)

    return band_db - band_db.mean()


def gap_total_db(ref_ltas: np.ndarray, wet_ltas: np.ndarray) -> float:
    """Total spectral-shape distance: L1 sum of the per-band dB deltas."""
    return float(np.abs(np.asarray(ref_ltas) - np.asarray(wet_ltas)).sum())


def next_band_gains(
    current_gains: list[float],
    ref_ltas: np.ndarray,
    wet_ltas: np.ndarray,
    clamp: tuple[float, float] = GAIN_CLAMP,
) -> list[float]:
    """new_gain[i] = clamp(current_gain[i] + (ref_ltas[i] - wet_ltas[i])).

    Each band is nudged by exactly the dB it is short (or over) relative to
    the reference shape — the proven additive rule. Convergent because the
    EQ raises that band's measured LTAS by the gain it adds.
    """
    delta = np.asarray(ref_ltas, dtype=np.float64) - np.asarray(wet_ltas, dtype=np.float64)
    new = np.asarray(current_gains, dtype=np.float64) + delta
    return [float(v) for v in np.clip(new, clamp[0], clamp[1])]


def next_highpass_hz(
    current_hz: float,
    ref_ltas: np.ndarray,
    wet_ltas: np.ndarray,
    ladder: list[float] | None = None,
    deadband_db: float = 1.0,
) -> float:
    """Move band 1's high-pass cutoff to match the reference's low end.

    If the render carries more low-band energy than the reference, step the
    cutoff UP one rung (cut more bass); if it carries less, step DOWN; inside
    the deadband, hold. Frequency move, not a gain — b1 is a high-pass.
    """
    ladder = HIGHPASS_LADDER_HZ if ladder is None else ladder
    low_excess = float(ref_ltas[0]) * -1.0 + float(wet_ltas[0])  # wet - ref
    idx = int(np.argmin([abs(h - current_hz) for h in ladder]))
    if low_excess > deadband_db and idx < len(ladder) - 1:
        idx += 1
    elif low_excess < -deadband_db and idx > 0:
        idx -= 1
    return float(ladder[idx])


def _parse_gains(raw: str) -> list[float]:
    parts = [p for p in raw.replace(" ", "").split(",") if p != ""]
    gains = [float(p) for p in parts]
    if len(gains) != len(BAND_CENTERS_HZ):
        raise argparse.ArgumentTypeError(
            f"--gains needs {len(BAND_CENTERS_HZ)} comma-separated values, got {len(gains)}"
        )
    return gains


def build_correction(
    ref_path: Path,
    wet_path: Path,
    current_gains: list[float],
    current_hp_hz: float | None = None,
) -> dict[str, Any]:
    ref_sig, ref_sr = _common.load_audio(ref_path)
    wet_sig, wet_sr = _common.load_audio(wet_path)
    ref_ltas = normalized_ltas(ref_sig, ref_sr)
    wet_ltas = normalized_ltas(wet_sig, wet_sr)
    band_gap = (ref_ltas - wet_ltas).tolist()
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "band_centers_hz": BAND_CENTERS_HZ,
        "ref_ltas_db": _common.round_for_json(ref_ltas.tolist()),
        "wet_ltas_db": _common.round_for_json(wet_ltas.tolist()),
        "band_gap_db": _common.round_for_json(band_gap),
        "total_gap_db": _common.round_for_json(gap_total_db(ref_ltas, wet_ltas)),
        # Level-independent timbre proximity (the acceptance bar). total_gap_db
        # is a raw dB distance; this is the 0-100 % the tone-builder gates on.
        "proximity_pct": _common.round_for_json(
            _common.ltas_proximity_pct(ref_ltas, wet_ltas), ndigits=2
        ),
        "new_gains": _common.round_for_json(
            next_band_gains(current_gains, ref_ltas, wet_ltas)
        ),
    }
    if current_hp_hz is not None:
        out["new_highpass_hz"] = next_highpass_hz(current_hp_hz, ref_ltas, wet_ltas)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute the next 8-band EQ gains to match a reference's spectral shape."
    )
    parser.add_argument("reference", help="path to the isolated-guitar reference WAV")
    parser.add_argument("wet", help="path to the rendered (wet) WAV")
    parser.add_argument(
        "--gains", type=_parse_gains, required=True,
        help="current EQ band gains, comma-separated (8 values, dB)",
    )
    parser.add_argument("--hp-hz", type=float, default=None,
                        help="current band-1 high-pass cutoff (Hz); if given, a new cutoff is suggested")
    parser.add_argument("--output", default=None, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    diff = build_correction(Path(args.reference), Path(args.wet), args.gains, args.hp_hz)
    payload = json.dumps(diff, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
