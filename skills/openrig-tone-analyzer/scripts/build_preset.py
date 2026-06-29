#!/usr/bin/env python3
"""Offline single-tone preset builder -- the deterministic "FORM" of the
openrig-tone-builder skill as ONE portable tool. Builds ONE tone per run.

The caller (the tone-builder FORM) researches the COMPLETE rig and writes it as
a **base-chain YAML**: a flat `blocks:` list in signal order, where every
researched block (compressor, wah, pitch, modulation, delay, reverb, a
non-EQ filter, an acoustic body, ...) is present with its researched params.
Blocks the tool should SEARCH carry a `candidates:` list instead of a fixed
`model`; the ONE `eq_eight_band_parametric` filter is the slot the tool TUNES.
This tool keeps every other block FIXED/verbatim and optimizes only the
timbre-determining slots:

  1. Measure the reference ONCE: the honest fingerprint (`fingerprint_match_target`)
     gives the reliable range / mask and the per-song self-floor BAR; the
     1/3-octave LTAS is cached as the proximity target.
  2. Classify the base chain: SEARCH (preamp/amp/body core + gain drive(s) +
     cab -- those carrying `candidates:`), TUNE (the eq_eight_band filter), and
     FIXED pass-through (everything else, preserved verbatim in signal order).
  3. Gear search: enumerate the cartesian product over the SEARCH slots'
     candidate lists (`none` => that slot empty; multiple `gain` slots => a
     drive STACK). For each combo, render the FULL chain (all FIXED FX present)
     and score `weighted_spectral_proximity_pct` over the reliable range. Pick
     the best combo. `--cab-model` auto-inserts a `type: cab` PLUGIN block
     (catalog model id, whose manifest `output_gain_db` makes the level right)
     right after the amp ONLY when the amp renders DIRECT, there is no researched
     cab already, and the amp is not `:full_rig`. (A raw off-catalog IR is the
     separate `generic_ir` escape, authored directly in the base chain.)
  4. EQ refine on the winner: iterate render -> `next_band_gains` (CAPPED at
     +/-6 dB, dead-top / out-of-range bands HELD at 0) -> apply, until
     within-floor / plateau / iteration cap.
  5. Headroom: set the EQ `output_db` so the DI peak lands ~ -7 dBFS. The chain
     ENDS AT THE EQ -- no limiter, no volume block is ever added (any
     `limiter_brickwall` / `volume` in the base chain is STRIPPED).
  6. Write the preset YAML (`openrig-render --chain` shape) and a report JSON
     (chosen amp/drive(s)/cab, proximity, self-floor, within, peak, the FIXED
     FX preserved, history).

This SUPERSEDES the old `rebuild_preset.py`, which applied raw uncapped
eq_match gains (piling low-mid, killing presence) and finalised the chain with
a limiter + volume -- both now forbidden. The pure helpers (YAML round-trip,
EQ grid, absolute-gain application, headroom normalisation) are salvaged from
it but ADAPTED: the EQ trim caps at +/-6 (not +/-24) and the chain ends at the
EQ.

CRITICAL real-world detail: `openrig-render` exits 0 even when it cannot build
a block -- it prints `ignoring unsupported or invalid block ...` /
`unsupported nam model '<id>'` and renders WITHOUT that block. So a non-zero
exit is NOT enough: the real render path captures stdout+stderr and treats
those markers as a HARD FAILURE (`assert_no_dropped_blocks`), so a typo'd model
id can never silently ship a preset missing a block.

The render and measurement calls are INJECTED so the loop logic is unit-testable
without the Rust binary or large WAVs. `main()` wires the real subprocess calls.

PORTABLE BY CONSTRUCTION (skill-rules LAW 1): no machine-tied paths. The
analyzer scripts and venv resolve relative to this file (`sys.executable`,
`Path(__file__)`); the render binary, DI, plugins root and cab model id are
CLI/env inputs only (they live in the OpenRig app / OpenRig-plugins, whose clone
location varies per machine).
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
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
# The off-catalog raw-IR loader (`type: ir`). It loads a RAW wav and applies NO
# catalog normalization -- it is the explicit escape for a genuinely off-catalog
# IR, NEVER the default cab. A catalog cab is a `type: cab` PLUGIN block (see
# cab_block), whose manifest carries the per-capture `output_gain_db` the render
# applies so the cab level is right.
GENERIC_IR_MODEL = "generic_ir"
# The render-consumable param key that points a generic_ir block at a wav file.
# Verified against the OpenRig source (crates/block-ir/src/ir_generic_ir.rs:
# file_path_parameter("file", ...) / required_string(params, "file")).
GENERIC_IR_FILE_KEY = "file"

# block `type` strings (OpenRig EFFECT_TYPE_*). A drive/overdrive pedal is the
# `gain` family; a head-only amp is `amp`; a full-rig capture (cab baked in) is
# `full_rig`; a user-loaded IR is `ir`; the parametric EQ is a `filter`.
TYPE_GAIN = "gain"
TYPE_AMP = "amp"
TYPE_PREAMP = "preamp"
TYPE_BODY = "body"
TYPE_CAB = "cab"
TYPE_FULL_RIG = "full_rig"
TYPE_IR = "ir"
TYPE_FILTER = "filter"

# Core, head-style timbre slots that the `--cab-model` direct-capture rule may
# sit a cab after. An acoustic `body` core is searched like an amp but is NEVER
# given a guitar cab.
CAB_ANCHOR_TYPES = {TYPE_AMP, TYPE_PREAMP}
# The timbre-determining CORE is identified by TYPE, never by the presence of a
# `candidates:` list. A `type: amp/preamp/body` block is the core whether it is
# PINNED (a fixed `model:` -> a single variant used verbatim) or SEARCHED (a
# `candidates:` list). The number REGULATES the core (EQ trim, gain-axis when
# given as candidates, drive, cab, level) -- it never swaps a PINNED amp model.
CORE_TYPES = {TYPE_AMP, TYPE_PREAMP, TYPE_BODY}
# Block types that count as a researched cab already in the chain (so the
# `--cab-model` auto-insert is suppressed -- never double a cabinet). A `type:
# cab` catalog plugin OR an off-catalog `type: ir` raw loader both count.
RESEARCHED_CAB_TYPES = {TYPE_CAB, TYPE_IR}

# Blocks the chain must NEVER emit: a brickwall limiter or a volume block. They
# are stripped from the base chain and never re-added (the chain ends at the EQ).
FORBIDDEN_MODELS = {"limiter_brickwall"}
FORBIDDEN_TYPES = {"volume"}

# Slot roles after classifying the base chain.
ROLE_SEARCH = "search"   # carries a `candidates:` list -> optimized by proximity
ROLE_TUNE = "tune"       # the ONE eq_eight_band filter -> trimmed (+/-6, held)
ROLE_FIXED = "fixed"     # everything else -> preserved verbatim in place

# Param provenance (Rule B). A base-chain block MAY carry an optional helper key
# `provenance:` declaring where its FX params came from:
#   `sourced`    -- documented (rig rundown / interview) -> used as-is;
#   `derived`    -- computed (e.g. delay time = tempo math from the song BPM);
#   `unverified` -- a sensible default with NO source, must be surfaced.
# Like `candidates:`, this is METADATA, stripped from the emitted preset (it is
# not a real OpenRig param). A MISSING marker is conservatively `unverified`: a
# default presented without a source must never read as sourced.
PROVENANCE_KEY = "provenance"
PROV_SOURCED = "sourced"
PROV_DERIVED = "derived"
PROV_UNVERIFIED = "unverified"
PROVENANCE_CLASSES = {PROV_SOURCED, PROV_DERIVED, PROV_UNVERIFIED}
# Helper keys that are build-time metadata, never emitted as OpenRig params.
HELPER_KEYS = ("candidates", PROVENANCE_KEY)

# Render-output markers proving openrig-render dropped a block despite exit 0.
DROPPED_BLOCK_MARKERS = (
    "ignoring unsupported or invalid block",
    "unsupported or invalid block",
    "unsupported nam model",
)

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


def cab_block(cab_model: str) -> dict:
    """A cab PLUGIN block (`type: cab`) referencing a catalog cab model id (e.g.
    `ir_marshall_4x12_v30`). The render loads the plugin and APPLIES its
    per-capture `output_gain_db`, so the cab comes in at the correct level. This
    is the auto-insert mechanism (`--cab-model`) -- NOT a raw-IR loader.
    """
    return {"type": TYPE_CAB, "model": str(cab_model), "enabled": True, "params": {}}


def generic_ir_block(ir_path: str | os.PathLike) -> dict:
    """A RAW IR wav loaded through the portable `generic_ir` loader (params.file).

    OFF-CATALOG ESCAPE ONLY. `generic_ir` applies NO catalog `output_gain_db`, so
    a raw wav comes in un-normalized (~18 dB hotter than a catalog cab plugin) --
    it must NEVER stand in for a catalog cab. Use it only for a genuinely
    off-catalog IR the user supplies as a wav; the agent authors this block
    directly in the base chain (it is then a FIXED researched cab). The
    auto-insert path uses `cab_block` (a `type: cab` plugin), never this.
    """
    return {
        "type": TYPE_IR,
        "model": GENERIC_IR_MODEL,
        "enabled": True,
        "params": {GENERIC_IR_FILE_KEY: str(ir_path)},
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
    cab_model: str | None = None,
) -> list[dict]:
    """Build the flat chain `drive(s) -> amp -> cab -> EQ`.

    - each drive model becomes one `gain` block, in order; the literal token
      `none` (or a falsy model) is omitted (amp-only);
    - the cab is a `type: cab` PLUGIN block (catalog model id) added ONLY when
      `cab_model` is given AND the amp is not a full-rig capture (a full_rig
      already contains the cab -- never double it). The plugin's `output_gain_db`
      makes the level right;
    - the chain ENDS at the EQ: no limiter, no volume block is ever appended.
    """
    blocks: list[dict] = []
    for m in drive_models:
        if m and m != "none":
            blocks.append(drive_block(m))
    blocks.append(amp_block(amp_model, amp_type))
    if cab_model is not None and amp_type != TYPE_FULL_RIG:
        blocks.append(cab_block(cab_model))
    blocks.append(flat_eq_block())
    return blocks


def make_preset(preset_id: str, name: str, blocks: list[dict]) -> dict:
    return {"id": preset_id, "name": name, "blocks": blocks}


FULL_RIG_SUFFIX = ":full_rig"


def parse_candidate(token: str | dict) -> tuple[str, bool, dict]:
    """Parse a SEARCH-slot candidate into (model_id, is_full_rig, params).

    A candidate is EITHER a bare model-id string (rendered at the capture's
    DEFAULT params) OR a mapping carrying per-candidate params:

      - a bare string -- used as-is (NAM ids are snake_case slugs and keep their
        architecture suffix, e.g. `nam_marshall_1959_slp_a2`), with EMPTY params;
      - the literal `none` keeps the slot EMPTY (returned verbatim as `none`);
      - the optional `:full_rig` suffix declares a capture that already contains
        the cab -- it sets the block type to `full_rig` and skips the cab
        unconditionally. (Model ids never contain ':', so the split is safe.)
      - a mapping `{model: <id>, params: {<axis>: <value>, ...}}` carries
        per-candidate params applied to that block (e.g. cranking a modded-amp
        capture's own `gain` axis). An optional `full_rig: true` on the mapping
        is EQUIVALENT to the `:full_rig` string suffix. Two mappings of the same
        model with different `params` are two DISTINCT search variants.

    Returns `params = {}` for a bare string; the per-candidate params dict (a
    fresh copy) for a mapping. The params are REAL block params, never stripped.
    """
    if isinstance(token, dict):
        model = str(token["model"]).strip()
        full_rig = bool(token.get("full_rig", False))
        params = dict(token.get("params") or {})
        if model.endswith(FULL_RIG_SUFFIX):
            model, full_rig = model[: -len(FULL_RIG_SUFFIX)], True
        return model, full_rig, params
    token = token.strip()
    if token == "none":
        return "none", False, {}
    if token.endswith(FULL_RIG_SUFFIX):
        return token[: -len(FULL_RIG_SUFFIX)], True, {}
    return token, False, {}


# --- base-chain classification & forbidden-block stripping -----------------

@dataclass
class Slot:
    """A classified base-chain block: its role (search/tune/fixed), the block
    dict (a deep copy -- never the caller's), and its candidate list when it is
    a SEARCH slot."""

    role: str
    block: dict
    candidates: list[str | dict] | None = None


def is_forbidden(block: dict) -> bool:
    return block.get("model") in FORBIDDEN_MODELS or block.get("type") in FORBIDDEN_TYPES


def strip_forbidden(blocks: list[dict]) -> list[dict]:
    """Return the chain with every `limiter_brickwall` / `volume` block removed
    (deep-copied, so the caller's list is untouched). The chain ends at the EQ."""
    return [copy.deepcopy(b) for b in blocks if not is_forbidden(b)]


def pinned_core_candidate(block: dict) -> str | dict:
    """Synthesize the SINGLE search candidate for a PINNED core (a `type:
    amp/preamp/body` block with a fixed `model:` and no `candidates:`).

    The pinned amp is the artist's actual amp, authored verbatim -- it is used
    as-is, never swapped. When the block carries `params:` (e.g. a fixed gain
    axis), they ride along as the candidate's per-candidate params so they land
    on the emitted block AND are recorded in the report; otherwise a bare model
    string (default params)."""
    model = block.get("model")
    params = block.get("params") or {}
    if params:
        return {"model": model, "params": dict(params)}
    return model


def classify_chain(blocks: list[dict]) -> list[Slot]:
    """Classify a flat base chain (signal order preserved) into SEARCH / TUNE /
    FIXED slots, dropping any forbidden (`limiter_brickwall` / `volume`) block.

    - the CORE is identified by TYPE: a `type: amp/preamp/body` block is SEARCH
      whether it is PINNED (a fixed `model:` -> a single synthesized variant,
      used verbatim but still the cabbable/recorded core) or SEARCHED (a
      `candidates:` list of gain-axis or stand-in variants);
    - any other block carrying a non-empty `candidates:` list (e.g. a `gain` or
      `cab` SEARCH slot) => SEARCH (optimized);
    - the `eq_eight_band_parametric` filter (no candidates) => TUNE (trimmed);
    - everything else (dynamics, wah, pitch, mod, delay, reverb, a non-EQ
      filter, a researched cab, ...) => FIXED pass-through, preserved verbatim.
    """
    slots: list[Slot] = []
    for b in strip_forbidden(blocks):
        cands = b.get("candidates")
        if cands:
            slots.append(Slot(ROLE_SEARCH, b, list(cands)))
        elif b.get("type") in CORE_TYPES:
            # PINNED core: a fixed-model amp/preamp/body, still the searchable,
            # cabbable, recorded core -- a single synthesized candidate.
            slots.append(Slot(ROLE_SEARCH, b, [pinned_core_candidate(b)]))
        elif b.get("type") == TYPE_FILTER and b.get("model") == EQ_MODEL:
            slots.append(Slot(ROLE_TUNE, b, None))
        else:
            slots.append(Slot(ROLE_FIXED, b, None))
    return slots


def block_provenance(block: dict) -> str:
    """Classify a block's FX-param provenance (Rule B). Returns the declared
    `provenance:` marker when it is one of `sourced` / `derived` / `unverified`;
    an ABSENT or unrecognised marker is conservatively `unverified` -- a default
    presented without a source must never read as sourced."""
    val = block.get(PROVENANCE_KEY)
    return val if val in PROVENANCE_CLASSES else PROV_UNVERIFIED


def strip_helper_keys(block: dict) -> dict:
    """Remove every build-time helper key (`candidates`, `provenance`) from a
    block in place and return it -- those are metadata, never real OpenRig
    params, so they are stripped from the emitted preset."""
    for k in HELPER_KEYS:
        block.pop(k, None)
    return block


def param_provenance_report(slots: list[Slot]) -> dict:
    """Build the report's `param_provenance` section from the FIXED FX slots.

    Returns `{"blocks": [{type, model, provenance}, ...], "unverified": [...]}`:
    every FIXED block's provenance class, plus an explicit `unverified` list of
    the FX blocks whose params are unverified -- so the agent can surface them
    to the user (Rule B). SEARCH slots (amp/drive chosen by the number from
    research-derived candidates) and the TUNE EQ are reported elsewhere; param
    provenance is for the FIXED FX params only."""
    blocks: list[dict] = []
    unverified: list[dict] = []
    for s in slots:
        if s.role != ROLE_FIXED:
            continue
        prov = block_provenance(s.block)
        entry = {"type": s.block.get("type"), "model": s.block.get("model"), "provenance": prov}
        blocks.append(entry)
        if prov == PROV_UNVERIFIED:
            unverified.append({"type": entry["type"], "model": entry["model"]})
    return {"blocks": blocks, "unverified": unverified}


def assert_no_dropped_blocks(render_output: str) -> None:
    """Raise if openrig-render's output proves it silently dropped a block.

    The renderer exits 0 even when it cannot build a block -- it logs
    `ignoring unsupported or invalid block ...` / `unsupported nam model '<id>'`
    and renders the chain WITHOUT that block. A typo'd / uninstalled model id
    must therefore be caught from the OUTPUT, not the exit code, so a preset
    that silently lost a researched block can never ship."""
    low = (render_output or "").lower()
    for marker in DROPPED_BLOCK_MARKERS:
        if marker in low:
            raise SystemExit(
                "openrig-render dropped a block (invalid/uninstalled model id?) -- "
                "refusing to ship a preset missing a researched block:\n"
                + (render_output or "").strip()[:800]
            )


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

def decide_cab(amp_model, amp_type, cab_model, measure_fn):
    """Decide whether an amp needs a cab. A full_rig capture NEVER does (and is
    never measured). Otherwise render the amp alone (flat EQ, no drive, no cab)
    and check the top-octave excess.

    `measure_fn(blocks) -> fine_ltas` renders the blocks through the DI and
    returns the wet 1/3-octave LTAS. Returns (direct: bool, cab_model_or_None).
    """
    if amp_type == TYPE_FULL_RIG or cab_model is None:
        return False, None
    amp_only = assemble_blocks([], amp_model, amp_type=amp_type, cab_model=None)
    direct = is_direct_capture(measure_fn(amp_only))
    return direct, (cab_model if direct else None)


def _proximity(ref_fine, wet_fine) -> float:
    return float(_common.weighted_spectral_proximity_pct(np.asarray(ref_fine), np.asarray(wet_fine)))


def _resolve_combo(slots: list[Slot], combo: tuple, flat_eq: dict) -> tuple[list[dict], dict]:
    """Resolve one candidate combo into a full chain (without the auto cab yet).

    Walks the classified slots in signal order: FIXED blocks are copied
    verbatim, the TUNE slot becomes a flat-grid EQ, and each SEARCH slot takes
    its chosen candidate (`none` => omitted; `:full_rig` => `full_rig` type).
    Returns (blocks, info) where `info` records the chosen amp/drives/core, the
    amp's position, whether it is full_rig, and whether a researched cab is
    already present. If the chain carries no EQ slot, a flat EQ is appended so
    the chain still ends at the EQ.
    """
    blocks: list[dict] = []
    info = {
        "drives": [], "drive_params": [], "amp": None, "amp_type": None,
        "amp_pos": None, "amp_full_rig": False, "amp_params": {}, "core": None,
        "core_params": {}, "cab_model": None, "cab_params": {},
        "has_researched_cab": False,
    }
    eq_present = False
    si = 0
    for slot in slots:
        if slot.role == ROLE_FIXED:
            b = strip_helper_keys(copy.deepcopy(slot.block))
            blocks.append(b)
            if b.get("type") in RESEARCHED_CAB_TYPES:
                info["has_researched_cab"] = True
            continue
        if slot.role == ROLE_TUNE:
            blocks.append(copy.deepcopy(flat_eq))
            eq_present = True
            continue
        # SEARCH slot
        token = combo[si]
        si += 1
        model, full_rig, params = parse_candidate(token)
        if model == "none":
            continue
        b = strip_helper_keys(copy.deepcopy(slot.block))
        b["model"] = model
        if full_rig:
            b["type"] = TYPE_FULL_RIG
        b.setdefault("enabled", True)
        b.setdefault("params", {})
        # the candidate's per-candidate params are REAL block params (e.g. a
        # modded-amp capture cranked on its own `gain` axis) -- apply them onto
        # the searched block so the chosen variant carries them into the preset.
        if params:
            b["params"].update(copy.deepcopy(params))
        blocks.append(b)
        t = slot.block.get("type")
        if t == TYPE_GAIN:
            info["drives"].append(model)
            info["drive_params"].append(dict(params))
        elif t in CAB_ANCHOR_TYPES:
            info["amp"] = model
            info["amp_type"] = TYPE_FULL_RIG if full_rig else t
            info["amp_full_rig"] = full_rig
            info["amp_pos"] = len(blocks) - 1
            info["amp_params"] = dict(params)
        elif t == TYPE_BODY:
            info["core"] = model
            info["core_params"] = dict(params)
        elif t == TYPE_CAB:
            info["cab_model"] = model
            info["cab_params"] = dict(params)
            info["has_researched_cab"] = True
    if not eq_present:
        blocks.append(copy.deepcopy(flat_eq))
    return blocks, info


def search_chain(
    slots: list[Slot],
    ref_fine_ltas,
    measure_fn,
    cab_model=None,
    score_fn=None,
    flat_eq: dict | None = None,
) -> dict:
    """Search the cartesian product over the base chain's SEARCH slots for the
    full chain with the best spectral proximity to the reference.

    Each combo renders the FULL chain (all FIXED FX in place, flat EQ). The
    `--cab-model` cab (a `type: cab` plugin) is auto-inserted right after the amp
    ONLY when the amp renders DIRECT, there is no researched cab already, and the
    amp is not `:full_rig`. `measure_fn(blocks) -> fine_ltas` renders+measures;
    `score_fn(ref, wet)` scores proximity (defaults to the energy-weighted,
    reliable-range metric). Returns the winning chain, the chosen gear, and the
    ranked history.
    """
    score_fn = _proximity if score_fn is None else score_fn
    flat_eq = flat_eq_block() if flat_eq is None else flat_eq
    search_slots = [s for s in slots if s.role == ROLE_SEARCH]
    cand_lists = [s.candidates for s in search_slots]

    # cab need is a property of the AMP model (measured once per amp), not the
    # drive/combo -- cache it across combos.
    cab_cache: dict[tuple, tuple[bool, object]] = {}
    history: list[dict] = []
    best: dict | None = None

    for combo in itertools.product(*cand_lists):
        blocks, info = _resolve_combo(slots, combo, flat_eq)

        direct, cab_used = False, None
        if info["amp"] and cab_model is not None and not info["has_researched_cab"]:
            key = (info["amp"], info["amp_type"])
            if key not in cab_cache:
                cab_cache[key] = decide_cab(info["amp"], info["amp_type"], cab_model, measure_fn)
            direct, cab_used = cab_cache[key]
            if cab_used is not None and info["amp_pos"] is not None:
                blocks.insert(info["amp_pos"] + 1, cab_block(cab_used))

        prox = float(score_fn(ref_fine_ltas, measure_fn(blocks)))
        rec = {
            "amp": info["amp"], "amp_type": info["amp_type"],
            "amp_params": dict(info["amp_params"]), "drives": list(info["drives"]),
            "drive_params": [dict(p) for p in info["drive_params"]],
            "core": info["core"], "core_params": dict(info["core_params"]),
            "direct": direct, "cab_model": cab_used,
            "proximity_pct": round(prox, 2),
        }
        history.append(rec)
        if best is None or prox > best["_prox"]:
            best = {**rec, "_prox": prox, "blocks": blocks}

    if best is None:
        raise ValueError("no candidate combos to search")
    return {
        "amp": best["amp"], "amp_type": best["amp_type"],
        "amp_params": best["amp_params"], "drives": best["drives"],
        "drive_params": best["drive_params"], "core": best["core"],
        "core_params": best["core_params"], "direct": best["direct"],
        "cab_model": best["cab_model"], "proximity_pct": round(best["_prox"], 2),
        "blocks": best["blocks"], "history": history,
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline single-tone OpenRig preset builder (the FORM)")
    ap.add_argument("--base-chain", required=True,
                    help="researched full-rig base-chain YAML (flat `blocks:` in signal order; "
                         "SEARCH slots carry `candidates:`, the eq_eight_band filter is TUNED)")
    ap.add_argument("--ref", required=True, help="isolated-guitar reference WAV")
    ap.add_argument("--cab-model", default="",
                    help="catalog cab PLUGIN model id (a `type: cab` plugin, e.g. ir_marshall_4x12_v30); "
                         "auto-inserted after the amp ONLY when the amp renders direct and no researched "
                         "cab is present (omit for a full-rig / cabbed base chain). The plugin's "
                         "output_gain_db makes the cab level right; a raw generic_ir wav would not")
    # BREAKING: the old `--cab-ir <wav>` loaded a RAW IR through generic_ir, which
    # bypasses the cab plugin's per-capture output_gain_db (renders ~18 dB hot).
    # It is replaced by `--cab-model <cab_model_id>`. Kept as a deprecated alias
    # that ERRORS with a pointer (a raw wav must NOT be accepted as a cab model).
    ap.add_argument("--cab-ir", default="", help=argparse.SUPPRESS)
    ap.add_argument("--render-bin", required=True, help="path to the installed openrig-render")
    ap.add_argument("--di", required=True, help="bundled DI WAV (assets/audio/input.wav)")
    ap.add_argument("--plugins-root", default="",
                    help="override plugins root (OPENRIG_PLUGINS_ROOT); omit with the installed binary")
    ap.add_argument("--dyld-lib", default="",
                    help="extra DYLD_FALLBACK_LIBRARY_PATH (dev-tree macOS NAM dylib only)")
    ap.add_argument("--out-preset", required=True, help="write the preset YAML here")
    ap.add_argument("--name", default="", help="display name (default: base chain's `name`)")
    ap.add_argument("--id", default="", help="preset id / slug (default: base chain's `id`)")
    ap.add_argument("--out-report", default="", help="report JSON path (default: next to the preset)")
    ap.add_argument("--max-iters", type=int, default=6)
    args = ap.parse_args(argv)

    if args.cab_ir:
        raise SystemExit(
            "--cab-ir is removed: it loaded a RAW IR through generic_ir and bypassed the "
            "cab plugin's per-capture output_gain_db (renders ~18 dB hot). Use "
            "--cab-model <cab_model_id> with a catalog `type: cab` plugin (e.g. "
            "ir_marshall_4x12_v30) so the render applies the manifest output_gain_db. For a "
            "genuinely off-catalog IR, author a {type: ir, model: generic_ir, params:{file}} "
            "block directly in the base chain instead."
        )

    # Parse the base chain and classify its slots (forbidden blocks stripped).
    base = load_yaml(args.base_chain) or {}
    raw_blocks = base.get("blocks") or []
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise SystemExit(f"--base-chain has no `blocks:` list: {args.base_chain}")
    slots = classify_chain(raw_blocks)
    preset_id = args.id or base.get("id") or "preset"
    name = args.name or base.get("name") or preset_id
    cab_model = args.cab_model or None
    fixed_fx = [
        {"type": s.block.get("type"), "model": s.block.get("model")}
        for s in slots if s.role == ROLE_FIXED
    ]

    out_preset = Path(args.out_preset)
    out_preset.parent.mkdir(parents=True, exist_ok=True)
    out_report = Path(args.out_report) if args.out_report else out_preset.with_suffix(".report.json")
    work = out_preset.parent / f".{preset_id}-build"
    work.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    if args.plugins_root:
        env["OPENRIG_PLUGINS_ROOT"] = args.plugins_root
    if args.dyld_lib:
        env["DYLD_FALLBACK_LIBRARY_PATH"] = args.dyld_lib + ":" + env.get("DYLD_FALLBACK_LIBRARY_PATH", "")

    counter = {"n": 0}

    def _render(blocks_or_preset) -> str:
        preset = blocks_or_preset if "blocks" in blocks_or_preset else make_preset(preset_id, name, blocks_or_preset)
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
        # openrig-render exits 0 even when it could not build a block -- catch a
        # dropped/invalid model id from the OUTPUT so a preset never silently
        # ships missing a researched block.
        assert_no_dropped_blocks((r.stdout or "") + "\n" + (r.stderr or ""))
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

    # 2-3. Search the timbre slots (full chain rendered each combo).
    search = search_chain(slots, ref_fine, measure_blocks, cab_model=cab_model)
    print(f"gear: amp={search['amp']} ({search['amp_type']}) drives={search['drives']} "
          f"core={search['core']} direct={search['direct']} proximity={search['proximity_pct']:.2f}")

    # 4. EQ refine on the winning full chain.
    winner = make_preset(preset_id, name, search["blocks"])
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

    # 5. Headroom -- chain ends at the EQ (no limiter, no volume). Strip any
    # forbidden block defensively before writing.
    normalize_for_headroom(final)

    def render_peak(preset) -> float:
        return _peak_dbfs_of(_render(preset))

    peak_db = headroom_pass(final, render_peak)
    final["blocks"] = strip_forbidden(final["blocks"])

    # 6. Write outputs.
    dump_yaml(final, str(out_preset))
    report = {
        "id": preset_id,
        "name": name,
        "amp": search["amp"],
        "amp_type": search["amp_type"],
        "amp_params": search["amp_params"],
        "drives": search["drives"],
        "drive_params": search["drive_params"],
        "core": search["core"],
        "core_params": search["core_params"],
        "direct": search["direct"],
        "cab_model": search["cab_model"],
        "fixed_fx_preserved": fixed_fx,
        "param_provenance": param_provenance_report(slots),
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
