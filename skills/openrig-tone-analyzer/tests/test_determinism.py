"""Pinned-hash tests: fingerprint.json must be byte-identical across runs.

If a code change perturbs any pinned hash, update it here in the same commit
with a one-line justification in the commit body. The hash assertion is what
catches accidental numerical drift; the dictionary structure of the JSON is
covered by test_analyze.py.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from scripts import analyze

PINNED_HASHES = {
    "clean_di.wav":      "c7baa833fe136b4fdd68b8195a22faebf5e1d7f8fe400b959a7a07d1f70d8da0",
    "distorted_di.wav":  "888f47cbec6e5c30124e2c6d9d390081090bcfcfd25e2fa948ed6e4a607c8ece",
    "reverb_tail.wav":   "62229eac0cf060d4dca161af103dd402ea840572ba7403ac6af06ec70f655d2c",
    "delayed_echo.wav":  "5f64199e4bf6b8d9cb8609af7ded405a5512d67d5ab58b665e7f28715c7e13da",
    "multi_section.wav": "e11d99c27d28fdef8f7ea105ef26a8f0d23c577420c56f18e12107aceecc9449",
}


@pytest.fixture(autouse=True)
def clear_analyzer_cache() -> None:
    """The /tmp cache used by compare.py mustn't influence analyze's output —
    but if a prior compare run left stale entries, clearing them eliminates
    any chance of confusion."""
    cache = Path("/tmp/openrig-analyzer-cache")
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)


@pytest.mark.parametrize("fixture_name,expected_hash", list(PINNED_HASHES.items()))
def test_fingerprint_hash_pinned(fixture_name: str, expected_hash: str, fixtures_dir: Path, tmp_path: Path) -> None:
    fixture_path = fixtures_dir / fixture_name
    out_dir = tmp_path / "out"
    rc = analyze.main([str(fixture_path), "--out-dir", str(out_dir)])
    assert rc == 0
    fp_path = out_dir / "fingerprint.json"
    payload = fp_path.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    assert actual == expected_hash, (
        f"Determinism drift on {fixture_name}: expected {expected_hash}, got {actual}. "
        "If this drift is intentional, update PINNED_HASHES with a one-line "
        "justification in the commit body."
    )
