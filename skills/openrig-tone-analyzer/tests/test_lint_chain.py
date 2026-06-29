"""Tests for lint_chain.py — the tone POLICY enforced as code.

These tests pin the four checks the linter must enforce so the agent can't skip
the policy in prose:

* zero-time-fx       (warn)  — a chain with no reverb AND no delay is almost
                               always a research miss.
* ungated-high-gain-nam (warn) — a NAM amp/gain chain with no noise gate.
* amp-not-pinned     (block) — a multi-model amp contest when an exact capture
                               for the researched amp already exists.
* forbidden-block    (block) — a limiter_brickwall / volume block (the engine
                               strips them; the chain ends at the EQ).

The catalog comes from the Task-1 fixtures under fixtures/catalog/ — never the
real OpenRig-plugins tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.catalog import load_catalog
from scripts.lint_chain import lint, main

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"
NATIVE = FIXTURES / "native_models.yaml"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(FIXTURES, NATIVE)


def codes(findings):
    return [f["code"] for f in findings]


def by_code(findings, code):
    return [f for f in findings if f["code"] == code]


# --- helpers to build chains --------------------------------------------------

def amp_block(model="nam_dumble_a2", **extra):
    b = {"type": "amp", "model": model}
    b.update(extra)
    return b


def reverb_block():
    return {"type": "reverb", "model": "reverb_hall"}


def delay_block():
    return {"type": "delay", "model": "delay_digital"}


def gate_block():
    return {"type": "dynamics", "model": "gate_basic"}


# --- zero-time-fx -------------------------------------------------------------

def test_no_reverb_and_no_delay_warns(catalog):
    chain = {"blocks": [amp_block(), gate_block()]}
    findings = lint(chain, catalog)
    assert "zero-time-fx" in codes(findings)
    assert by_code(findings, "zero-time-fx")[0]["level"] == "warn"


def test_reverb_and_delay_present_no_warn(catalog):
    chain = {"blocks": [amp_block(), reverb_block(), delay_block()]}
    findings = lint(chain, catalog)
    assert "zero-time-fx" not in codes(findings)


def test_only_delay_present_no_zero_time_warn(catalog):
    chain = {"blocks": [amp_block(), delay_block()]}
    findings = lint(chain, catalog)
    assert "zero-time-fx" not in codes(findings)


# --- ungated-high-gain-nam ----------------------------------------------------

def test_nam_amp_without_gate_warns(catalog):
    chain = {"blocks": [amp_block(model="nam_dumble_a2"), reverb_block(), delay_block()]}
    findings = lint(chain, catalog)
    assert "ungated-high-gain-nam" in codes(findings)
    assert by_code(findings, "ungated-high-gain-nam")[0]["level"] == "warn"


def test_nam_amp_with_gate_no_warn(catalog):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_a2"),
            gate_block(),
            reverb_block(),
            delay_block(),
        ]
    }
    findings = lint(chain, catalog)
    assert "ungated-high-gain-nam" not in codes(findings)


def test_non_nam_amp_no_ungated_warn(catalog):
    chain = {"blocks": [amp_block(model="brit_4x12"), reverb_block(), delay_block()]}
    findings = lint(chain, catalog)
    assert "ungated-high-gain-nam" not in codes(findings)


# --- amp-not-pinned -----------------------------------------------------------

DUMBLE_RESEARCH = {
    "amp": {"name": "Dumble ODS John Mayer", "brand": "dumble", "signature": "john mayer"}
}


def test_multi_model_amp_contest_with_exact_capture_blocks(catalog):
    chain = {
        "blocks": [
            {
                "type": "amp",
                "candidates": [
                    {"model": "nam_dumble_a2"},
                    {"model": "nam_fender_deluxe_reverb_a2"},
                ],
            },
            reverb_block(),
            delay_block(),
            gate_block(),
        ]
    }
    findings = lint(chain, catalog, research=DUMBLE_RESEARCH)
    blk = by_code(findings, "amp-not-pinned")
    assert blk, "expected an amp-not-pinned finding"
    assert blk[0]["level"] == "block"


def test_pinned_single_model_amp_no_block(catalog):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            reverb_block(),
            delay_block(),
            gate_block(),
        ]
    }
    findings = lint(chain, catalog, research=DUMBLE_RESEARCH)
    assert "amp-not-pinned" not in codes(findings)


def test_gain_axis_variants_of_one_model_not_a_contest(catalog):
    # same model id swept across the gain axis is ONE distinct base model.
    chain = {
        "blocks": [
            {
                "type": "amp",
                "candidates": [
                    {"model": "nam_dumble_a2", "params": {"gain": 3}},
                    {"model": "nam_dumble_a2", "params": {"gain": 6}},
                    {"model": "nam_dumble_a2", "params": {"gain": 9}},
                ],
            },
            reverb_block(),
            delay_block(),
            gate_block(),
        ]
    }
    findings = lint(chain, catalog, research=DUMBLE_RESEARCH)
    assert "amp-not-pinned" not in codes(findings)


def test_amp_contest_without_research_no_block(catalog):
    chain = {
        "blocks": [
            {
                "type": "amp",
                "candidates": [
                    {"model": "nam_dumble_a2"},
                    {"model": "nam_fender_deluxe_reverb_a2"},
                ],
            },
            reverb_block(),
            delay_block(),
            gate_block(),
        ]
    }
    findings = lint(chain, catalog, research=None)
    assert "amp-not-pinned" not in codes(findings)


def test_amp_contest_no_exact_capture_no_block(catalog):
    chain = {
        "blocks": [
            {
                "type": "amp",
                "candidates": [
                    {"model": "nam_dumble_a2"},
                    {"model": "nam_fender_deluxe_reverb_a2"},
                ],
            },
            reverb_block(),
            delay_block(),
            gate_block(),
        ]
    }
    research = {"amp": {"name": "Soldano SLO Imaginary Boutique"}}
    findings = lint(chain, catalog, research=research)
    assert "amp-not-pinned" not in codes(findings)


# --- forbidden-block ----------------------------------------------------------

def test_limiter_brickwall_blocks(catalog):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            gate_block(),
            reverb_block(),
            delay_block(),
            {"type": "limiter", "model": "limiter_brickwall"},
        ]
    }
    findings = lint(chain, catalog)
    blk = by_code(findings, "forbidden-block")
    assert blk
    assert blk[0]["level"] == "block"


def test_volume_block_is_forbidden(catalog):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            gate_block(),
            reverb_block(),
            delay_block(),
            {"type": "volume", "model": "volume_post"},
        ]
    }
    findings = lint(chain, catalog)
    assert "forbidden-block" in codes(findings)


# --- clean chain --------------------------------------------------------------

def test_clean_pinned_chain_no_findings(catalog):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            gate_block(),
            delay_block(),
            reverb_block(),
        ]
    }
    findings = lint(chain, catalog, research=DUMBLE_RESEARCH)
    assert findings == []


# --- CLI exit codes -----------------------------------------------------------

def _write_chain(tmp_path, chain):
    import json

    p = tmp_path / "chain.json"
    p.write_text(json.dumps(chain), encoding="utf-8")
    return p


def test_cli_exits_1_on_block(tmp_path, capsys):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            gate_block(),
            reverb_block(),
            delay_block(),
            {"type": "limiter", "model": "limiter_brickwall"},
        ]
    }
    chain_path = _write_chain(tmp_path, chain)
    rc = main(["--chain", str(chain_path), "--plugins-root", str(FIXTURES), "--native", str(NATIVE)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "forbidden-block" in out


def test_cli_exits_0_on_clean(tmp_path, capsys):
    chain = {
        "blocks": [
            amp_block(model="nam_dumble_ods_john_mayer_a2"),
            gate_block(),
            delay_block(),
            reverb_block(),
        ]
    }
    chain_path = _write_chain(tmp_path, chain)
    rc = main(["--chain", str(chain_path), "--plugins-root", str(FIXTURES), "--native", str(NATIVE)])
    assert rc == 0
