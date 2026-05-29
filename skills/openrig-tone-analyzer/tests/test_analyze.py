"""Integration tests for analyze.py."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scripts import analyze


def _run(input_path: Path, tmp_path: Path) -> dict:
    out_dir = tmp_path / "out"
    rc = analyze.main([str(input_path), "--out-dir", str(out_dir)])
    assert rc == 0
    fp_path = out_dir / "fingerprint.json"
    assert fp_path.exists()
    return json.loads(fp_path.read_text())


def test_clean_di_basic(clean_di_path: Path, tmp_path: Path) -> None:
    fp = _run(clean_di_path, tmp_path)

    assert fp["schema_version"] == 2
    assert fp["source"]["channels"] == 1
    assert fp["source"]["sample_rate_hz"] == 22050
    assert 3.5 < fp["source"]["duration_s"] < 4.5
    assert isinstance(fp["source"]["sha256"], str) and len(fp["source"]["sha256"]) == 64

    assert isinstance(fp["global"]["peak_db"], float)
    assert "lufs_integrated" in fp["global"]
    assert fp["global"]["stereo"]["is_stereo"] is False

    # clean DI is 4 s — segmentation should return exactly 1 section
    assert len(fp["sections"]) == 1
    sec = fp["sections"][0]
    assert sec["id"] == "section_0"
    assert sec["labels"]["tone_profile"] == "clean"
    assert isinstance(sec["spectrum"]["band_energy_db"], list)
    assert len(sec["spectrum"]["band_energy_db"]) == 8


def test_distorted_di_classifies_high_gain(distorted_di_path: Path, tmp_path: Path) -> None:
    fp = _run(distorted_di_path, tmp_path)
    assert len(fp["sections"]) == 1
    sec = fp["sections"][0]
    # heavy softclip(gain=8) on a single sine should be at least "distortion"
    assert sec["labels"]["tone_profile"] in ("distortion", "high_gain")
    assert sec["distortion"]["thd_estimate_pct"] > 10.0


def test_multi_section_finds_three(multi_section_path: Path, tmp_path: Path) -> None:
    fp = _run(multi_section_path, tmp_path)
    n = len(fp["sections"])
    # 8+12+8 s of distinct timbres — accept 2-4 sections (segmentation has natural drift)
    assert 2 <= n <= 4, f"expected ~3 sections, got {n}"

    tone_profiles = [s["labels"]["tone_profile"] for s in fp["sections"]]
    # At least one section should be high-gain (the middle softclip stretch)
    assert any(t in ("distortion", "high_gain") for t in tone_profiles), \
        f"expected at least one heavy section among {tone_profiles}"


def test_determinism_same_inputs(clean_di_path: Path, tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    analyze.main([str(clean_di_path), "--out-dir", str(out_a)])
    analyze.main([str(clean_di_path), "--out-dir", str(out_b)])
    payload_a = (out_a / "fingerprint.json").read_bytes()
    payload_b = (out_b / "fingerprint.json").read_bytes()
    assert hashlib.sha256(payload_a).hexdigest() == hashlib.sha256(payload_b).hexdigest()


def test_png_dimensions(clean_di_path: Path, tmp_path: Path) -> None:
    from PIL import Image

    out_dir = tmp_path / "out"
    analyze.main([str(clean_di_path), "--out-dir", str(out_dir)])
    pngs = list(out_dir.glob("*.png"))
    assert len(pngs) >= 2  # at least global + 1 section
    for png in pngs:
        with Image.open(png) as img:
            assert img.size[0] >= 1024
            assert img.size[1] >= 512


def test_global_png_has_section_boundaries(multi_section_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    analyze.main([str(multi_section_path), "--out-dir", str(out_dir)])
    # We can't programmatically read matplotlib cyan dashed lines easily, but
    # we can assert the PNG exists and has the expected dimensions; visual
    # inspection during smoke is the human gate.
    global_png = out_dir / "spec_global.png"
    assert global_png.exists()
    # one per-section PNG per section
    fp = json.loads((out_dir / "fingerprint.json").read_text())
    for sec in fp["sections"]:
        assert (out_dir / f"spec_{sec['id']}.png").exists()


def test_long_file_rejected(tmp_path: Path) -> None:
    long_path = tmp_path / "too_long.wav"
    silence = np.zeros(601 * 22050, dtype=np.float32)
    sf.write(str(long_path), silence, 22050, subtype="PCM_16")
    with pytest.raises(SystemExit) as exc:
        analyze.main([str(long_path), "--out-dir", str(tmp_path / "out")])
    assert "too long" in str(exc.value)


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

def test_analyze_emits_pdf_report_at_default_filename(clean_di_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    analyze.main([str(clean_di_path), "--out-dir", str(out_dir)])
    pdf_path = out_dir / analyze.PDF_FILENAME
    assert pdf_path.exists(), f"expected {analyze.PDF_FILENAME} in {out_dir}, got {list(out_dir.iterdir())}"


def test_pdf_starts_with_pdf_magic_bytes(clean_di_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    analyze.main([str(clean_di_path), "--out-dir", str(out_dir)])
    head = (out_dir / analyze.PDF_FILENAME).read_bytes()[:5]
    assert head == b"%PDF-", f"expected PDF magic header, got {head!r}"


def test_pdf_above_minimum_content_size(clean_di_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    analyze.main([str(clean_di_path), "--out-dir", str(out_dir)])
    size = (out_dir / analyze.PDF_FILENAME).stat().st_size
    # cover page + global spectrogram + at least 1 section page = always > 20KB
    # for a real analysis. Empty / malformed PDFs are well under this.
    assert size > 20_000, f"PDF suspiciously small ({size} bytes) — likely missing pages"


def test_pdf_multi_section_pages_count_scales_with_sections(
    multi_section_path: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    analyze.main([str(multi_section_path), "--out-dir", str(out_dir)])
    fp = json.loads((out_dir / "fingerprint.json").read_text())
    pdf = (out_dir / analyze.PDF_FILENAME).read_bytes()
    # Count `/Type /Page ` (trailing space — leaf page) excluding `/Type /Pages` (parent).
    import re
    page_markers = len(re.findall(rb"/Type\s+/Page\b(?!s)", pdf))
    expected_min = 1 + 1 + len(fp["sections"])  # cover + global + per-section
    assert page_markers >= expected_min, (
        f"expected at least {expected_min} pages (cover + global + {len(fp['sections'])} sections), "
        f"got {page_markers} /Type /Page markers"
    )
