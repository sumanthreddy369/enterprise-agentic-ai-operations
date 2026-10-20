"""SQL-authoritative run lifecycle and authorized report retrieval."""

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.contracts import (
    AuthorizationContext,
    InvestigationReport,
    InvestigationRequest,
    InvestigationSnapshot,
    SourceReference,
)
from src.models.database import AuditEvent, Incident, InvestigationRun
from src.services.errors import PermissionDenied, ServiceError

logger = logging.getLogger(__name__)


class InvestigationConflict(ServiceError):
    pass


class InvestigationNotFound(ServiceError):
    pass


class InvestigationUnavailable(ServiceError):
    pass


def authorize(context: AuthorizationContext, permission: str) -> None:
    # Existing incident rows have no enterprise tenant ownership. Reject other tenants.
    if (
        context.tenant_id != "local"
        or context.expires_at <= datetime.now(UTC)
        or permission not in context.permissions
    ):
        raise PermissionDenied()


class SQLInvestigationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        try:
            async with asyncio.timeout(10), self.sessions() as session, session.begin():
                yield session
        except (SQLAlchemyError, TimeoutError):
            logger.warning("investigation_database_failure")
            raise InvestigationUnavailable() from None

    @staticmethod
    def audit(
        session: AsyncSession,
        context: AuthorizationContext,
        run_id: str,
        action: str,
        revision: int,
    ) -> None:
        session.add(
            AuditEvent(
                actor=context.subject,
                action=action,
                resource_id=run_id,
                request_id=context.request_id,
                details={"revision": revision},
            )
        )

    @staticmethod
    async def snapshot(
        session: AsyncSession, context: AuthorizationContext, run_id: str
    ) -> InvestigationSnapshot | None:
        row = (
            await session.execute(
                select(InvestigationRun, Incident)
                .join(Incident, InvestigationRun.incident_id == Incident.id)
                .where(
                    InvestigationRun.id == run_id,
                    InvestigationRun.tenant_id == context.tenant_id,
                    InvestigationRun.submission_key.is_not(None),
                    Incident.source.in_(context.allowed_sources),
                )
            )
        ).first()
        if row is None:
            return None
        run, incident = row
        return InvestigationSnapshot.model_validate(
            {
                "run_id": run.id,
                "tenant_id": run.tenant_id,
                "incident": SourceReference(source=incident.source, source_id=incident.source_id),
                "status": run.status,
                "revision": run.revision,
            }
        )

    async def create(
        self, context: AuthorizationContext, request: InvestigationRequest
    ) -> InvestigationSnapshot:
        authorize(context, "investigations:write")
        if request.incident.source not in context.allowed_sources:
            raise PermissionDenied()
        key = hashlib.sha256(
            json.dumps([context.tenant_id, context.subject, request.idempotency_key]).encode()
        ).hexdigest()
        digest = hashlib.sha256(
            request.model_dump_json(exclude={"idempotency_key"}).encode()
        ).hexdigest()
        async with self.transaction() as session:
            incident_id = await session.scalar(
                select(Incident.id).where(
                    Incident.source == request.incident.source,
                    Incident.source_id == request.incident.source_id,
                )
            )
            if incident_id is None:
                raise InvestigationNotFound()
            insert = (
                sqlite_insert
                if session.bind is not None and (session.bind.dialect.name == "sqlite")
                else pg_insert
            )
            run_id = str(uuid4())
            await session.execute(
                insert(InvestigationRun)
                .values(
                    id=run_id,
                    incident_id=incident_id,
                    requested_by=context.subject,
                    tenant_id=context.tenant_id,
                    question=request.question,
                    submission_key=key,
                    request_hash=digest,
                    status="pending",
                    revision=0,
                )
                .on_conflict_do_nothing(index_elements=["submission_key"])
            )
            existing = (
                await session.scalars(
                    select(InvestigationRun).where(InvestigationRun.submission_key == key)
                )
            ).one()
            if existing.request_hash != digest:
                raise InvestigationConflict()
            if existing.id == run_id:
                self.audit(session, context, run_id, "investigation.create", 0)
            result = await self.snapshot(session, context, existing.id)
            if result is None:
                raise InvestigationNotFound()
            authorize(context, "investigations:write")
        logger.info(
            "investigation_submission",
            extra={"run_id": result.run_id, "request_id": context.request_id},
        )
        return result

    async def get(self, context: AuthorizationContext, run_id: str) -> InvestigationSnapshot | None:
        authorize(context, "investigations:read")
        async with self.transaction() as session:
            result = await self.snapshot(session, context, run_id)
            authorize(context, "investigations:read")
            return result

    async def get_report(
        self, context: AuthorizationContext, run_id: str
    ) -> InvestigationReport | None:
        authorize(context, "investigations:read")
        async with self.transaction() as session:
            snapshot = await self.snapshot(session, context, run_id)
            if snapshot is None:
                raise InvestigationNotFound()
            row = await session.get(InvestigationRun, run_id)
            if row is None or row.status != "completed" or row.report is None:
                return None
            report = InvestigationReport.model_validate(row.report)
            if any(e.reference.source not in context.allowed_sources for e in report.evidence):
                raise PermissionDenied()
            authorize(context, "investigations:read")
            return report

    async def transition(
        self,
        context: AuthorizationContext,
        snapshot: InvestigationSnapshot,
        *,
        expected_revision: int,
    ) -> InvestigationSnapshot:
        permission = (
            "investigations:write"
            if snapshot.status == "cancelled"
            else "investigations:transition"
        )
        authorize(context, permission)
        async with self.transaction() as session:
            current = await self.snapshot(session, context, snapshot.run_id)
            if current is None:
                raise InvestigationNotFound()
            # Never permit callers to replace identity, source or revision through a snapshot.
            if (
                snapshot.tenant_id != current.tenant_id
                or snapshot.incident != current.incident
                or snapshot.revision != expected_revision
                or current.revision != expected_revision
            ):
                raise InvestigationConflict()
            allowed = {"pending": {"running", "cancelled"}, "running": {"failed", "cancelled"}}
            if snapshot.status not in allowed.get(current.status, set()):
                raise InvestigationConflict()
            changed = await session.scalar(
                update(InvestigationRun)
                .where(
                    InvestigationRun.id == current.run_id,
                    InvestigationRun.tenant_id == context.tenant_id,
                    InvestigationRun.revision == expected_revision,
                    InvestigationRun.status == current.status,
                )
                .values(status=snapshot.status, revision=expected_revision + 1)
                .returning(InvestigationRun.id)
            )
            if changed is None:
                raise InvestigationConflict()
            self.audit(
                session,
                context,
                current.run_id,
                f"investigation.{snapshot.status}",
                expected_revision + 1,
            )
            authorize(context, permission)
            result = snapshot.model_copy(update={"revision": expected_revision + 1})
        logger.info(
            "investigation_transition",
            extra={"run_id": result.run_id, "request_id": context.request_id},
        )
        return result
