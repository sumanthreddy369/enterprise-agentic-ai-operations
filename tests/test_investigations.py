import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select

from src.domain.contracts import AuthorizationContext, InvestigationRequest, SourceReference
from src.models.database import AuditEvent, Incident, InvestigationRun
from src.services.db import make_engine, session_factory
from src.services.errors import PermissionDenied
from src.services.investigations import InvestigationConflict, SQLInvestigationRepository


def auth() -> AuthorizationContext:
    return AuthorizationContext(
        subject="synthetic-test",
        tenant_id="local",
        request_id="test",
        permissions=frozenset(
            {"investigations:read", "investigations:write", "investigations:transition"}
        ),
        allowed_sources=frozenset({"synthetic-test"}),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


async def exercise_lifecycle(url: str) -> None:
    engine = make_engine(url)
    sessions = session_factory(engine)
    context = auth()
    source_id = str(uuid4())
    request = InvestigationRequest(
        incident=SourceReference(source="synthetic-test", source_id=source_id),
        question="Investigate synthetic fixture",
        idempotency_key=source_id,
    )
    try:
        async with sessions() as session, session.begin():
            session.add(
                Incident(
                    source="synthetic-test",
                    source_id=source_id,
                    title="Synthetic incident",
                    attributes={"synthetic": True},
                )
            )
        repository = SQLInvestigationRepository(sessions)
        results = await asyncio.gather(*(repository.create(context, request) for _ in range(4)))
        initial = results[0]
        assert all(result == initial for result in results)
        for status in ("completed", "awaiting_approval", "failed"):
            with pytest.raises(InvestigationConflict):
                await repository.transition(
                    context, initial.model_copy(update={"status": status}), expected_revision=0
                )
        with pytest.raises(InvestigationConflict):
            await repository.transition(
                context,
                initial.model_copy(update={"status": "running", "tenant_id": "forged"}),
                expected_revision=0,
            )
        with pytest.raises(PermissionDenied):
            await repository.transition(
                context.model_copy(update={"permissions": frozenset({"investigations:write"})}),
                initial.model_copy(update={"status": "running"}),
                expected_revision=0,
            )
        with pytest.raises(InvestigationConflict):
            await repository.create(context, request.model_copy(update={"question": "Changed"}))
        # Dispose the entire pool and construct a new repository to demonstrate durable state.
        await engine.dispose()
        repository = SQLInvestigationRepository(session_factory(engine))
        assert await repository.get(context, initial.run_id) == initial
        races = await asyncio.gather(
            *(
                repository.transition(
                    context, initial.model_copy(update={"status": status}), expected_revision=0
                )
                for status in ("running", "cancelled")
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, InvestigationConflict) for result in races) == 1
        current = await repository.get(context, initial.run_id)
        assert current is not None and current.revision == 1
        if current.status == "running":
            current = await repository.transition(
                context, current.model_copy(update={"status": "cancelled"}), expected_revision=1
            )
        assert current.status == "cancelled"
        with pytest.raises(InvestigationConflict):
            await repository.transition(
                context,
                current.model_copy(update={"status": "running"}),
                expected_revision=current.revision,
            )
        with pytest.raises(PermissionDenied):
            await repository.get(context.model_copy(update={"tenant_id": "other"}), initial.run_id)
        with pytest.raises(PermissionDenied):
            await repository.create(
                context.model_copy(update={"expires_at": datetime.now(UTC)}), request
            )
        assert (
            await repository.get(
                context.model_copy(update={"allowed_sources": frozenset()}), initial.run_id
            )
            is None
        )
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(AuditEvent.resource_id == initial.run_id)
                )
                == current.revision + 1
            )
    finally:
        async with sessions() as session, session.begin():
            incident_ids = select(Incident.id).where(
                Incident.source == "synthetic-test", Incident.source_id == source_id
            )
            run_ids = select(InvestigationRun.id).where(
                InvestigationRun.incident_id.in_(incident_ids)
            )
            await session.execute(delete(AuditEvent).where(AuditEvent.resource_id.in_(run_ids)))
            await session.execute(
                delete(InvestigationRun).where(InvestigationRun.incident_id.in_(incident_ids))
            )
            await session.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
        await engine.dispose()


async def test_durable_lifecycle(migrated_url: str) -> None:
    await exercise_lifecycle(migrated_url)


@pytest.mark.integration
async def test_postgres_investigations() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    await exercise_lifecycle(url)


async def test_cancellation_rolls_back(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    repository = SQLInvestigationRepository(session_factory(engine))
    entered = asyncio.Event()

    async def interrupted() -> None:
        async with repository.transaction() as session:
            session.add(
                Incident(
                    source="synthetic-test",
                    source_id="cancelled",
                    title="Synthetic",
                    attributes={"synthetic": True},
                )
            )
            await session.flush()
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(interrupted())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with repository.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Incident)) == 0
    finally:
        task.cancel()
        await engine.dispose()


async def test_investigation_api(client: httpx.AsyncClient) -> None:
    writer = {"Authorization": "Bearer test-writer", "Idempotency-Key": "synthetic"}
    reader = {"Authorization": "Bearer test-reader"}
    incident = await client.post(
        "/api/v1/incidents",
        headers=writer,
        json={"source_id": "synthetic", "title": "Synthetic", "opened_at": "2026-01-01T00:00:00Z"},
    )
    assert incident.status_code == 201
    body = {
        "incident": {"source": "api:local-writer", "source_id": "synthetic"},
        "question": "Investigate synthetic incident",
    }
    path = "/api/v1/investigations"
    assert (await client.post(path, json=body)).status_code == 401
    assert (await client.post(path, headers=reader, json=body)).status_code == 403
    assert (
        await client.post(path, headers={**writer, "Idempotency-Key": " "}, json=body)
    ).status_code == 422
    assert (
        await client.post(path, headers=writer, json={**body, "tenant_id": "other"})
    ).status_code == 422
    response = await client.post(path, headers={**writer, "X-Tenant-ID": "other"}, json=body)
    assert response.status_code == 202
    run = response.json()
    assert run["status"] == "pending" and run["tenant_id"] == "local"
    assert (await client.post(path, headers=writer, json=body)).json() == run
    assert (
        await client.post(path, headers=writer, json={**body, "question": "Changed"})
    ).status_code == 409
    item = f"{path}/{run['run_id']}"
    assert (await client.get(item, headers=reader)).json() == run
    assert (
        await client.post(f"{item}/cancel", headers=reader, json={"expected_revision": 0})
    ).status_code == 403
    cancelled = await client.post(f"{item}/cancel", headers=writer, json={"expected_revision": 0})
    assert cancelled.json()["status"] == "cancelled"
    assert (
        await client.post(f"{item}/cancel", headers=writer, json={"expected_revision": 0})
    ).status_code == 409
    assert (await client.get(f"{path}/unknown", headers=reader)).status_code == 404


async def test_backend_failure_is_redacted(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import OperationalError

    async def broken(*args: object, **kwargs: object) -> None:
        raise OperationalError("secret SQL", {}, Exception("secret password"))

    monkeypatch.setattr(SQLInvestigationRepository, "snapshot", broken)
    response = await client.get(
        "/api/v1/investigations/test", headers={"Authorization": "Bearer test-reader"}
    )
    assert response.status_code == 503
    assert "secret" not in response.text
