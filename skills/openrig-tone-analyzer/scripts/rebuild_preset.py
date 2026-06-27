#!/usr/bin/env python3
"""Offline preset-rebuild driver for the openrig-tone-builder loop.

Given a flat preset YAML (the same `id/name/blocks` shape `openrig-render
--chain` consumes) and a surviving isolated-guitar reference, this drives the
deterministic render -> eq_match -> apply loop entirely offline:

  1. render the bundled DI through the preset (`openrig-render --chain`),
  2. measure the level-normalised LTAS proximity vs the reference (eq_match.py),
  3. set the 8-band parametric EQ to the absolute gains eq_match returns,
  4. repeat until `within_floor` (or a plateau / iteration cap),
  5. gain-normalise the EQ (cut-biased, makeup on output_db) and run a headroom
     pass so the DI peak lands ~ -7 dBFS with the limiter idle.

The render and eq_match calls are injected (`render_fn`, `eqmatch_fn`) so the
loop logic is unit-testable without the Rust binary or large WAVs. `main()`
wires the real subprocess calls.

PORTABLE BY CONSTRUCTION (skill-rules LAW 1): no machine-tied paths. The
analyzer scripts and venv are resolved relative to this file; the render
binary, bundled DI, and plugins root are required CLI arguments (they live in
the OpenRig app / OpenRig-plugins, whose clone location varies per machine).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import yaml

# numpy is a hard dep of this skill; register safe representers so numpy
# scalars (returned by soundfile/numpy peak math) serialise cleanly.
try:
    import numpy as _np

    yaml.SafeDumper.add_representer(_np.float64, lambda d, v: d.represent_float(float(v)))
    yaml.SafeDumper.add_multi_representer(_np.floating, lambda d, v: d.represent_float(float(v)))
    yaml.SafeDumper.add_multi_representer(_np.integer, lambda d, v: d.represent_int(int(v)))
except Exception:  # pragma: no cover - numpy always present in this skill's venv
    _np = None

EQ_MODEL = "eq_eight_band_parametric"
LIMITER_MODEL = "limiter_brickwall"
# eq_match.py operates on this fixed octave grid: band1 = high-pass, bands 2-7
# = peak, band8 = high-shelf. The EQ bands MUST sit on these centres or the
# returned gains land on the wrong bands.
GRID_HZ = [80, 160, 320, 640, 1280, 2560, 5120, 10240]
GAIN_MIN, GAIN_MAX = -24.0, 24.0
OUTPUT_MIN, OUTPUT_MAX = -24.0, 12.0
PEAK_TARGET_DB = -7.0
PEAK_LO_DB, PEAK_HI_DB = -8.0, -6.0


# --- YAML round-trip -------------------------------------------------------

def load_yaml(path: str | os.PathLike) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def dump_yaml(obj: dict, path: str | os.PathLike) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False)


# --- pure EQ / block helpers ----------------------------------------------

def eq_block(preset: dict) -> dict:
    for b in preset["blocks"]:
        if b.get("model") == EQ_MODEL:
            return b
    raise ValueError(f"preset has no {EQ_MODEL} block")


def set_block_enabled(preset: dict, model: str, enabled: bool) -> None:
    for b in preset["blocks"]:
        if b.get("model") == model:
            b["enabled"] = enabled


def set_eq_grid(preset: dict) -> None:
    """Place the 8 bands on the eq_match grid, flat (gains 0, output 0)."""
    p = eq_block(preset).setdefault("params", {})
    for i, freq in enumerate(GRID_HZ, start=1):
        if i == 1:
            btype = "high_pass"
        elif i == 8:
            btype = "high_shelf"
        else:
            btype = "peak"
        p[f"band{i}_enabled"] = True
        p[f"band{i}_type"] = btype
        p[f"band{i}_freq"] = float(freq)
        p[f"band{i}_gain"] = 0.0
        p[f"band{i}_q"] = 1.0
    p["output_db"] = 0.0


def band_gains(preset: dict) -> list[float]:
    p = eq_block(preset)["params"]
    return [float(p[f"band{i}_gain"]) for i in range(1, 9)]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def apply_band_gains(preset: dict, new_gains, hp_hz) -> None:
    """Set the 8 ABSOLUTE band gains eq_match returned (its contract), clamped.
    No normalisation in-loop — that breaks the gains feedback. band1's
    high-pass cutoff moves to the eq_match-suggested value."""
    p = eq_block(preset)["params"]
    for i in range(1, 9):
        p[f"band{i}_gain"] = round(_clamp(new_gains[i - 1], GAIN_MIN, GAIN_MAX), 2)
    p["band1_freq"] = float(hp_hz)


def normalize_for_headroom(preset: dict) -> float:
    """Gain-normalise the EQ: subtract the max positive band gain so the curve
    is cut-biased (no band boosted into the limiter), recovering that common-
    mode level once on the EQ output_db. Returns the offset removed."""
    p = eq_block(preset)["params"]
    gains = [float(p[f"band{i}_gain"]) for i in range(1, 9)]
    offset = max(gains)
    if offset <= 0:
        return 0.0
    for i in range(1, 9):
        p[f"band{i}_gain"] = round(_clamp(gains[i - 1] - offset, GAIN_MIN, GAIN_MAX), 2)
    cur = float(p.get("output_db", 0.0))
    p["output_db"] = round(_clamp(cur + offset, OUTPUT_MIN, OUTPUT_MAX), 2)
    return offset


# --- loop orchestration (render_fn / eqmatch_fn injected) ------------------

def rebuild(base_preset: dict, render_fn, eqmatch_fn, max_iters: int = 6,
            plateau_eps: float = 0.5) -> dict:
    """Drive render -> eq_match -> apply until within_floor / plateau / cap.

    render_fn(preset, iter) -> None       (renders the DI through `preset`)
    eqmatch_fn(preset, gains, hp, iter) -> dict with keys proximity_pct,
        self_floor_pct, within_floor, new_gains, new_highpass_hz, ...
    """
    preset = copy.deepcopy(base_preset)
    set_eq_grid(preset)
    set_block_enabled(preset, LIMITER_MODEL, False)  # clean, unclipped measurement

    history: list[tuple] = []
    best = None  # (iter, prox, floor, preset_snapshot)
    for it in range(1, max_iters + 1):
        render_fn(preset, it)
        res = eqmatch_fn(preset, band_gains(preset),
                         eq_block(preset)["params"]["band1_freq"], it)
        prox, floor = float(res["proximity_pct"]), float(res["self_floor_pct"])
        within = bool(res["within_floor"])
        history.append((it, round(prox, 2), round(floor, 2), within))
        if best is None or prox > best[1]:
            best = (it, prox, floor, copy.deepcopy(preset))
        if within:
            break
        if len(history) >= 2 and it >= 3 and (history[-1][1] - history[-2][1]) < plateau_eps:
            break
        apply_band_gains(preset, res["new_gains"], res["new_highpass_hz"])

    final = copy.deepcopy(best[3])
    set_block_enabled(final, LIMITER_MODEL, True)
    normalize_for_headroom(final)
    return {
        "history": history,
        "within": best[1] >= best[2] - 3.0,
        "best_iter": best[0],
        "best_prox": round(best[1], 2),
        "best_floor": round(best[2], 2),
        "final_preset": final,
    }


# --- real subprocess wiring (CLI) ------------------------------------------

def _peak_dbfs(wav_path: str) -> float:
    import numpy as np
    import soundfile as sf

    data, _sr = sf.read(wav_path)
    peak = float(np.max(np.abs(data))) if getattr(data, "size", 0) else 0.0
    return 20.0 * math.log10(peak) if peak > 0 else -120.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline OpenRig preset-rebuild driver")
    ap.add_argument("--ref", required=True, help="isolated-guitar reference WAV")
    ap.add_argument("--base", required=True, help="base flat preset YAML (gear + EQ block)")
    ap.add_argument("--out-dir", required=True, help="evaluation dir (renders/, diffs/, presets/)")
    ap.add_argument("--role", required=True, help="rhythm/lead/solo/clean")
    ap.add_argument("--render-bin", required=True, help="path to the installed openrig-render")
    ap.add_argument("--di", required=True, help="bundled DI WAV (assets/audio/input.wav)")
    ap.add_argument("--plugins-root", default="",
                    help="override plugins root (OPENRIG_PLUGINS_ROOT); omit when using "
                         "the installed openrig-render, which auto-resolves the bundled plugins")
    ap.add_argument("--dyld-lib", default="",
                    help="extra DYLD_FALLBACK_LIBRARY_PATH (dev-tree macOS NAM dylib only; "
                         "the installed binary resolves it via the bundle Frameworks rpath)")
    ap.add_argument("--max-iters", type=int, default=6)
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent
    py = sys.executable  # this skill's venv python (portable)
    eq_match = str(here / "eq_match.py")

    renders = Path(args.out_dir) / "renders"
    diffs = Path(args.out_dir) / "diffs"
    presets = Path(args.out_dir) / "presets"
    for d in (renders, diffs, presets):
        d.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    if args.plugins_root:
        env["OPENRIG_PLUGINS_ROOT"] = args.plugins_root
    if args.dyld_lib:
        env["DYLD_FALLBACK_LIBRARY_PATH"] = args.dyld_lib + ":" + env.get("DYLD_FALLBACK_LIBRARY_PATH", "")

    role = args.role

    def render(preset, wav):
        dump_yaml(preset, str(presets / f"{role}-tmp.yaml"))
        r = subprocess.run([args.render_bin, "--chain", str(presets / f"{role}-tmp.yaml"),
                            "--input", args.di, "--output", wav],
                           env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"render failed:\n{r.stderr}\n{r.stdout}")

    def render_fn(preset, it):
        yml = presets / f"{role}-v{it}.yaml"
        dump_yaml(preset, str(yml))
        render(preset, str(renders / f"{role}-v{it}.wav"))

    def eqmatch_fn(preset, gains, hp, it):
        wav = str(renders / f"{role}-v{it}.wav")
        out = str(diffs / f"{role}-v{it}-eq.json")
        g = ",".join(str(round(x, 4)) for x in gains)
        r = subprocess.run([py, eq_match, args.ref, wav, f"--gains={g}",
                            f"--hp-hz={hp}", f"--output={out}"],
                           env=env, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"eq_match failed:\n{r.stderr}\n{r.stdout}")
        res = json.load(open(out))
        print(f"  {role} v{it}: proximity={res['proximity_pct']:.2f} "
              f"floor={res['self_floor_pct']:.2f} within={res['within_floor']}")
        return res

    out = rebuild(load_yaml(args.base), render_fn, eqmatch_fn, max_iters=args.max_iters)

    # headroom pass: nudge EQ output_db until the DI peak lands in [-8,-6] dBFS
    final = out["final_preset"]
    final_yaml = presets / f"{role}-final.yaml"
    p = eq_block(final)["params"]
    peak_db = -120.0
    for _ in range(5):
        dump_yaml(final, str(final_yaml))
        wav = str(renders / f"{role}-final.wav")
        render(final, wav)
        peak_db = _peak_dbfs(wav)
        if PEAK_LO_DB <= peak_db <= PEAK_HI_DB:
            break
        p["output_db"] = round(_clamp(float(p["output_db"]) + (PEAK_TARGET_DB - peak_db),
                                      OUTPUT_MIN, OUTPUT_MAX), 2)
    out["peak_db"] = round(peak_db, 2)
    out["final_yaml"] = str(final_yaml)
    out.pop("final_preset", None)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
