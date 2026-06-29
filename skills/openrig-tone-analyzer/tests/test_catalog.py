"""Tests for the deterministic, offline catalog index (catalog.py).

The catalog turns the on-disk OpenRig plugin manifests + a committed native-model
list into a queryable index, so later tools resolve/validate model ids OFFLINE
and the agent never types a model id from memory.

These tests depend ONLY on hand-written fixtures under fixtures/catalog/ —
never on the real OpenRig-plugins tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.catalog import load_catalog

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"
NATIVE = FIXTURES / "native_models.yaml"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(FIXTURES, NATIVE)


# --- indexing -----------------------------------------------------------------

def test_indexes_each_manifest_id(catalog):
    for model_id in (
        "nam_dumble_ods_john_mayer_a2",
        "nam_dumble_a2",
        "ir_marshall_4x12_v30",
        "nam_ibanez_ts808_a2",
    ):
        assert catalog.is_known(model_id), f"{model_id} should be indexed"


def test_meta_carries_type_brand_display_backend(catalog):
    meta = catalog.meta("nam_dumble_ods_john_mayer_a2")
    assert meta is not None
    assert meta["type"] == "amp"
    assert meta["brand"] == "dumble"
    assert meta["display_name"] == "Dumble ODS John Mayer"
    assert meta["backend"] == "nam"


def test_meta_for_unknown_is_none(catalog):
    assert catalog.meta("nam_totally_made_up_a2") is None


# --- params -------------------------------------------------------------------

def test_params_of_plugin_returns_manifest_axis(catalog):
    assert catalog.params("nam_dumble_ods_john_mayer_a2") == {"gain": [2, 5, 8, 10]}


def test_params_of_multi_axis_plugin(catalog):
    assert catalog.params("nam_ibanez_ts808_a2") == {
        "drive": [0, 5, 10],
        "tone": [3, 7],
    }


def test_params_of_native_is_none(catalog):
    # native id is known but has NO offline param schema
    assert catalog.is_known("eq_eight_band_parametric")
    assert catalog.params("eq_eight_band_parametric") is None


def test_params_of_unknown_is_none(catalog):
    assert catalog.params("nam_totally_made_up_a2") is None


# --- is_known -----------------------------------------------------------------

def test_is_known_true_for_native_id(catalog):
    assert catalog.is_known("brit_4x12")
    assert catalog.is_known("compressor_studio_clean")


def test_is_known_false_for_made_up_id(catalog):
    assert not catalog.is_known("nam_fender_twin_imaginary_a2")
    assert not catalog.is_known("")


# --- find: ranking ------------------------------------------------------------

def test_find_ranks_signature_capture_first(catalog):
    results = catalog.find("dumble john mayer", type="amp")
    assert results, "expected at least one match"
    assert results[0].model_id == "nam_dumble_ods_john_mayer_a2"
    # the generic dumble must also match but rank BELOW the signature one
    ids = [m.model_id for m in results]
    assert "nam_dumble_a2" in ids
    assert ids.index("nam_dumble_ods_john_mayer_a2") < ids.index("nam_dumble_a2")


def test_find_match_has_expected_fields(catalog):
    m = catalog.find("dumble john mayer", type="amp")[0]
    assert m.model_id == "nam_dumble_ods_john_mayer_a2"
    assert m.type == "amp"
    assert m.brand == "dumble"
    assert m.display_name == "Dumble ODS John Mayer"
    assert m.score > 0


# --- find: case + accent insensitivity ----------------------------------------

def test_find_is_case_insensitive(catalog):
    lower = [m.model_id for m in catalog.find("marshall")]
    upper = [m.model_id for m in catalog.find("MARSHALL")]
    assert "ir_marshall_4x12_v30" in lower
    assert lower == upper


def test_find_is_accent_insensitive(catalog):
    # an accented query still resolves the un-accented catalog entry
    plain = [m.model_id for m in catalog.find("ibanez")]
    accented = [m.model_id for m in catalog.find("ibáñez")]
    assert "nam_ibanez_ts808_a2" in plain
    assert accented == plain


# --- find: type filter --------------------------------------------------------

def test_find_type_filter_excludes_other_types(catalog):
    cab_results = catalog.find("dumble", type="cab")
    assert all(m.type == "cab" for m in cab_results)
    assert "nam_dumble_a2" not in [m.model_id for m in cab_results]


def test_find_no_match_returns_empty(catalog):
    assert catalog.find("nonexistentgearname") == []


# --- find: deterministic ordering ---------------------------------------------

def test_find_is_deterministic(catalog):
    a = [m.model_id for m in catalog.find("dumble", type="amp")]
    b = [m.model_id for m in catalog.find("dumble", type="amp")]
    assert a == b
