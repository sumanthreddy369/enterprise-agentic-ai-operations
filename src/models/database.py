from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.models.types import UTCDateTime


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, onupdate=now)


class Source:
    source: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[str] = mapped_column(String(512))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Service(Identity, Source, Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    name: Mapped[str] = mapped_column(String(512))


class ConfigurationItem(Identity, Source, Base):
    __tablename__ = "configuration_items"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    name: Mapped[str] = mapped_column(String(512))


class Incident(Identity, Source, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        Index("ix_incident_status_time", "status", "opened_at"),
    )
    title: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    source_status: Mapped[str | None] = mapped_column(String(128))
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    configuration_item_id: Mapped[str | None] = mapped_column(ForeignKey("configuration_items.id"))


class IncidentEvent(Identity, Source, Base):
    __tablename__ = "incident_events"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    activity: Mapped[str] = mapped_column(String(512))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class ApplicationLog(Identity, Source, Base):
    __tablename__ = "application_logs"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text)
    component: Mapped[str | None] = mapped_column(String(512))
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"))


class Change(Identity, Source, Base):
    __tablename__ = "changes"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class KnowledgeDocument(Identity, Source, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    title: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str] = mapped_column(Text)


class HistoricalResolution(Identity, Base):
    __tablename__ = "historical_resolutions"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_documents.id"))
    resolution: Mapped[str] = mapped_column(Text)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON)


class InvestigationRun(Identity, Base):
    __tablename__ = "investigation_runs"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    requested_by: Mapped[str] = mapped_column(String(256))


class InvestigationEvidence(Identity, Base):
    __tablename__ = "investigation_evidence"
    run_id: Mapped[str] = mapped_column(ForeignKey("investigation_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[str] = mapped_column(String(512))
    facts: Mapped[dict[str, Any]] = mapped_column(JSON)


class AgentExecution(Identity, Base):
    __tablename__ = "agent_executions"
    run_id: Mapped[str] = mapped_column(ForeignKey("investigation_runs.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RemediationProposal(Identity, Base):
    __tablename__ = "remediation_proposals"
    run_id: Mapped[str] = mapped_column(ForeignKey("investigation_runs.id"), index=True)
    action: Mapped[str] = mapped_column(String(128))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON)
    rollback_plan: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")


class ApprovalRequest(Identity, Base):
    __tablename__ = "approval_requests"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("remediation_proposals.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    approver_identity: Mapped[str | None] = mapped_column(String(256))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    actor: Mapped[str] = mapped_column(String(256))
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_id: Mapped[str] = mapped_column(String(512), index=True)
    request_id: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
