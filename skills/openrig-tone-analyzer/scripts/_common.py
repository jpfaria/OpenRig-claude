"""Shared spectral, time-FX, and segmentation helpers for the tone analyzer.

All public helpers are pure functions of their inputs (no global state besides
seeded RNGs). Floats returned for JSON serialization should be passed through
``round_for_json`` to keep determinism tight.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import scipy.signal
import soundfile as sf

MAX_DURATION_S = 600.0
SEED = 42

BANDS_HZ = [80, 160, 320, 640, 1280, 2560, 5120, 10240]
BAND_EDGES_HZ = BANDS_HZ + [20000]

STFT_N_FFT = 2048
STFT_HOP = 512


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_audio(path: Path | str) -> tuple[np.ndarray, int]:
    """Load a WAV (or anything soundfile understands) as float32 in [-1, 1].

    Mono returns shape (N,); stereo returns shape (2, N).
    """
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    except Exception as exc:
        raise SystemExit(f"could not decode audio: {path} ({exc})") from exc

    if data.ndim == 2:
        # soundfile returns (N, channels) for stereo; transpose to (channels, N)
        data = np.ascontiguousarray(data.T)

    duration_s = data.shape[-1] / sr
    if duration_s > MAX_DURATION_S:
        raise SystemExit(f"file too long (max {int(MAX_DURATION_S)} s): {path}, got {duration_s:.1f} s")
    return data.astype(np.float32, copy=False), int(sr)


def mono_mixdown(signal: np.ndarray) -> np.ndarray:
    """Collapse a stereo array to mono by mean. Mono input is returned as-is."""
    if signal.ndim == 1:
        return signal
    return signal.mean(axis=0).astype(np.float32)


# ---------------------------------------------------------------------------
# Loudness
# ---------------------------------------------------------------------------

def _safe_log10(x: float) -> float:
    return float(np.log10(max(x, 1e-12)))


def compute_rms_db(signal: np.ndarray) -> float:
    sig = mono_mixdown(signal)
    rms = float(np.sqrt(np.mean(sig.astype(np.float64) ** 2)))
    return 20.0 * _safe_log10(rms)


def compute_peak_db(signal: np.ndarray) -> float:
    sig = mono_mixdown(signal)
    peak = float(np.max(np.abs(sig)))
    return 20.0 * _safe_log10(peak)


def compute_crest_factor_db(signal: np.ndarray) -> float:
    peak_db = compute_peak_db(signal)
    rms_db = compute_rms_db(signal)
    return peak_db - rms_db


def compute_lufs_integrated(signal: np.ndarray, sr: int) -> float:
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(0.4 * sr):
        # pyloudnorm needs >= 400 ms; for tiny clips, fall back to rms_db.
        return compute_rms_db(signal)
    try:
        return float(meter.integrated_loudness(sig))
    except Exception:
        return compute_rms_db(signal)


# ---------------------------------------------------------------------------
# Spectrum
# ---------------------------------------------------------------------------

def _stft_mag(signal: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (freq_bins_hz, magnitude_matrix [bins, frames])."""
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < STFT_N_FFT:
        sig = np.pad(sig, (0, STFT_N_FFT - len(sig)))
    f, _, z = scipy.signal.stft(
        sig,
        fs=sr,
        nperseg=STFT_N_FFT,
        noverlap=STFT_N_FFT - STFT_HOP,
        boundary=None,
        padded=False,
    )
    return f.astype(np.float64), np.abs(z).astype(np.float64)


def compute_band_energy_db(signal: np.ndarray, sr: int) -> list[float]:
    f, mag = _stft_mag(signal, sr)
    # power spectrum averaged across frames
    power = (mag ** 2).mean(axis=1)
    results: list[float] = []
    for i in range(len(BANDS_HZ)):
        lo = BAND_EDGES_HZ[i]
        hi = BAND_EDGES_HZ[i + 1]
        mask = (f >= lo) & (f < hi)
        band_power = float(power[mask].sum()) if mask.any() else 0.0
        results.append(10.0 * _safe_log10(band_power + 1e-12))
    return results


def compute_spectral_centroid_hz(signal: np.ndarray, sr: int) -> float:
    f, mag = _stft_mag(signal, sr)
    # per-frame centroid, then median across frames
    frame_energy = mag.sum(axis=0) + 1e-12
    frame_centroid = (f[:, None] * mag).sum(axis=0) / frame_energy
    # exclude frames whose energy is negligible (silence)
    energy_db = 20.0 * np.log10(frame_energy / frame_energy.max() + 1e-12)
    keep = energy_db > -40
    if not keep.any():
        return float(np.median(frame_centroid))
    return float(np.median(frame_centroid[keep]))


