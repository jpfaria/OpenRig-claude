"""openrig-render does NOT resample its --input: it reads the WAV samples as if
they were at the engine rate (48 kHz). A DI recorded at 44.1 kHz therefore
renders 8.8 % fast and ~1.5 semitones sharp, and every proximity number built
on it measures the guitar out of tune. build_preset must hand the renderer a
48 kHz DI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts import build_preset as bp  # noqa: E402


def _sine(path: Path, sr: int, hz: float = 131.0, seconds: float = 1.0) -> None:
    t = np.arange(int(sr * seconds)) / sr
    sf.write(str(path), (0.3 * np.sin(2 * np.pi * hz * t)).astype("float32"), sr)


def _pitch_hz(path: str) -> float:
    x, sr = sf.read(path)
    sp = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8 * len(x)))
    return float(np.fft.rfftfreq(8 * len(x), 1 / sr)[np.argmax(sp)])


def test_di_at_44k1_is_resampled_to_48k_keeping_pitch_and_duration(tmp_path):
    di = tmp_path / "di.wav"
    _sine(di, 44100)
    out = bp.di_at_render_rate(str(di), tmp_path / "work")
    info = sf.info(out)
    assert info.samplerate == bp.RENDER_SAMPLE_RATE_HZ == 48000
    assert abs(info.duration - 1.0) < 1e-3
    assert abs(_pitch_hz(out) - 131.0) < 0.5


def test_di_already_at_48k_is_used_as_is(tmp_path):
    di = tmp_path / "di.wav"
    _sine(di, 48000)
    assert bp.di_at_render_rate(str(di), tmp_path / "work") == str(di)
