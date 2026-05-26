#!/usr/bin/env python3
"""Deterministic fixture synthesis for openrig-tone-analyzer tests.

Run from the skill root:

    .venv/bin/python tests/fixtures/generate.py

All randomness is seeded; files are byte-identical across machines as long as
numpy and soundfile versions match requirements.txt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050
SEED = 42
HERE = Path(__file__).resolve().parent


def synth_di(duration_s: float, fundamental_hz: float, harmonics: int = 5) -> np.ndarray:
    """Sum of sine partials with light vibrato — clean DI signal."""
    n = int(round(duration_s * SR))
    t = np.arange(n, dtype=np.float64) / SR
    vibrato = 1.0 + 0.003 * np.sin(2 * np.pi * 5.5 * t)
    signal = np.zeros(n, dtype=np.float64)
    for k in range(1, harmonics + 1):
        amp = 1.0 / k
        signal += amp * np.sin(2 * np.pi * fundamental_hz * k * t * vibrato)
    signal /= np.max(np.abs(signal)) + 1e-9
    envelope = np.minimum(1.0, np.minimum(t * 50, (duration_s - t) * 50))
    return (signal * envelope * 0.6).astype(np.float32)


def apply_softclip(signal: np.ndarray, gain: float) -> np.ndarray:
    """Tube-style saturation via tanh."""
    return np.tanh(gain * signal).astype(np.float32)


def apply_convolve_reverb(signal: np.ndarray, rt60_s: float) -> np.ndarray:
    """Convolve with an exponentially decaying noise IR (synthetic reverb)."""
    rng = np.random.default_rng(SEED)
    n_ir = int(round(rt60_s * 1.5 * SR))
    t = np.arange(n_ir, dtype=np.float64) / SR
    envelope = np.exp(-6.91 * t / rt60_s)
    ir = rng.standard_normal(n_ir).astype(np.float64) * envelope
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet = np.convolve(signal.astype(np.float64), ir, mode="full")[: len(signal)]
    mix = 0.6 * signal.astype(np.float64) + 0.4 * wet
    peak = np.max(np.abs(mix)) + 1e-9
    return (mix / peak * 0.9).astype(np.float32)


def add_delay(signal: np.ndarray, time_ms: float, feedback: float, mix: float) -> np.ndarray:
    """Feedback delay line."""
    delay_samples = int(round(time_ms / 1000.0 * SR))
    out = signal.astype(np.float64).copy()
    buf = np.zeros(len(signal) + delay_samples * 8, dtype=np.float64)
    buf[: len(signal)] = signal
    for i in range(len(signal)):
        tap_idx = i - delay_samples
        if tap_idx >= 0:
            tap = buf[tap_idx]
            buf[i] += feedback * tap
            out[i] = (1 - mix) * signal[i] + mix * buf[i]
    peak = np.max(np.abs(out)) + 1e-9
    return (out / peak * 0.9).astype(np.float32)


def write(name: str, signal: np.ndarray) -> None:
    path = HERE / name
    sf.write(str(path), signal, SR, subtype="PCM_16")
    size_kb = path.stat().st_size / 1024
    print(f"  {name:32s} {len(signal) / SR:5.2f} s  {size_kb:6.1f} KB")


def main() -> int:
    np.random.seed(SEED)

    print(f"Generating fixtures into {HERE}/ (sr={SR}, seed={SEED})")

    clean = synth_di(4.0, 330.0, harmonics=5)
    write("clean_di.wav", clean)

    distorted = apply_softclip(clean, gain=8.0)
    write("distorted_di.wav", distorted)

    reverb = apply_convolve_reverb(clean, rt60_s=1.4)
    write("reverb_tail.wav", reverb)

    delayed = add_delay(clean, time_ms=380.0, feedback=0.25, mix=0.3)
    write("delayed_echo.wav", delayed)

    silence_pad = np.zeros(int(1.5 * SR), dtype=np.float32)
    clean_with_silence = np.concatenate([clean, silence_pad])
    write("clean_with_silence.wav", clean_with_silence)

    sec_clean = synth_di(8.0, 330.0, harmonics=5)
    sec_high_gain = apply_softclip(synth_di(12.0, 220.0, harmonics=6), gain=12.0)
    sec_clean_tail = synth_di(8.0, 330.0, harmonics=5)
    multi = np.concatenate([sec_clean, sec_high_gain, sec_clean_tail])
    write("multi_section.wav", multi)

    total = sum(p.stat().st_size for p in HERE.glob("*.wav"))
    print(f"Total: {total / 1024:.1f} KB across {len(list(HERE.glob('*.wav')))} files")
    if total > 2_500_000:
        print(f"ERROR: total exceeds 2.5 MB budget", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