def compute_spectral_rolloff_hz(signal: np.ndarray, sr: int, pct: float = 0.85) -> float:
    f, mag = _stft_mag(signal, sr)
    energy = (mag ** 2).mean(axis=1)
    cumulative = np.cumsum(energy)
    total = cumulative[-1]
    if total <= 0:
        return 0.0
    idx = int(np.searchsorted(cumulative, pct * total))
    idx = min(idx, len(f) - 1)
    return float(f[idx])


def compute_spectral_flatness(signal: np.ndarray, sr: int) -> float:
    _, mag = _stft_mag(signal, sr)
    power = (mag ** 2).mean(axis=1) + 1e-12
    gmean = float(np.exp(np.mean(np.log(power))))
    amean = float(np.mean(power))
    return gmean / amean if amean > 0 else 0.0


# ---------------------------------------------------------------------------
# Distortion
# ---------------------------------------------------------------------------

def _estimate_fundamental_hz(signal: np.ndarray, sr: int) -> float | None:
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(0.05 * sr):
        return None
    # autocorrelation-based pitch estimate, restricted to guitar range
    win = sig[: min(len(sig), int(0.3 * sr))]
    win = win - win.mean()
    if np.max(np.abs(win)) < 1e-4:
        return None
    win = win / (np.max(np.abs(win)) + 1e-9)
    ac = np.correlate(win, win, mode="full")[len(win) - 1 :]
    min_lag = int(sr / 1000.0)  # 1000 Hz upper bound
    max_lag = int(sr / 60.0)    # 60 Hz lower bound
    if max_lag >= len(ac):
        return None
    peak = int(np.argmax(ac[min_lag:max_lag])) + min_lag
    if ac[peak] <= 0:
        return None
    return float(sr / peak)


def estimate_thd_pct(signal: np.ndarray, sr: int) -> float:
    """Best-effort THD estimate: ratio of harmonic energy to fundamental energy.

    Pure sine: < 1%. Heavily clipped sine: > 15%.
    """
    f0 = _estimate_fundamental_hz(signal, sr)
    if f0 is None or f0 < 60 or f0 > 1500:
        return 0.0
    f, mag = _stft_mag(signal, sr)
    spectrum = (mag ** 2).mean(axis=1)
    # bin width
    bin_hz = sr / STFT_N_FFT
    fund_idx = int(round(f0 / bin_hz))

    def energy_at(idx: int, half_bw: int = 2) -> float:
        lo = max(0, idx - half_bw)
        hi = min(len(spectrum), idx + half_bw + 1)
        return float(spectrum[lo:hi].sum())

    fund_e = energy_at(fund_idx, half_bw=3)
    if fund_e < 1e-12:
        return 0.0
    harm_e = 0.0
    for k in range(2, 7):
        idx = int(round(f0 * k / bin_hz))
        if idx >= len(spectrum):
            break
        harm_e += energy_at(idx, half_bw=3)
    thd = np.sqrt(harm_e / fund_e) * 100.0
    return float(min(thd, 200.0))


def compute_odd_even_harmonic_ratio_db(signal: np.ndarray, sr: int) -> float:
    """Estimate odd/even harmonic-energy ratio in dB. Returns 0.0 if undeterminable."""
    f0 = _estimate_fundamental_hz(signal, sr)
    if f0 is None:
        return 0.0
    f, mag = _stft_mag(signal, sr)
    spectrum = (mag ** 2).mean(axis=1)
    bin_hz = sr / STFT_N_FFT
    odd = 0.0
    even = 0.0
    for k in range(2, 8):
        idx = int(round(f0 * k / bin_hz))
        if idx >= len(spectrum):
            break
        e = float(spectrum[max(0, idx - 2) : idx + 3].sum())
        if k % 2 == 1:
            odd += e
        else:
            even += e
    if even <= 0:
        return 0.0
    return 10.0 * _safe_log10((odd + 1e-12) / (even + 1e-12))


