import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from src.domain.contracts import InvestigationRequest, SourceReference
from src.models.database import Incident, InvestigationRun
from src.services.db import make_engine, session_factory
from src.services.incident_worker import evidence_handler, evidence_registry
from src.services.investigations import InvestigationConflict, SQLInvestigationRepository
from src.services.worker import InvestigationWorker
from tests.test_investigations import auth


async def test_worker_reclaim_cancel_and_complete(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    repository = SQLInvestigationRepository(session_factory(engine))
    context = auth().model_copy(update={"permissions": auth().permissions | {"incidents:read"}})
    try:
        async with repository.transaction() as session:
            session.add(
                Incident(
                    source="synthetic-test",
                    source_id="worker",
                    title="Synthetic incident",
                    attributes={"synthetic": True},
                )
            )
        request = InvestigationRequest(
            incident=SourceReference(source="synthetic-test", source_id="worker"),
            question="Read evidence",
            idempotency_key="worker",
        )
        initial = await repository.create(context, request)
        worker = InvestigationWorker(repository)
        claims = await asyncio.gather(worker.claim(context), worker.claim(context))
        assert sum(item is not None for item in claims) == 1
        old = next(item for item in claims if item is not None)
        assert old is not None
        assert await worker.claim(context) is None
        async with repository.transaction() as session:
            await session.execute(
                update(InvestigationRun)
                .where(InvestigationRun.id == initial.run_id)
                .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
            )
        await engine.dispose()  # Recreate connections and worker after a simulated stop.
        worker = InvestigationWorker(repository)
        new = await worker.claim(context)
        assert new is not None and new.token != old.token
        handler = evidence_handler(evidence_registry(repository))
        with pytest.raises(InvestigationConflict):
            await worker.finish(context, old, await handler(context, old))
        await worker.finish(context, new, await handler(context, new))
        report = await repository.get_report(context, initial.run_id)
        assert report is not None and len(report.evidence) == 1 and not report.hypotheses
        assert await worker.claim(context) is None
        another = await repository.create(
            context, request.model_copy(update={"idempotency_key": "cancel"})
        )
        active = await worker.claim(context)
        assert active is not None
        await repository.transition(
            context,
            active.snapshot.model_copy(update={"status": "cancelled"}),
            expected_revision=active.snapshot.revision,
        )
        with pytest.raises(InvestigationConflict):
            await worker.finish(context, active, await handler(context, active))
        assert await repository.get_report(context, another.run_id) is None
    finally:
        await engine.dispose()


async def test_worker_failure_exhaustion(migrated_url: str) -> None:
    engine = make_engine(migrated_url)
    repository = SQLInvestigationRepository(session_factory(engine))
    context = auth()
    try:
        async with repository.transaction() as session:
            session.add(
                Incident(
                    source="synthetic-test",
                    source_id="retry",
                    title="Synthetic",
                    attributes={"synthetic": True},
                )
            )
        run = await repository.create(
            context,
            InvestigationRequest(
                incident=SourceReference(source="synthetic-test", source_id="retry"),
                question="Synthetic",
                idempotency_key="retry",
            ),
        )
        worker = InvestigationWorker(repository, max_attempts=1)

        async def broken(*args: object):
            raise RuntimeError("sensitive backend exception")

        assert await worker.run_once(context, broken)
        assert await worker.claim(context) is None
        current = await repository.get(context, run.run_id)
        assert current is not None and current.status == "failed"
    finally:
        await engine.dispose()
