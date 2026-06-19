#!/usr/bin/env python3
"""Write a min-phase correction-EQ impulse response (.wav) from a reference + render.

Pure measurement + DSP (no rig, no network). Measures the 1/3-octave LTAS of
both, derives the energy-gated/capped correction curve, realizes it as a
min-phase FIR (no bulk latency), and writes it as a mono WAV. Convolve it into
the cab IR, or load it via a `generic_ir` block, to impose the reference's
spectral shape and close the last ~1-1.5 dB to the song's self-floor.

Reports the before proximity, the per-song self-floor, and the predicted
after proximity (render convolved with the IR) so the gain is verifiable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import scipy.signal
import soundfile as sf

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import _common  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Write a min-phase correction-EQ IR from ref + render.")
    p.add_argument("reference", help="isolated-guitar reference WAV")
    p.add_argument("render", help="rendered (wet) WAV")
    p.add_argument("--output", required=True, help="path to write the correction IR WAV")
    p.add_argument("--taps", type=int, default=8192, help="FIR length (default 8192)")
    args = p.parse_args(argv)

    ref, ref_sr = _common.load_audio(args.reference)
    wet, wet_sr = _common.load_audio(args.render)

    ir = _common.correction_ir(ref, ref_sr, wet, wet_sr, n_taps=args.taps)
    sf.write(args.output, ir.astype(np.float32), ref_sr)

    ltas = _common.third_octave_ltas
    ref_l = ltas(ref, ref_sr)
    before = _common.weighted_spectral_proximity_pct(ref_l, ltas(wet, wet_sr))
    floor = _common.reference_self_floor(ref, ref_sr)
    corrected = scipy.signal.fftconvolve(_common.mono_mixdown(wet), ir)[: wet.shape[-1]]
    after = _common.weighted_spectral_proximity_pct(ref_l, ltas(corrected, wet_sr))

    print(
        f"wrote {args.output}  taps={len(ir)} sr={ref_sr}\n"
        f"  before={before:.1f}%  self_floor={floor:.1f}%  predicted_after={after:.1f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