def classify_gain_character(
    thd_pct: float,
    crest_db: float,
    band_energy_db: list[float],
) -> tuple[str, float]:
    """Apply the spec's decision rules.

    Returns (label, confidence). Confidence is a heuristic distance from the
    nearest decision boundary, clipped to [0, 1].
    """
    # primary rule on THD
    if thd_pct < 3.0 and crest_db > 12.0:
        label = "clean"
        boundary = 3.0
        dist = boundary - thd_pct
    elif thd_pct < 10.0:
        label = "crunch"
        # confidence is min distance to nearest neighbor (3 or 10)
        dist = min(thd_pct - 3.0, 10.0 - thd_pct)
    elif thd_pct < 25.0:
        label = "distortion"
        dist = min(thd_pct - 10.0, 25.0 - thd_pct)
    else:
        label = "high_gain"
        dist = thd_pct - 25.0

    # secondary high_gain override
    if thd_pct >= 15.0 and len(band_energy_db) >= 5:
        mid_high = band_energy_db[5]  # 2560
        low_mid = band_energy_db[3]   # 640
        if (mid_high - low_mid) > 6.0:  # strong upper-mid bias
            label = "high_gain"
            dist = max(dist, mid_high - low_mid - 6.0)

    confidence = float(min(1.0, max(0.0, dist) / 5.0))
    if label == "clean":
        confidence = float(min(1.0, max(0.0, (12.0 - thd_pct) / 12.0)))
    return label, confidence


# ---------------------------------------------------------------------------
# Time-FX
# ---------------------------------------------------------------------------

def estimate_rt60_s(signal: np.ndarray, sr: int) -> tuple[float | None, float]:
    """Estimate RT60 from the decay tail after the loudest peak.

    Approach: find peak, then fit a line to the log-RMS envelope after the
    peak; RT60 = time to drop by 60 dB. If the envelope doesn't decay
    monotonically (continuous playing), confidence drops toward 0.
    """
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(0.3 * sr):
        return None, 0.0

    # smooth envelope via abs + low-pass
    env = np.abs(sig)
    window = max(1, int(0.02 * sr))  # 20 ms
    env = np.convolve(env, np.ones(window) / window, mode="same")
    if env.max() <= 0:
        return None, 0.0

    peak_idx = int(np.argmax(env))
    tail = env[peak_idx:]
    if len(tail) < int(0.2 * sr):
        return None, 0.0

    tail_db = 20.0 * np.log10(tail / env.max() + 1e-12)
    # Fit a line to the first 1.5 s of tail (or until -40 dB, whichever first).
    fit_len = min(len(tail_db), int(1.5 * sr))
    y = tail_db[:fit_len]
    drop_idx = np.argmax(y < -40.0) if (y < -40.0).any() else fit_len
    drop_idx = max(drop_idx, int(0.05 * sr))
    y = y[:drop_idx]
    x = np.arange(len(y), dtype=np.float64) / sr
    if len(y) < 16:
        return None, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= -1.0:
        # too flat → no decay
        return None, 0.0
    rt60 = float(-60.0 / slope)
    # confidence: how monotonic is the decay (correlation with line)?
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) + 1e-9
    r2 = max(0.0, 1.0 - ss_res / ss_tot)
    if rt60 <= 0 or rt60 > 10.0:
        return None, 0.0
    return rt60, float(r2)


