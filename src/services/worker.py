"""Bounded SQL polling worker with expiring leases and fenced result commits."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update

from src.domain.contracts import AuthorizationContext, InvestigationReport, InvestigationSnapshot
from src.models.database import Incident, InvestigationRun
from src.services.investigations import (
    InvestigationConflict,
    InvestigationUnavailable,
    SQLInvestigationRepository,
    authorize,
)


@dataclass(frozen=True)
class WorkItem:
    snapshot: InvestigationSnapshot
    question: str
    token: str


class InvestigationWorker:
    """Trusted local worker; handlers must use authorized read-only tool boundaries."""

    def __init__(
        self,
        repository: SQLInvestigationRepository,
        *,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> None:
        if not 5 <= lease_seconds <= 300 or not 1 <= max_attempts <= 10:
            raise ValueError("Invalid worker bounds")
        self.repository = repository
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    async def claim(self, context: AuthorizationContext) -> WorkItem | None:
        authorize(context, "investigations:transition")
        now = datetime.now(UTC)
        async with self.repository.transaction() as session:
            eligible = or_(
                InvestigationRun.status == "pending",
                and_(
                    InvestigationRun.status == "running",
                    InvestigationRun.lease_until <= now,
                ),
            )
            candidate = await session.scalar(
                select(InvestigationRun)
                .join(Incident, InvestigationRun.incident_id == Incident.id)
                .where(
                    eligible,
                    InvestigationRun.tenant_id == context.tenant_id,
                    InvestigationRun.submission_key.is_not(None),
                    Incident.source.in_(context.allowed_sources),
                )
                .order_by(InvestigationRun.created_at, InvestigationRun.id)
                .limit(1)
            )
            if candidate is None:
                return None
            exhausted = candidate.attempts >= self.max_attempts
            token = str(uuid4())
            changed = await session.scalar(
                update(InvestigationRun)
                .where(
                    InvestigationRun.id == candidate.id,
                    InvestigationRun.revision == candidate.revision,
                    eligible,
                )
                .values(
                    status="failed" if exhausted else "running",
                    revision=InvestigationRun.revision + 1,
                    attempts=InvestigationRun.attempts + (0 if exhausted else 1),
                    lease_token=None if exhausted else token,
                    lease_until=None if exhausted else now + timedelta(seconds=self.lease_seconds),
                )
                .returning(InvestigationRun.id)
                .execution_options(synchronize_session=False)
            )
            if changed is None:
                return None
            self.repository.audit(
                session,
                context,
                candidate.id,
                "investigation.exhausted" if exhausted else "investigation.claim",
                candidate.revision + 1,
            )
            authorize(context, "investigations:transition")
            if exhausted:
                return None
            # Refresh because the CAS intentionally does not synchronize the identity map.
            await session.refresh(candidate)
            snapshot = await self.repository.snapshot(session, context, candidate.id)
            if snapshot is None or candidate.question is None:
                raise InvestigationConflict()
            return WorkItem(snapshot, candidate.question, token)

    async def finish(
        self,
        context: AuthorizationContext,
        item: WorkItem,
        report: InvestigationReport | None,
    ) -> None:
        authorize(context, "investigations:transition")
        if report is not None:
            report = InvestigationReport.model_validate(report.model_dump())
            if (
                report.run_id != item.snapshot.run_id
                or len(report.model_dump_json().encode()) > 262144
                or any(e.reference.source not in context.allowed_sources for e in report.evidence)
            ):
                raise InvestigationConflict()
        async with self.repository.transaction() as session:
            current = await self.repository.snapshot(session, context, item.snapshot.run_id)
            if current is None or current.incident != item.snapshot.incident:
                raise InvestigationConflict()
            changed = await session.scalar(
                update(InvestigationRun)
                .where(
                    InvestigationRun.id == item.snapshot.run_id,
                    InvestigationRun.tenant_id == context.tenant_id,
                    InvestigationRun.status == "running",
                    InvestigationRun.revision == item.snapshot.revision,
                    InvestigationRun.lease_token == item.token,
                    InvestigationRun.lease_until > datetime.now(UTC),
                )
                .values(
                    status="completed" if report else "pending",
                    revision=InvestigationRun.revision + 1,
                    report=report.model_dump(mode="json") if report else None,
                    lease_token=None,
                    lease_until=None,
                )
                .returning(InvestigationRun.id)
            )
            if changed is None:
                raise InvestigationConflict()
            self.repository.audit(
                session,
                context,
                item.snapshot.run_id,
                "investigation.completed" if report else "investigation.retry",
                item.snapshot.revision + 1,
            )
            authorize(context, "investigations:transition")

    async def run_once(
        self,
        context: AuthorizationContext,
        handler: Callable[[AuthorizationContext, WorkItem], Awaitable[InvestigationReport]],
    ) -> bool:
        item = await self.claim(context)
        if item is None:
            return False
        try:
            # Shorter execution deadline leaves time to commit before lease expiry.
            async with asyncio.timeout(self.lease_seconds - 2):
                report = await handler(context, item)
            await self.finish(context, item, report)
        except asyncio.CancelledError:
            # A stopped process leaves its lease to expire for another worker.
            raise
        except InvestigationConflict:
            pass  # Cancellation/reclaim won: stale output must never be published.
        except Exception:
            # No raw exception, question or result is logged or persisted.
            try:
                await self.finish(context, item, None)
            except InvestigationConflict:
                pass
        return True

    async def serve(
        self,
        context_factory: Callable[[], AuthorizationContext],
        handler: Callable[[AuthorizationContext, WorkItem], Awaitable[InvestigationReport]],
        stop: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            try:
                await self.run_once(context_factory(), handler)
            except InvestigationUnavailable:
                pass  # SQL remains authoritative; retry polling after the bounded delay.
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
