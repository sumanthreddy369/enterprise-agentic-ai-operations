import asyncio
import gzip
from pathlib import Path

import httpx
import pytest
from defusedxml.common import EntitiesForbidden

from apps.api.main import create_app
from src.pipelines.parsers import xes_records
from src.services.settings import Settings


async def test_concurrency_limit_and_release(migrated_url: str) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_url=migrated_url,
            allowed_hosts=["test"],
            max_concurrent_requests=1,
        )
    )
    entered, release = asyncio.Event(), asyncio.Event()

    @app.get("/hold-test")
    async def hold() -> dict[str, bool]:
        entered.set()
        await release.wait()
        return {"ok": True}

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        pending = asyncio.create_task(client.get("/hold-test"))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            assert (await client.get("/health")).status_code == 503
        finally:
            release.set()
        assert (await pending).status_code == 200
        assert (await client.get("/health")).status_code == 200


async def test_slow_body_timeout(migrated_url: str) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_url=migrated_url,
            allowed_hosts=["test"],
            body_timeout_seconds=0.01,
        )
    )

    async def slow_body():
        await asyncio.sleep(0.1)
        yield b"{}"

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        result = await client.post(
            "/api/v1/incidents", content=slow_body(), headers={"Content-Type": "application/json"}
        )
        assert result.status_code == 408


def test_xml_entity_expansion_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "malicious-synthetic.xes.gz"
    path.write_bytes(
        gzip.compress(
            b'<!DOCTYPE log [<!ENTITY secret SYSTEM "file:///nonexistent-secret">]>'
            b'<log xmlns="http://www.xes-standard.org/">&secret;</log>'
        )
    )
    with pytest.raises(EntitiesForbidden):
        list(xes_records(path, "synthetic", "0" * 64, None))
