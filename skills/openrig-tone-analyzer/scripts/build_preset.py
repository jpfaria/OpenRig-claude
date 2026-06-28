#!/usr/bin/env python3
"""Offline single-tone preset builder -- the deterministic "FORM" of the
openrig-tone-builder skill as ONE portable tool. Builds ONE tone per run.

Given a surviving isolated-guitar reference, a roster of candidate amp/drive
MODEL IDs, and a cab IR, this drives the whole deterministic loop offline:

  1. Measure the reference ONCE: the honest fingerprint (`fingerprint_match_target`)
     gives the reliable range / mask and the per-song self-floor BAR; the
     1/3-octave LTAS is cached as the proximity target.
  2. Per amp, detect whether the capture is DIRECT (head-only, fizzy top that
     needs a cab) by rendering it alone and measuring the top-octave excess.
     A `full_rig` capture already contains the cab and is NEVER direct.
  3. Gear search: for each amp x drive (+ the cab IR iff the amp is direct),
     build the chain `drive(s) -> amp -> cab -> EQ(flat)` -- NO limiter, NO
     volume -- render it, and score `weighted_spectral_proximity_pct` over the
     reliable range. Pick the best combo.
  4. EQ refine on the winner: iterate render -> `next_band_gains` (CAPPED at
     +/-6 dB, dead-top / out-of-range bands HELD at 0) -> apply, until
     within-floor / plateau / iteration cap.
  5. Headroom: set the EQ `output_db` so the DI peak lands ~ -7 dBFS. The chain
     ENDS AT THE EQ -- no limiter, no volume block is ever added.
  6. Write the flat preset YAML (`openrig-render --chain` shape) and a report
     JSON (best amp/drive/cab, proximity, self-floor, within, peak, history).

This SUPERSEDES the old `rebuild_preset.py`, which applied raw uncapped
eq_match gains (piling low-mid, killing presence) and finalised the chain with
a limiter + volume -- both now forbidden. The pure helpers (YAML round-trip,
EQ grid, absolute-gain application, headroom normalisation) are salvaged from
it but ADAPTED: the EQ trim caps at +/-6 (not +/-24) and the chain ends at the
EQ.

The render and measurement calls are INJECTED so the loop logic is unit-testable
without the Rust binary or large WAVs. `main()` wires the real subprocess calls.

PORTABLE BY CONSTRUCTION (skill-rules LAW 1): no machine-tied paths. The
analyzer scripts and venv resolve relative to this file (`sys.executable`,
`Path(__file__)`); the render binary, DI, plugins root and cab IR are CLI/env
inputs only (they live in the OpenRig app / OpenRig-plugins, whose clone
location varies per machine).
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

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import numpy as np  # noqa: E402

from scripts import _common  # noqa: E402
from scripts.eq_match import next_band_gains, next_highpass_hz  # noqa: E402

# numpy scalars (from soundfile/numpy peak math) must serialise cleanly to YAML.
yaml.SafeDumper.add_representer(np.float64, lambda d, v: d.represent_float(float(v)))
yaml.SafeDumper.add_multi_representer(np.floating, lambda d, v: d.represent_float(float(v)))
yaml.SafeDumper.add_multi_representer(np.integer, lambda d, v: d.represent_int(int(v)))


# --- constants -------------------------------------------------------------

EQ_MODEL = "eq_eight_band_parametric"
CAB_IR_MODEL = "generic_ir"
# The render-consumable param key that points a generic_ir block at a wav file.
# Verified against the OpenRig source (crates/block-ir/src/ir_generic_ir.rs:
# file_path_parameter("file", ...) / required_string(params, "file")).
CAB_IR_FILE_KEY = "file"

# block `type` strings (OpenRig EFFECT_TYPE_*). A drive/overdrive pedal is the
# `gain` family; a head-only amp is `amp`; a full-rig capture (cab baked in) is
# `full_rig`; a user-loaded IR is `ir`; the parametric EQ is a `filter`.
TYPE_GAIN = "gain"
TYPE_AMP = "amp"
TYPE_FULL_RIG = "full_rig"
TYPE_IR = "ir"
TYPE_FILTER = "filter"

# eq_match.py operates on this fixed octave grid: band1 = high-pass, bands 2-7
# = peak, band8 = high-shelf. The EQ bands MUST sit on these centres.
GRID_HZ: list[int] = list(_common.BANDS_HZ)  # [80,160,320,640,1280,2560,5120,10240]

# The EQ trim is a GENTLE shape, not a sledgehammer: cap at +/-6 dB (the old
# rebuild_preset used +/-24, which piled low-mid and gutted presence).
EQ_GAIN_MIN, EQ_GAIN_MAX = -6.0, 6.0
OUTPUT_MIN, OUTPUT_MAX = -24.0, 12.0
PEAK_TARGET_DB = -7.0
PEAK_LO_DB, PEAK_HI_DB = -8.0, -6.0

# A head-only (direct) capture leaves the top octave within this many dB of the
# body -- nearly flat to 10 kHz = fizz = "toy sound" -> it needs a cab. A
# real cab/full-rig rolls the top off well below this. NAMED per the FORM.
DIRECT_TOP_EXCESS_DB = 15.0
# Body region (low/mid) and top-octave region (the brilho a cab rolls off), on
# the fine 1/3-octave grid, for the direct-capture decision.
BODY_TOP_HZ = 2500.0
TOP_OCTAVE_LOW_HZ = 6300.0

# The gate is "within this many % of the reference's own self-floor".
SELF_FLOOR_MARGIN_PCT = 3.0


# --- YAML round-trip -------------------------------------------------------

def load_yaml(path: str | os.PathLike) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def dump_yaml(obj: dict, path: str | os.PathLike) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False)


# --- block builders & chain assembly ---------------------------------------

def drive_block(model: str) -> dict:
    """A drive/overdrive/distortion/fuzz pedal -- the `gain` family."""
    return {"type": TYPE_GAIN, "model": model, "enabled": True, "params": {}}


def amp_block(model: str, block_type: str = TYPE_AMP) -> dict:
    """A head-only amp (`amp`) or a full-rig capture (`full_rig`)."""
    return {"type": block_type, "model": model, "enabled": True, "params": {}}


def cab_block(ir_path: str | os.PathLike) -> dict:
    """A cab IR loaded through the portable `generic_ir` loader (params.file)."""
    return {
        "type": TYPE_IR,
        "model": CAB_IR_MODEL,
        "enabled": True,
        "params": {CAB_IR_FILE_KEY: str(ir_path)},
    }


def flat_eq_block() -> dict:
    """The 8-band parametric EQ, flat, with bands on the eq_match grid."""
    block = {"type": TYPE_FILTER, "model": EQ_MODEL, "enabled": True, "params": {}}
    _grid_params(block["params"])
    return block


def _grid_params(p: dict) -> None:
    for i, freq in enumerate(GRID_HZ, start=1):
        if i == 1:
            btype = "high_pass"
        elif i == len(GRID_HZ):
            btype = "high_shelf"
        else:
            btype = "peak"
        p[f"band{i}_enabled"] = True
        p[f"band{i}_type"] = btype
        p[f"band{i}_freq"] = float(freq)
        p[f"band{i}_gain"] = 0.0
        p[f"band{i}_q"] = 1.0
    p["output_db"] = 0.0


def assemble_blocks(
    drive_models: list[str],
    amp_model: str,
    amp_type: str = TYPE_AMP,
    cab_ir: str | os.PathLike | None = None,
) -> list[dict]:
    """Build the flat chain `drive(s) -> amp -> cab -> EQ`.

    - each drive model becomes one `gain` block, in order; the literal token
      `none` (or a falsy model) is omitted (amp-only);
    - the cab IR is added ONLY when `cab_ir` is given AND the amp is not a
      full-rig capture (a full_rig already contains the cab -- never double it);
    - the chain ENDS at the EQ: no limiter, no volume block is ever appended.
    """
    blocks: list[dict] = []
    for m in drive_models:
        if m and m != "none":
            blocks.append(drive_block(m))
    blocks.append(amp_block(amp_model, amp_type))
    if cab_ir is not None and amp_type != TYPE_FULL_RIG:
        blocks.append(cab_block(cab_ir))
    blocks.append(flat_eq_block())
    return blocks


def make_preset(preset_id: str, name: str, blocks: list[dict]) -> dict:
    return {"id": preset_id, "name": name, "blocks": blocks}


def parse_amp_token(token: str) -> tuple[str, str]:
    """Parse an `--amps` token into (model_id, block_type).

    A plain model id is a head-only `amp`. The optional `:full_rig` suffix
    declares a full-rig capture (cab baked in) -- the only block type that
    skips the cab unconditionally. Defaults to `amp` so plain model ids work
    unchanged. (NAM model ids are snake_case slugs, never containing ':'.)
    """
    if ":" in token:
        model, _, suffix = token.rpartition(":")
        if suffix == TYPE_FULL_RIG:
            return model, TYPE_FULL_RIG
    return token, TYPE_AMP


# --- pure EQ helpers -------------------------------------------------------

def eq_block(preset: dict) -> dict:
    for b in preset["blocks"]:
        if b.get("model") == EQ_MODEL:
            return b
    raise ValueError(f"preset has no {EQ_MODEL} block")


def set_eq_grid(preset: dict) -> None:
    """Place the 8 bands on the eq_match grid, flat (gains 0, output 0)."""
    _grid_params(eq_block(preset).setdefault("params", {}))


def band_gains(preset: dict) -> list[float]:
    p = eq_block(preset)["params"]
    return [float(p[f"band{i}_gain"]) for i in range(1, len(GRID_HZ) + 1)]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def apply_band_gains(preset: dict, new_gains, hp_hz) -> None:
    """Set the 8 ABSOLUTE band gains, CAPPED at +/-6 dB (the gentle trim). No
    in-loop normalisation -- that breaks the additive gains feedback. band1's
    high-pass cutoff moves to the eq_match-suggested value."""
    p = eq_block(preset)["params"]
    for i in range(1, len(GRID_HZ) + 1):
        p[f"band{i}_gain"] = round(_clamp(new_gains[i - 1], EQ_GAIN_MIN, EQ_GAIN_MAX), 2)
    p["band1_freq"] = float(hp_hz)


def normalize_for_headroom(preset: dict) -> float:
    """Gain-normalise the EQ: subtract the max positive band gain so the curve
    is cut-biased (nothing boosted), recovering that common-mode level once on
    the EQ output_db. Returns the offset removed."""
    p = eq_block(preset)["params"]
    gains = [float(p[f"band{i}_gain"]) for i in range(1, len(GRID_HZ) + 1)]
    offset = max(gains)
    if offset <= 0:
        return 0.0
    for i in range(1, len(GRID_HZ) + 1):
        p[f"band{i}_gain"] = round(_clamp(gains[i - 1] - offset, EQ_GAIN_MIN, EQ_GAIN_MAX), 2)
    cur = float(p.get("output_db", 0.0))
    p["output_db"] = round(_clamp(cur + offset, OUTPUT_MIN, OUTPUT_MAX), 2)
    return offset


# --- direct-capture detection + hold mask ----------------------------------

def is_direct_capture(
    fine_ltas,
    centers: list[int] | None = None,
    excess_db: float = DIRECT_TOP_EXCESS_DB,
) -> bool:
    """True when an amp-only capture is DIRECT (head-only, no cab): the top
    octave sits within `excess_db` of the low/mid body, i.e. nearly flat to
    10 kHz = fizz. A cab/full-rig rolls the top well below the body -> False."""
    centers = list(_common.THIRD_OCTAVE_CENTERS_HZ) if centers is None else centers
    c = np.asarray(centers, dtype=float)
    v = np.asarray(fine_ltas, dtype=float)
    body_mask = c <= BODY_TOP_HZ
    top_mask = c >= TOP_OCTAVE_LOW_HZ
    if not body_mask.any() or not top_mask.any():
        return False
    body = float(v[body_mask].max())
    top = float(v[top_mask].max())
    return (body - top) <= excess_db


def coarse_hold_mask(ref_8band_ltas, reliable_range_hz) -> np.ndarray:
    """Boolean 8-band mask of the bands the EQ trim may move. HOLDS (False) the
    dead-top separation-artifact bands and any band whose centre is outside the
    reference's reliable range -- those must stay at 0 (never chased)."""
    trust = _common.trustworthy_band_mask(np.asarray(ref_8band_ltas, dtype=float))
    lo, hi = reliable_range_hz
    in_range = np.array([lo <= c <= hi for c in GRID_HZ], dtype=bool)
    return np.asarray(trust, dtype=bool) & in_range


