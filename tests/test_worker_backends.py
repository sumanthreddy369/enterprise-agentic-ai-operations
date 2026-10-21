"""Worker fencing and competing claims against the real deployment database."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from src.domain.contracts import InvestigationRequest, SourceReference
from src.models.database import AuditEvent, Incident, InvestigationRun
from src.services.db import make_engine, session_factory
from src.services.incident_worker import evidence_handler, evidence_registry
from src.services.investigations import InvestigationConflict, SQLInvestigationRepository
from src.services.worker import InvestigationWorker
from tests.test_investigations import auth


@pytest.mark.integration
async def test_postgres_worker_claim_and_fence() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    source = "synthetic-worker-" + uuid4().hex
    context = auth().model_copy(
        update={
            "allowed_sources": frozenset({source}),
            "permissions": auth().permissions | {"incidents:read"},
        }
    )
    engines = [make_engine(url), make_engine(url)]
    repositories = [SQLInvestigationRepository(session_factory(engine)) for engine in engines]
    workers = [InvestigationWorker(repository) for repository in repositories]
    try:
        async with repositories[0].transaction() as session:
            session.add(
                Incident(
                    source=source,
                    source_id="one",
                    title="Synthetic worker integration fixture",
                    attributes={"synthetic": True},
                )
            )
        initial = await repositories[0].create(
            context,
            InvestigationRequest(
                incident=SourceReference(source=source, source_id="one"),
                question="Read synthetic evidence",
                idempotency_key=source,
            ),
        )
        claims = await asyncio.gather(*(worker.claim(context) for worker in workers))
        assert sum(claim is not None for claim in claims) == 1
        old = next(claim for claim in claims if claim is not None)
        assert await workers[1].claim(context) is None
        async with repositories[0].transaction() as session:
            await session.execute(
                update(InvestigationRun)
                .where(InvestigationRun.id == initial.run_id)
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
        await engines[0].dispose()
        current = await workers[1].claim(context)
        assert current is not None and current.token != old.token
        report = await evidence_handler(evidence_registry(repositories[1]))(context, current)
        with pytest.raises(InvestigationConflict):
            await workers[0].finish(context, old, report)
        await workers[1].finish(context, current, report)
        assert await repositories[0].get_report(context, initial.run_id) == report
        assert await workers[0].claim(context) is None
    finally:
        async with repositories[0].transaction() as session:
            incident_ids = select(Incident.id).where(Incident.source == source)
            run_ids = select(InvestigationRun.id).where(
                InvestigationRun.incident_id.in_(incident_ids)
            )
            await session.execute(delete(AuditEvent).where(AuditEvent.resource_id.in_(run_ids)))
            await session.execute(delete(InvestigationRun).where(InvestigationRun.id.in_(run_ids)))
            await session.execute(delete(Incident).where(Incident.source == source))
        for engine in engines:
            await engine.dispose()
