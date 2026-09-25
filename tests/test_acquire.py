import hashlib
from pathlib import Path

import pytest

from src.ingestion.acquire import acquire, download


def test_cached_download_integrity(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "test"
    raw.mkdir(parents=True)
    path = raw / "synthetic.txt"
    path.write_bytes(b"synthetic")
    manifest = {
        "datasets": {
            "test": {"filename": path.name, "sha256": hashlib.sha256(b"synthetic").hexdigest()}
        }
    }
    assert acquire("test", tmp_path, manifest) == path
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="refusing overwrite"):
        acquire("test", tmp_path, manifest)


def test_insecure_download_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        download("http://example.org/data", tmp_path / "file", "a" * 64, 100)
