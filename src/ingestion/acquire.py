import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from filelock import FileLock
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.security.egress import validate_data_url


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog(path: Path = Path("data/dataset_manifest.json")) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


@retry(
    retry=retry_if_exception_type((httpx.TransportError,)),
    wait=wait_exponential(min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
def download(url: str, destination: Path, expected_sha256: str, max_bytes: int) -> None:
    """Bounded HTTPS download; no partial file is promoted as a successful acquisition."""
    validate_data_url(url)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        with httpx.Client(
            follow_redirects=False, timeout=30, headers={"Accept-Encoding": "identity"}
        ) as client:
            current_url = url
            for redirect in range(6):
                validate_data_url(current_url)
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        if redirect == 5 or "location" not in response.headers:
                            raise ValueError("invalid or excessive dataset redirects")
                        current_url = urljoin(current_url, response.headers["location"])
                        continue
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ValueError("compressed HTTP transfer is not accepted")
                    size = 0
                    deadline = time.monotonic() + 120
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_raw():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("download exceeds declared size limit")
                            if time.monotonic() > deadline:
                                raise ValueError("dataset download time budget exceeded")
                            handle.write(chunk)
                    break
        if sha256_file(temporary) != expected_sha256:
            raise ValueError("dataset checksum mismatch; source was not promoted")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def acquire(dataset: str, root: Path, manifest: dict[str, Any]) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", dataset):
        raise ValueError("invalid dataset key")
    entry = manifest["datasets"][dataset]
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", str(entry["filename"])):
        raise ValueError("dataset filename must be a safe basename")
    directory = root / "raw" / dataset
    directory.mkdir(parents=True, exist_ok=True)
    destination: Path = directory / str(entry["filename"])
    with FileLock(str(directory / ".download.lock")):
        if destination.exists():
            if sha256_file(destination) != entry["sha256"]:
                raise ValueError("existing raw file differs from manifest; refusing overwrite")
        else:
            download(entry["download_url"], destination, entry["sha256"], entry["size_bytes"])
        (directory / "provenance.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
        if dataset.startswith("loghub-"):
            notice = Path("docs/LOGHUB-LICENSE.txt").read_text(encoding="utf-8")
            (directory / "LICENSE.txt").write_text(notice, encoding="utf-8")
    return destination