# --- gear search (render/measure injected) ---------------------------------

def decide_cab(amp_model, amp_type, cab_ir, measure_fn):
    """Decide whether an amp needs a cab. A full_rig capture NEVER does (and is
    never measured). Otherwise render the amp alone (flat EQ, no drive, no cab)
    and check the top-octave excess.

    `measure_fn(blocks) -> fine_ltas` renders the blocks through the DI and
    returns the wet 1/3-octave LTAS. Returns (direct: bool, cab_or_None).
    """
    if amp_type == TYPE_FULL_RIG or cab_ir is None:
        return False, None
    amp_only = assemble_blocks([], amp_model, amp_type=amp_type, cab_ir=None)
    direct = is_direct_capture(measure_fn(amp_only))
    return direct, (cab_ir if direct else None)


def _proximity(ref_fine, wet_fine) -> float:
    return float(_common.weighted_spectral_proximity_pct(np.asarray(ref_fine), np.asarray(wet_fine)))


def search_gear(
    amp_candidates: list[tuple[str, str]],
    drive_candidates: list[str],
    cab_ir,
    ref_fine_ltas,
    measure_fn,
    score_fn=None,
) -> dict:
    """Search amp x drive (+ cab iff the amp is direct) for the best spectral
    proximity to the reference, over the reliable range.

    `measure_fn(blocks) -> fine_ltas` renders + measures; `score_fn(ref, wet)`
    scores proximity (defaults to the energy-weighted, reliable-range metric).
    Returns the winning combo, its flat-EQ blocks, and the ranked history.
    """
    score_fn = _proximity if score_fn is None else score_fn
    history: list[dict] = []
    best: dict | None = None

    # cab need is a property of the AMP (measured once per amp), not the drive.
    cab_cache: dict[tuple[str, str], tuple[bool, object]] = {}
    for amp_model, amp_type in amp_candidates:
        key = (amp_model, amp_type)
        if key not in cab_cache:
            cab_cache[key] = decide_cab(amp_model, amp_type, cab_ir, measure_fn)
        direct, cab_for_amp = cab_cache[key]

        for drive in drive_candidates:
            drives = [] if drive == "none" else [drive]
            blocks = assemble_blocks(drives, amp_model, amp_type=amp_type, cab_ir=cab_for_amp)
            prox = score_fn(ref_fine_ltas, measure_fn(blocks))
            rec = {
                "amp": amp_model,
                "amp_type": amp_type,
                "drive": drive,
                "direct": direct,
                "cab_ir": cab_for_amp,
                "proximity_pct": round(float(prox), 2),
            }
            history.append(rec)
            if best is None or prox > best["proximity_pct"]:
                best = {**rec, "proximity_pct": float(prox), "blocks": blocks}

    if best is None:
        raise ValueError("no amp/drive candidates to search")
    return {
        "amp": best["amp"],
        "amp_type": best["amp_type"],
        "drive": best["drive"],
        "direct": best["direct"],
        "cab_ir": best["cab_ir"],
        "proximity_pct": round(best["proximity_pct"], 2),
        "blocks": best["blocks"],
        "history": history,
    }


