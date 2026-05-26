"""Verify analyze and compare don't attempt any network IO.

Monkey-patches socket.socket so any TCP/UDP connect attempt raises. Both
pipelines must complete cleanly with the patch in place. If a library tries
to phone home (download a model, fetch a config), this surfaces it.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from scripts import analyze, compare


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original = socket.socket.connect

    def blocked(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Allow loopback / unix sockets if any matplotlib/Agg internals need them.
        if args and isinstance(args[0], tuple):
            host, *_ = args[0]
            if host in ("127.0.0.1", "::1", "localhost"):
                return original(self, *args, **kwargs)
        raise RuntimeError("network access blocked by test fixture")

    monkeypatch.setattr(socket.socket, "connect", blocked)


def test_analyze_no_network(no_network, clean_di_path: Path, tmp_path: Path) -> None:
    rc = analyze.main([str(clean_di_path), "--out-dir", str(tmp_path / "out")])
    assert rc == 0


def test_compare_no_network(no_network, clean_di_path: Path, distorted_di_path: Path, tmp_path: Path) -> None:
    rc = compare.main([
        str(clean_di_path), str(distorted_di_path),
        "--out-dir", str(tmp_path / "out"),
    ])
    assert rc == 0
