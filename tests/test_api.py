import httpx
import pytest
from sqlalchemy import func, select

from apps.api.main import create_app
from src.models.database import AuditEvent, Incident
from src.services.db import make_engine, session_factory
from src.services.settings import Settings

WRITE = {"Authorization": "Bearer test-writer", "Idempotency-Key": "request-1"}
READ = {"Authorization": "Bearer test-reader"}
BODY = {
    "source_id": "synthetic-test-1",
    "title": "Synthetic unit test incident",
    "opened_at": "2026-01-01T10:00:00+02:00",
}


async def test_auth_rbac_and_validation(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/incidents")).status_code == 401
    assert (await client.post("/api/v1/incidents", headers=READ, json=BODY)).status_code == 403
    assert (
        await client.post(
            "/api/v1/incidents", headers=WRITE, json={**BODY, "opened_at": "2026-01-01T10:00:00"}
        )
    ).status_code == 422
    assert (
        await client.post("/api/v1/incidents", headers=WRITE, json={**BODY, "source": "bpi-2013"})
    ).status_code == 422
    assert (await client.get("/api/v1/incidents?limit=999", headers=READ)).status_code == 422


async def test_idempotency_audit_and_read(client: httpx.AsyncClient, migrated_url: str) -> None:
    first = await client.post("/api/v1/incidents", json=BODY, headers=WRITE)
    assert first.status_code == 201, first.text
    second = await client.post("/api/v1/incidents", json=BODY, headers=WRITE)
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    conflict = await client.post(
        "/api/v1/incidents", json={**BODY, "title": "Different"}, headers=WRITE
    )
    assert conflict.status_code == 409
    assert (
        await client.post(
            "/api/v1/incidents", json=BODY, headers={**WRITE, "Idempotency-Key": "another"}
        )
    ).status_code == 409
    listing = await client.get("/api/v1/incidents", headers=READ)
    assert len(listing.json()) == 1
    detail = await client.get(f"/api/v1/incidents/{first.json()['id']}", headers=READ)
    assert detail.status_code == 200
    assert detail.json()["opened_at"] == "2026-01-01T08:00:00Z"
    assert (await client.get("/api/v1/incidents/nonexistent", headers=READ)).status_code == 404
    engine = make_engine(migrated_url)
    async with session_factory(engine)() as database:
        assert await database.scalar(select(func.count()).select_from(Incident)) == 1
        assert await database.scalar(select(func.count()).select_from(AuditEvent)) == 1
    await engine.dispose()


async def test_health_readiness_openapi(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "verified-id"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "verified-id"
    assert (await client.get("/ready")).status_code == 200
    assert "/api/v1/incidents" in (await client.get("/openapi.json")).json()["paths"]
    assert (await client.post("/api/v1/investigations", headers=WRITE, json={})).status_code == 404


async def test_unmigrated_database_not_ready(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            allowed_hosts=["test"],
            database_url=f"sqlite+aiosqlite:///{tmp_path}/empty.db",
            opensearch_required=False,
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/ready")).status_code == 503


@pytest.mark.parametrize("token", ["", "wrong", "Bearer"])
async def test_invalid_credentials(client: httpx.AsyncClient, token: str) -> None:
    assert (
        await client.get("/api/v1/incidents", headers={"Authorization": token})
    ).status_code == 401
