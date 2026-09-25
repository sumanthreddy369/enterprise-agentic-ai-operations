from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonEmpty = Annotated[str, Field(min_length=1, max_length=512)]


class Status(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Provenance(Contract):
    source: NonEmpty
    source_id: NonEmpty
    source_file_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_record: Annotated[int, Field(ge=1)]
    synthetic: bool = False


class IncidentRecord(Provenance):
    title: Annotated[str, Field(min_length=1, max_length=1000)]
    status: Status = Status.UNKNOWN
    source_status: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("timestamp must include a timezone")
            return value.astimezone(UTC)
        return value


class EventRecord(Provenance):
    incident_source_id: NonEmpty
    activity: NonEmpty
    occurred_at: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


class LogRecord(Provenance):
    occurred_at: datetime | None = None
    timestamp_raw: str | None = None
    severity: Severity = Severity.UNKNOWN
    source_severity: str | None = None
    message: Annotated[str, Field(min_length=1)]
    component: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_aware(cls, value: datetime | None) -> datetime | None:
        return IncidentRecord.require_aware(value)


class IncidentCreate(Contract):
    source_id: NonEmpty
    title: Annotated[str, Field(min_length=1, max_length=1000)]
    status: Status = Status.OPEN
    opened_at: datetime

    @field_validator("opened_at")
    @classmethod
    def require_aware(cls, value: datetime) -> datetime:
        return EventRecord.require_aware(value)


class IncidentView(Contract):
    id: str
    source: str
    source_id: str
    title: str
    status: str
    opened_at: datetime | None
    closed_at: datetime | None
