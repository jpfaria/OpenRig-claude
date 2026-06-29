"""Tests for validate_chain.py — the offline anti-hallucination gate.

`validate_chain` HARD-FAILS on any model id or PLUGIN param the catalog doesn't
know, so an invented id (`nam_made_up`) or an invented plugin param/value
(`air=26`, a `gain` off the manifest axis) can never reach the render.

Option A split:
* PLUGIN blocks (NAM/IR — `catalog.params(model)` is a dict) are HARD-validated
  against the manifest axes: unknown param name OR off-axis value -> ERROR.
* NATIVE blocks (`is_known` true, `catalog.params(model)` is None) have NO
  offline schema, so their params are WARN-only, never an error.

Depends ONLY on the hand-written fixtures under fixtures/catalog/ (reused from
test_catalog.py) — never on the real OpenRig-plugins tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.catalog import load_catalog
from scripts.validate_chain import main, validate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"
NATIVE = FIXTURES / "native_models.yaml"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(FIXTURES, NATIVE)


def _chain(*blocks: dict) -> dict:
    return {"id": "p", "name": "P", "blocks": list(blocks)}


# --- unknown model id ---------------------------------------------------------

def test_unknown_model_id_is_error(catalog):
    result = validate(
        _chain({"type": "amp", "model": "nam_made_up", "params": {}}),
        catalog,
    )
    assert result["ok"] is False
    assert any("nam_made_up" in e for e in result["errors"])


# --- plugin: unknown param name (the air=26 class) ----------------------------

def test_plugin_unknown_param_name_is_error(catalog):
    result = validate(
        _chain(
            {
                "type": "amp",
                "model": "nam_dumble_ods_john_mayer_a2",
                "params": {"air": 26},
            }
        ),
        catalog,
    )
    assert result["ok"] is False
    assert any("air" in e and "nam_dumble_ods_john_mayer_a2" in e for e in result["errors"])


# --- plugin: value outside the declared axis ----------------------------------

def test_plugin_param_value_off_axis_is_error(catalog):
    # axis is [2, 5, 8, 10]; 7 is not a declared value
    result = validate(
        _chain(
            {
                "type": "amp",
                "model": "nam_dumble_ods_john_mayer_a2",
                "params": {"gain": 7},
            }
        ),
        catalog,
    )
    assert result["ok"] is False
    assert any("gain" in e for e in result["errors"])


def test_plugin_param_value_in_axis_is_clean(catalog):
    result = validate(
        _chain(
            {
                "type": "amp",
                "model": "nam_dumble_ods_john_mayer_a2",
                "params": {"gain": 8},
            }
        ),
        catalog,
    )
    assert result["ok"] is True
    assert result["errors"] == []


# --- native block: arbitrary param is WARN-only -------------------------------

def test_native_param_is_warning_not_error(catalog):
    result = validate(
        _chain(
            {
                "type": "dynamics",
                "model": "compressor_studio_clean",
                "params": {"threshold": -20},
            }
        ),
        catalog,
    )
    assert result["ok"] is True
    assert result["errors"] == []
    assert any("threshold" in w and "compressor_studio_clean" in w for w in result["warnings"])


# --- forbidden blocks ---------------------------------------------------------

def test_limiter_brickwall_is_error(catalog):
    result = validate(
        _chain({"type": "limiter", "model": "limiter_brickwall", "params": {}}),
        catalog,
    )
    assert result["ok"] is False
    assert any("limiter_brickwall" in e for e in result["errors"])


def test_volume_type_block_is_error(catalog):
    result = validate(
        _chain({"type": "volume", "model": "some_volume", "params": {}}),
        catalog,
    )
    assert result["ok"] is False
    assert any("volume" in e for e in result["errors"])


# --- a clean, fully valid chain -----------------------------------------------

def test_clean_chain_is_ok(catalog):
    result = validate(
        _chain(
            {
                "type": "amp",
                "model": "nam_dumble_ods_john_mayer_a2",
                "params": {"gain": 8},
            },
            {"type": "filter", "model": "eq_eight_band_parametric", "params": {}},
            {"type": "dynamics", "model": "compressor_studio_clean", "params": {}},
        ),
        catalog,
    )
    assert result["ok"] is True
    assert result["errors"] == []


# --- CLI ----------------------------------------------------------------------

def test_cli_exits_1_on_unknown_model(tmp_path, capsys):
    chain_path = tmp_path / "chain.yaml"
    chain_path.write_text(
        yaml.safe_dump(_chain({"type": "amp", "model": "nam_made_up", "params": {}})),
        encoding="utf-8",
    )
    code = main(
        [
            "--chain",
            str(chain_path),
            "--plugins-root",
            str(FIXTURES),
            "--native-models",
            str(NATIVE),
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "nam_made_up" in out


def test_cli_exits_0_on_clean_chain(tmp_path, capsys):
    chain = _chain(
        {"type": "amp", "model": "nam_dumble_ods_john_mayer_a2", "params": {"gain": 8}},
        {"type": "filter", "model": "eq_eight_band_parametric", "params": {}},
    )
    chain_path = tmp_path / "chain.yaml"
    chain_path.write_text(yaml.safe_dump(chain), encoding="utf-8")
    code = main(
        [
            "--chain",
            str(chain_path),
            "--plugins-root",
            str(FIXTURES),
            "--native-models",
            str(NATIVE),
        ]
    )
    assert code == 0