# --- EQ-refine loop (render/measure injected) ------------------------------

def refine_eq(
    preset: dict,
    ref_8band_ltas,
    hold_mask,
    self_floor_pct: float,
    measure_fn,
    max_iters: int = 6,
    plateau_eps: float = 0.5,
    margin_pct: float = SELF_FLOOR_MARGIN_PCT,
) -> dict:
    """Iterate render -> capped/held trim -> apply until within-floor / plateau
    / cap. The preset already carries the winning chain + a flat EQ grid.

    `measure_fn(preset, it) -> {"wet_8band_ltas", "proximity_pct"}` renders the
    preset through the DI and measures. Each step nudges the EQ by exactly the
    dB each band is short -- CAPPED at +/-6 and with the held bands forced to 0
    (`next_band_gains` zeroes their delta, so they never leave 0). The chain is
    NEVER finalised with a limiter or volume.
    """
    preset = copy.deepcopy(preset)
    ref8 = np.asarray(ref_8band_ltas, dtype=float)
    mask = np.asarray(hold_mask, dtype=bool)

    history: list[tuple] = []
    best = None  # (iter, prox, preset_snapshot)
    for it in range(1, max_iters + 1):
        res = measure_fn(preset, it)
        prox = float(res["proximity_pct"])
        wet8 = np.asarray(res["wet_8band_ltas"], dtype=float)
        within = prox >= self_floor_pct - margin_pct
        history.append((it, round(prox, 2), within))
        if best is None or prox > best[1]:
            best = (it, prox, copy.deepcopy(preset))
        if within:
            break
        if len(history) >= 2 and it >= 3 and (history[-1][1] - history[-2][1]) < plateau_eps:
            break
        cur = band_gains(preset)
        hp = float(eq_block(preset)["params"]["band1_freq"])
        ng = next_band_gains(cur, ref8, wet8, clamp=(EQ_GAIN_MIN, EQ_GAIN_MAX), band_mask=mask)
        nhp = next_highpass_hz(hp, ref8, wet8)
        apply_band_gains(preset, ng, nhp)

    return {
        "history": history,
        "within": best[1] >= self_floor_pct - margin_pct,
        "best_iter": best[0],
        "best_prox": round(best[1], 2),
        "final_preset": best[2],
    }


