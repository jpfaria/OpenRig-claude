"""Shared pytest fixtures and path setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def clean_di_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "clean_di.wav"


@pytest.fixture(scope="session")
def distorted_di_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "distorted_di.wav"


@pytest.fixture(scope="session")
def reverb_tail_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "reverb_tail.wav"


@pytest.fixture(scope="session")
def delayed_echo_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "delayed_echo.wav"


@pytest.fixture(scope="session")
def clean_with_silence_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "clean_with_silence.wav"


@pytest.fixture(scope="session")
def multi_section_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "multi_section.wav"
