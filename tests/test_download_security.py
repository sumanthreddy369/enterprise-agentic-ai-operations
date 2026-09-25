import hashlib
from pathlib import Path

import httpx
import pytest

from src.ingestion.acquire import download


def test_redirect_rechecked_and_partial_file_removed(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://169.254.169.254/metadata"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("src.ingestion.acquire.httpx.Client", lambda **_: client)
    destination = tmp_path / "file.log"
    with pytest.raises(ValueError, match="allowlisted"):
        download("https://raw.githubusercontent.com/example/file", destination, "a" * 64, 100)
    assert len(calls) == 1
    assert not destination.exists()
    assert not destination.with_suffix(".log.partial").exists()


@pytest.mark.parametrize(
    "limit,digest,reason",
    [
        (1, hashlib.sha256(b"synthetic").hexdigest(), "size limit"),
        (100, "a" * 64, "checksum"),
    ],
)
def test_download_budget_and_checksum(
    tmp_path: Path, monkeypatch, limit: int, digest: str, reason: str
) -> None:
    # A streaming response mirrors real HTTP; .iter_raw() must not receive pre-consumed content.
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"synthetic"

    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Stream()))
    )
    monkeypatch.setattr("src.ingestion.acquire.httpx.Client", lambda **_: client)
    destination = tmp_path / "file.log"
    with pytest.raises(ValueError, match=reason):
        download("https://raw.githubusercontent.com/example/file", destination, digest, limit)
    assert not destination.exists()
    assert not destination.with_suffix(".log.partial").exists()
