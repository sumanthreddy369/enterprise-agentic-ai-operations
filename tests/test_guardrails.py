import asyncio
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from apps.api.main import create_app
from src.security.egress import validate_data_url
from src.services.settings import Settings


async def test_rate_limit_and_headers(migrated_url: str) -> None:
    settings = Settings(
        _env_file=None, database_url=migrated_url, allowed_hosts=["test"], requests_per_minute=2
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        for _ in range(2):
            assert (await client.get("/api/v1/incidents")).status_code == 401
        response = await client.get("/api/v1/incidents", headers={"X-Forwarded-For": "8.8.8.8"})
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/health")).status_code == 200


async def test_request_limits_host_and_error_redaction(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health", headers={"Host": "evil.example"})).status_code == 400
    assert (await client.post("/api/v1/incidents", content="x" * 70000)).status_code == 413
    assert (
        await client.post("/api/v1/incidents", content="{}", headers={"Content-Type": "text/plain"})
    ).status_code == 415
    assert (
        await client.post("/api/v1/incidents", content="{}", headers={"Content-Encoding": "gzip"})
    ).status_code == 415
    secret = "sensitive-do-not-echo"
    response = await client.post(
        "/api/v1/incidents",
        headers={"Authorization": "Bearer test-writer", "Idempotency-Key": "redaction-test"},
        json={"source_id": "test", "title": "test", "opened_at": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text


async def test_chunked_body_limit(client: httpx.AsyncClient) -> None:
    async def chunks():
        yield b"x" * 40000
        yield b"x" * 40000

    response = await client.post(
        "/api/v1/incidents", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


async def test_handler_timeout(migrated_url: str) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_url=migrated_url,
            allowed_hosts=["test"],
            handler_timeout_seconds=0.02,
        )
    )

    @app.get("/slow-test")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(0.1)
        return {"status": "unexpected"}

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/slow-test")).status_code == 504


@pytest.mark.parametrize(
    "url",
    [
        "http://raw.githubusercontent.com/a",
        "https://127.0.0.1/a",
        "https://169.254.169.254/latest/meta-data/",
        "https://raw.githubusercontent.com.evil.com/a",
        "https://user:password@raw.githubusercontent.com/a",
        "https://raw.githubusercontent.com:8443/a",
        "https://s3.amazonaws.com/untrusted-bucket/a",
    ],
)
def test_dataset_egress_denied(url: str) -> None:
    with pytest.raises(ValueError):
        validate_data_url(url)


def test_dataset_egress_allowed() -> None:
    validate_data_url("https://raw.githubusercontent.com/logpai/loghub/pinned/file")


def test_production_promotion_is_blocked() -> None:
    with pytest.raises(ValidationError, match="enterprise identity"):
        Settings(_env_file=None, environment="production")


def test_manifest_path_traversal_rejected(tmp_path: Path) -> None:
    from src.ingestion.acquire import acquire

    with pytest.raises(ValueError, match="filename"):
        acquire("test", tmp_path, {"datasets": {"test": {"filename": "../outside"}}})
