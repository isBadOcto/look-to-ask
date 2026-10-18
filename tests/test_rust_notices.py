"""A corrupted cached source must stop licensing preparation without network access."""

import pytest

from scripts.fetch_rust_notices import fetch


def test_crate_checksum_mismatch_stops_before_parsing_or_network(tmp_path, monkeypatch):
    package = {"name": "fixture", "version": "1.0.0", "checksum": "0" * 64}
    (tmp_path / "fixture-1.0.0.crate").write_bytes(b"CORRUPTED TEST SOURCE")

    def forbidden(*args, **kwargs):
        raise AssertionError("A cached checksum failure must not download silently")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(RuntimeError, match="Cached crate checksum mismatch"):
        fetch(package, tmp_path)
