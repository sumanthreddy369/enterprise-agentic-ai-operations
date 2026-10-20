"""Local deterministic evidence worker. Run with python -m src.services.incident_worker."""

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from src.domain.contracts import (
    AuthorizationContext,
    Evidence,
    InvestigationReport,
    SourceReference,
    ToolDescriptor,
)
from src.models.database import Incident
from src.services.db import make_engine, session_factory
from src.services.errors import PermissionDenied, ToolUnavailable
from src.services.investigations import SQLInvestigationRepository, authorize
from src.services.settings import Settings
from src.services.tools import ToolRegistry, TypedTool
from src.services.worker import InvestigationWorker, WorkItem


def evidence_registry(repository: SQLInvestigationRepository) -> ToolRegistry:
    async def read(context: AuthorizationContext, reference: SourceReference) -> Evidence:
        authorize(context, "incidents:read")
        if reference.source not in context.allowed_sources:
            raise PermissionDenied()
        async with repository.transaction() as session:
            incident = await session.scalar(
                select(Incident).where(
                    Incident.source == reference.source, Incident.source_id == reference.source_id
                )
            )
            if incident is None:
                raise ToolUnavailable()
            excerpt = json.dumps(
                {
                    "title": incident.title,
                    "status": incident.status,
                    "source_status": incident.source_status,
                },
                sort_keys=True,
            )
            digest = hashlib.sha256(excerpt.encode()).hexdigest()
            return Evidence(
                evidence_id="incident-" + digest[:24],
                reference=reference,
                revision=incident.updated_at.isoformat(),
                locator="incident-record",
                excerpt=excerpt,
                content_sha256=digest,
            )

    registry = ToolRegistry()
    registry.register(
        TypedTool(
            descriptor=ToolDescriptor(
                name="incident.read",
                permission="incidents:read",
                description="Read a source-scoped incident snapshot; no causal inference.",
            ),
            input_model=SourceReference,
            output_model=Evidence,
            handler=read,
        )
    )
    registry.seal()
    return registry


def evidence_handler(
    registry: ToolRegistry,
) -> Callable[[AuthorizationContext, WorkItem], Awaitable[InvestigationReport]]:
    async def handle(context: AuthorizationContext, item: WorkItem) -> InvestigationReport:
        result = await registry.execute(
            "incident.read",
            context,
            {
                "source": item.snapshot.incident.source,
                "source_id": item.snapshot.incident.source_id,
            },
        )
        evidence = Evidence.model_validate(result.model_dump())
        return InvestigationReport(run_id=item.snapshot.run_id, evidence=(evidence,), hypotheses=())

    return handle


async def main() -> None:
    settings = Settings()
    engine = make_engine(settings.database_url)
    repository = SQLInvestigationRepository(session_factory(engine))
    worker = InvestigationWorker(repository)

    def context() -> AuthorizationContext:
        return AuthorizationContext(
            subject="local-evidence-worker",
            tenant_id="local",
            request_id=str(uuid4()),
            permissions=frozenset({"investigations:transition", "incidents:read"}),
            allowed_sources=frozenset({"bpi-2013", "bpi-2014", "api:local-writer"}),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

    try:
        await worker.serve(
            context, evidence_handler(evidence_registry(repository)), asyncio.Event()
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