# --- headroom pass (render injected) ---------------------------------------

def headroom_pass(preset: dict, render_peak_fn, max_iters: int = 5) -> float:
    """Nudge the EQ output_db until the rendered DI peak lands in [-8,-6] dBFS.

    `render_peak_fn(preset) -> peak_dbfs` renders the preset and returns the
    wet peak. The chain ends at the EQ -- level is the EQ output_db alone, no
    limiter, no volume."""
    p = eq_block(preset)["params"]
    peak_db = -120.0
    for _ in range(max_iters):
        peak_db = float(render_peak_fn(preset))
        if PEAK_LO_DB <= peak_db <= PEAK_HI_DB:
            break
        p["output_db"] = round(
            _clamp(float(p.get("output_db", 0.0)) + (PEAK_TARGET_DB - peak_db), OUTPUT_MIN, OUTPUT_MAX),
            2,
        )
    return round(peak_db, 2)


# --- real subprocess wiring (CLI) ------------------------------------------

def _peak_dbfs_of(wav_path: str) -> float:
    import soundfile as sf

    data, _sr = sf.read(wav_path)
    peak = float(np.max(np.abs(data))) if getattr(data, "size", 0) else 0.0
    return 20.0 * math.log10(peak) if peak > 0 else -120.0


def _split_csv(raw: str) -> list[str]:
    return [tok.strip() for tok in raw.split(",") if tok.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline single-tone OpenRig preset builder (the FORM)")
    ap.add_argument("--ref", required=True, help="isolated-guitar reference WAV")
    ap.add_argument("--amps", required=True,
                    help="comma-separated amp MODEL IDs (suffix ':full_rig' for a full-rig capture)")
    ap.add_argument("--drives", required=True,
                    help="comma-separated drive MODEL IDs; the literal 'none' means amp-only")
    ap.add_argument("--cab-ir", required=True, help="4x12 cab IR WAV (used only when an amp is direct)")
    ap.add_argument("--render-bin", required=True, help="path to the installed openrig-render")
    ap.add_argument("--di", required=True, help="bundled DI WAV (assets/audio/input.wav)")
    ap.add_argument("--plugins-root", default="",
                    help="override plugins root (OPENRIG_PLUGINS_ROOT); omit with the installed binary")
    ap.add_argument("--dyld-lib", default="",
                    help="extra DYLD_FALLBACK_LIBRARY_PATH (dev-tree macOS NAM dylib only)")
    ap.add_argument("--out-preset", required=True, help="write the flat preset YAML here")
    ap.add_argument("--name", required=True, help="display name for the preset")
    ap.add_argument("--id", required=True, help="preset id / slug")
    ap.add_argument("--out-report", default="", help="report JSON path (default: next to the preset)")
    ap.add_argument("--max-iters", type=int, default=6)
    args = ap.parse_args(argv)

    out_preset = Path(args.out_preset)
    out_preset.parent.mkdir(parents=True, exist_ok=True)
    out_report = Path(args.out_report) if args.out_report else out_preset.with_suffix(".report.json")
    work = out_preset.parent / f".{args.id}-build"
    work.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    if args.plugins_root:
        env["OPENRIG_PLUGINS_ROOT"] = args.plugins_root
    if args.dyld_lib:
        env["DYLD_FALLBACK_LIBRARY_PATH"] = args.dyld_lib + ":" + env.get("DYLD_FALLBACK_LIBRARY_PATH", "")

    counter = {"n": 0}

    def _render(blocks_or_preset) -> str:
        preset = blocks_or_preset if "blocks" in blocks_or_preset else make_preset(args.id, args.name, blocks_or_preset)
        counter["n"] += 1
        yml = work / f"r{counter['n']:03d}.yaml"
        wav = work / f"r{counter['n']:03d}.wav"
        dump_yaml(preset, str(yml))
        r = subprocess.run(
            [args.render_bin, "--chain", str(yml), "--input", args.di, "--output", str(wav)],
            env=env, capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise SystemExit(f"render failed (exit {r.returncode}):\n{r.stderr}\n{r.stdout}")
        return str(wav)

    def measure_blocks(blocks) -> np.ndarray:
        wav = _render(blocks)
        sig, sr = _common.load_audio(wav)
        return _common.third_octave_ltas(sig, sr)

    # 1. Measure the reference ONCE.
    ref_sig, ref_sr = _common.load_audio(args.ref)
    ref_fine = _common.third_octave_ltas(ref_sig, ref_sr)
    fp = _common.fingerprint_match_target(ref_sig, ref_sr)
    self_floor = float(fp["self_floor_pct"])
    reliable_range = fp["reliable_range_hz"]
    from scripts.eq_match import normalized_ltas  # noqa: E402

    ref_8band = normalized_ltas(ref_sig, ref_sr)
    hold_mask = coarse_hold_mask(ref_8band, reliable_range)

    # 2-3. Gear search.
    amp_candidates = [parse_amp_token(t) for t in _split_csv(args.amps)]
    drive_candidates = _split_csv(args.drives)
    if "none" not in drive_candidates:
        drive_candidates.append("none")
    search = search_gear(amp_candidates, drive_candidates, args.cab_ir, ref_fine, measure_blocks)
    print(f"gear: amp={search['amp']} ({search['amp_type']}) drive={search['drive']} "
          f"direct={search['direct']} proximity={search['proximity_pct']:.2f}")

    # 4. EQ refine on the winner.
    winner = make_preset(args.id, args.name, search["blocks"])
    set_eq_grid(winner)

    def measure_preset(preset, it) -> dict:
        wav = _render(preset)
        sig, sr = _common.load_audio(wav)
        wet_fine = _common.third_octave_ltas(sig, sr)
        wet_8band = normalized_ltas(sig, sr)
        prox = _proximity(ref_fine, wet_fine)
        print(f"  refine v{it}: proximity={prox:.2f} floor={self_floor:.2f}")
        return {"wet_8band_ltas": wet_8band, "proximity_pct": prox}

    refined = refine_eq(winner, ref_8band, hold_mask, self_floor, measure_preset,
                        max_iters=args.max_iters)
    final = refined["final_preset"]

    # 5. Headroom -- chain ends at the EQ (no limiter, no volume).
    normalize_for_headroom(final)

    def render_peak(preset) -> float:
        return _peak_dbfs_of(_render(preset))

    peak_db = headroom_pass(final, render_peak)

    # 6. Write outputs.
    dump_yaml(final, str(out_preset))
    report = {
        "id": args.id,
        "name": args.name,
        "amp": search["amp"],
        "amp_type": search["amp_type"],
        "drive": search["drive"],
        "direct": search["direct"],
        "cab_ir": search["cab_ir"],
        "proximity_pct": search["proximity_pct"],
        "self_floor_pct": round(self_floor, 2),
        "within": bool(refined["within"]),
        "best_prox": refined["best_prox"],
        "peak_db": peak_db,
        "reliable_range_hz": reliable_range,
        "refine_history": refined["history"],
        "gear_history": search["history"],
        "preset_path": str(out_preset),
    }
    out_report.write_text(json.dumps(_common.round_for_json(report), indent=2), encoding="utf-8")
    print(json.dumps({"preset": str(out_preset), "report": str(out_report),
                      "proximity_pct": search["proximity_pct"], "within": refined["within"],
                      "peak_db": peak_db}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