def detect_delay(signal: np.ndarray, sr: int) -> tuple[bool, int | None, float | None]:
    """Template-matching delay detection.

    A real delay echoes the source's envelope shape at lag T. We:
      1. Build the envelope (rectified + low-pass + downsample).
      2. Extract a short template starting at the loudest onset.
      3. Slide the template across later parts of the envelope; the highest
         normalized cross-correlation > 0.5 at lag ∈ [60 ms, 1500 ms] flags
         a delay.

    Modulation (vibrato, chorus) doesn't create structured envelope echoes,
    so this discriminates cleanly between the two.

    Returns (present, time_ms, feedback_pct_estimate).
    """
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(0.7 * sr):
        return False, None, None

    # envelope: rectify + 10 ms moving average, downsample to 1 kHz
    env = np.abs(sig)
    smooth = max(1, int(0.01 * sr))
    env = np.convolve(env, np.ones(smooth) / smooth, mode="same")
    target_sr = 1000
    step = max(1, sr // target_sr)
    env_ds = env[::step]
    ds_sr = sr / step

    if env_ds.max() < 1e-4:
        return False, None, None
    env_ds = env_ds / env_ds.max()

    # Find the loudest onset in the first 500 ms
    template_len = max(8, int(0.05 * ds_sr))  # 50 ms template
    search_start = 0
    search_end = min(int(0.5 * ds_sr), len(env_ds) - template_len)
    if search_end <= search_start:
        return False, None, None
    onset_candidates = env_ds[search_start:search_end]
    onset_idx = int(np.argmax(onset_candidates)) + search_start

    template = env_ds[onset_idx : onset_idx + template_len]
    if template.std() < 0.05:
        # template is too flat (silence or steady tone) — no chance of finding
        # a structured echo of it
        return False, None, None

    # Slide template across [onset + 60 ms, onset + 1500 ms]
    min_offset = int(0.06 * ds_sr)
    max_offset = int(1.5 * ds_sr)
    best_corr = -1.0
    best_offset = 0
    t_norm = template - template.mean()
    t_norm /= np.linalg.norm(t_norm) + 1e-9
    for offset in range(min_offset, min(max_offset, len(env_ds) - onset_idx - template_len)):
        window = env_ds[onset_idx + offset : onset_idx + offset + template_len]
        if window.std() < 1e-4:
            continue
        w = window - window.mean()
        w /= np.linalg.norm(w) + 1e-9
        corr = float(np.dot(t_norm, w))
        if corr > best_corr:
            best_corr = corr
            best_offset = offset

    if best_corr < 0.5:
        return False, None, None

    # estimate feedback by amplitude ratio of echo vs template peak
    echo_peak = float(env_ds[onset_idx + best_offset : onset_idx + best_offset + template_len].max())
    template_peak = float(template.max())
    feedback_pct = int(round(min(1.0, echo_peak / (template_peak + 1e-9)) * 100.0))

    time_ms = int(round(best_offset / ds_sr * 1000.0))
    return True, time_ms, feedback_pct


def detect_modulation(signal: np.ndarray, sr: int) -> tuple[bool, float | None, float | None]:
    """Best-effort modulation detection (chorus/flanger/tremolo).

    Looks for a low-frequency periodicity in the amplitude envelope between
    0.5 Hz and 10 Hz. Returns (present, rate_hz, depth_estimate_0_1).
    Conservative: high false-negative rate is fine; false positives are not.
    """
    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(2.0 * sr):
        return False, None, None
    env = np.abs(sig)
    window = max(1, int(0.01 * sr))
    env = np.convolve(env, np.ones(window) / window, mode="same")
    # downsample envelope to ~200 Hz for cheap FFT
    target_sr = 200
    step = max(1, sr // target_sr)
    env_ds = env[::step]
    env_ds = env_ds - env_ds.mean()
    if np.max(np.abs(env_ds)) < 1e-4:
        return False, None, None
    env_ds = env_ds / (np.max(np.abs(env_ds)) + 1e-9)
    n_fft = 1024
    if len(env_ds) < n_fft:
        env_ds = np.pad(env_ds, (0, n_fft - len(env_ds)))
    spec = np.abs(np.fft.rfft(env_ds[:n_fft]))
    freqs = np.fft.rfftfreq(n_fft, d=step / sr)
    band = (freqs > 0.5) & (freqs < 10.0)
    if not band.any():
        return False, None, None
    band_spec = spec[band]
    band_freqs = freqs[band]
    peak_idx = int(np.argmax(band_spec))
    peak_val = float(band_spec[peak_idx])
    median_val = float(np.median(spec[band]))
    if median_val <= 0 or peak_val / max(median_val, 1e-9) < 8.0:
        return False, None, None
    return True, float(band_freqs[peak_idx]), float(min(1.0, peak_val / spec.max()))


# ---------------------------------------------------------------------------
# Stereo
# ---------------------------------------------------------------------------

def compute_stereo_features(signal: np.ndarray) -> dict[str, Any]:
    if signal.ndim == 1:
        return {
            "is_stereo": False,
            "ms_balance_ratio": 1.0,
            "lr_correlation": 1.0,
        }
    left = signal[0].astype(np.float64)
    right = signal[1].astype(np.float64)
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    mid_e = float(np.sqrt(np.mean(mid ** 2)) + 1e-12)
    side_e = float(np.sqrt(np.mean(side ** 2)) + 1e-12)
    balance = float(mid_e / (mid_e + side_e))
    corr = float(np.corrcoef(left, right)[0, 1]) if left.std() > 1e-9 and right.std() > 1e-9 else 1.0
    return {
        "is_stereo": True,
        "ms_balance_ratio": balance,
        "lr_correlation": corr,
    }


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

@dataclass
class SectionRange:
    start_s: float
    end_s: float


def _frame_features(signal: np.ndarray, sr: int, hop_s: float = 1.0, win_s: float = 2.0) -> np.ndarray:
    """Per-frame feature matrix: shape (n_frames, 4) = [rms_db, centroid_hz, flatness, onset_strength]."""
    import librosa

    sig = mono_mixdown(signal).astype(np.float64)
    hop = int(hop_s * sr)
    win = int(win_s * sr)
    if len(sig) < win:
        sig = np.pad(sig, (0, win - len(sig)))
    n_frames = max(1, 1 + (len(sig) - win) // hop)
    feats = np.zeros((n_frames, 4), dtype=np.float64)
    for i in range(n_frames):
        chunk = sig[i * hop : i * hop + win]
        if len(chunk) < win:
            chunk = np.pad(chunk, (0, win - len(chunk)))
        feats[i, 0] = compute_rms_db(chunk.astype(np.float32))
        feats[i, 1] = compute_spectral_centroid_hz(chunk.astype(np.float32), sr)
        feats[i, 2] = compute_spectral_flatness(chunk.astype(np.float32), sr)
        # onset strength on the chunk
        onset_env = librosa.onset.onset_strength(y=chunk, sr=sr, hop_length=512)
        feats[i, 3] = float(onset_env.mean())
    return feats


def segment_track(signal: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """Detect structural boundaries via librosa agglomerative on frame features.

    Returns list of (start_s, end_s) tuples covering the full duration.
    Enforces an 8 s minimum section length by merging.
    """
    import librosa

    sig = mono_mixdown(signal).astype(np.float64)
    duration_s = len(sig) / sr
    if duration_s < 8.0:
        return [(0.0, float(duration_s))]

    feats = _frame_features(signal, sr, hop_s=1.0, win_s=2.0)
    if feats.shape[0] < 4:
        return [(0.0, float(duration_s))]

    # normalize each column for cosine distance fairness
    feats_n = feats.copy()
    for j in range(feats_n.shape[1]):
        col = feats_n[:, j]
        std = col.std() + 1e-9
        feats_n[:, j] = (col - col.mean()) / std

    k = int(np.ceil(duration_s / 30.0))
    k = max(2, min(12, k))
    try:
        # librosa.segment.agglomerative takes (features.T, k) — feature matrix is (n_features, n_frames)
        bounds = librosa.segment.agglomerative(feats_n.T, k)
    except Exception:
        return [(0.0, float(duration_s))]

    # bounds is an array of frame indices; convert to seconds (hop=1s)
    bound_seconds = sorted(set([0.0] + [float(b) for b in bounds] + [float(duration_s)]))
    sections: list[tuple[float, float]] = []
    for i in range(len(bound_seconds) - 1):
        sections.append((bound_seconds[i], bound_seconds[i + 1]))

    # merge sections shorter than 8 s into the more-similar neighbor (by frame-mean distance)
    def merged_once(secs: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], bool]:
        if len(secs) <= 1:
            return secs, False
        lengths = [e - s for s, e in secs]
        short_idx = -1
        for i, l in enumerate(lengths):
            if l < 8.0:
                short_idx = i
                break
        if short_idx < 0:
            return secs, False
        # merge with whichever neighbor exists; if both, pick the shorter one
        if short_idx == 0:
            merged = [(secs[0][0], secs[1][1])] + secs[2:]
        elif short_idx == len(secs) - 1:
            merged = secs[:-2] + [(secs[-2][0], secs[-1][1])]
        else:
            prev_len = lengths[short_idx - 1]
            next_len = lengths[short_idx + 1]
            target = short_idx - 1 if prev_len <= next_len else short_idx + 1
            if target == short_idx - 1:
                merged = secs[: short_idx - 1] + [(secs[short_idx - 1][0], secs[short_idx][1])] + secs[short_idx + 1 :]
            else:
                merged = secs[:short_idx] + [(secs[short_idx][0], secs[short_idx + 1][1])] + secs[short_idx + 2 :]
        return merged, True

    while True:
        sections, changed = merged_once(sections)
        if not changed:
            break

    if not sections:
        sections = [(0.0, float(duration_s))]
    return sections


# ---------------------------------------------------------------------------
# Time alignment
# ---------------------------------------------------------------------------

def align_signals(ref: np.ndarray, wet: np.ndarray, sr: int) -> tuple[int, float]:
    """Estimate the lag (in samples) and a confidence in [0, 1].

    Cross-correlate the first ~2 s of both signals. If cross-correlation peak
    is weak, fall back to onset-difference. If both are weak, confidence < 0.3.
    """
    import librosa

    ref_m = mono_mixdown(ref).astype(np.float64)
    wet_m = mono_mixdown(wet).astype(np.float64)

    # cross-correlation on first 2 s, RMS-normalized
    win = int(min(2.0 * sr, len(ref_m), len(wet_m)))
    if win < int(0.1 * sr):
        return 0, 0.0
    r = ref_m[:win]
    w = wet_m[:win]
    r = r - r.mean()
    w = w - w.mean()
    rn = r / (np.sqrt(np.mean(r ** 2)) + 1e-9)
    wn = w / (np.sqrt(np.mean(w ** 2)) + 1e-9)
    xc = np.correlate(rn, wn, mode="full")
    xc_norm = xc / (win + 1e-9)
    peak_idx = int(np.argmax(np.abs(xc_norm)))
    lag = peak_idx - (win - 1)
    confidence = float(min(1.0, np.abs(xc_norm[peak_idx])))
    if confidence > 0.6:
        return int(lag), confidence

    # fallback: librosa onset
    try:
        ref_onsets = librosa.onset.onset_detect(y=ref_m, sr=sr, units="samples")
        wet_onsets = librosa.onset.onset_detect(y=wet_m, sr=sr, units="samples")
        if len(ref_onsets) > 0 and len(wet_onsets) > 0:
            lag = int(wet_onsets[0]) - int(ref_onsets[0])
            return lag, 0.5
    except Exception:
        pass

    return int(lag), confidence


# ---------------------------------------------------------------------------
# JSON plumbing
# ---------------------------------------------------------------------------

def round_for_json(value: Any, ndigits: int = 4) -> Any:
    """Recursively round floats to ``ndigits`` decimals.

    Converts numpy scalar types to Python natives so json.dumps stays clean.
    """
    if isinstance(value, dict):
        return {k: round_for_json(v, ndigits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_for_json(v, ndigits) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(value):
            return None
        return float(round(float(value), ndigits))
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def sha256_file(path: Path | str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Section labeling
# ---------------------------------------------------------------------------

def label_section(
    rms_db: float,
    crest_db: float,
    onset_rate_per_s: float,
    rms_variance_db: float,
    tone_profile: str,
    track_loudest_rms_db: float,
) -> dict[str, str]:
    if onset_rate_per_s < 1.0 or rms_variance_db > 8.0:
        dynamics = "sparse"
    elif onset_rate_per_s >= 2.5 and rms_variance_db <= 8.0:
        dynamics = "rhythmic"
    elif onset_rate_per_s < 2.5 and crest_db < 10.0:
        dynamics = "sustained"
    else:
        dynamics = "rhythmic"

    relative_db = rms_db - track_loudest_rms_db
    if relative_db >= -3.0:
        presence = "lead"
    elif relative_db >= -10.0:
        presence = "rhythm"
    else:
        presence = "background"

    return {
        "tone_profile": tone_profile,
        "dynamics_profile": dynamics,
        "presence": presence,
    }


def compute_onset_rate_per_s(signal: np.ndarray, sr: int) -> float:
    import librosa

    sig = mono_mixdown(signal).astype(np.float64)
    if len(sig) < int(0.5 * sr):
        return 0.0
    onsets = librosa.onset.onset_detect(y=sig, sr=sr, units="time")
    duration_s = len(sig) / sr
    if duration_s <= 0:
        return 0.0
    return float(len(onsets) / duration_s)


def compute_rms_variance_db(signal: np.ndarray, sr: int, frame_s: float = 0.1) -> float:
    sig = mono_mixdown(signal).astype(np.float64)
    frame = max(1, int(frame_s * sr))
    n_frames = max(1, len(sig) // frame)
    rms_values = []
    for i in range(n_frames):
        chunk = sig[i * frame : (i + 1) * frame]
        rms = float(np.sqrt(np.mean(chunk ** 2)) + 1e-12)
        rms_values.append(20.0 * _safe_log10(rms))
    return float(np.std(rms_values))
