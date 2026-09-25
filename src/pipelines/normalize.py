from datetime import UTC, datetime

import pandas as pd

from src.models.contracts import Severity, Status


def status(value: str | None) -> Status:
    return {
        "open": Status.OPEN,
        "registered": Status.OPEN,
        "queued": Status.OPEN,
        "awaiting assignment": Status.OPEN,
        "in progress": Status.IN_PROGRESS,
        "accepted": Status.IN_PROGRESS,
        "resolved": Status.RESOLVED,
        "completed": Status.RESOLVED,
        "closed": Status.CLOSED,
    }.get((value or "").strip().lower(), Status.UNKNOWN)


def severity(value: str | None) -> Severity:
    return {
        "debug": Severity.DEBUG,
        "info": Severity.INFO,
        "notice": Severity.INFO,
        "warn": Severity.WARNING,
        "warning": Severity.WARNING,
        "error": Severity.ERROR,
        "err": Severity.ERROR,
        "fatal": Severity.CRITICAL,
        "critical": Severity.CRITICAL,
        "alert": Severity.CRITICAL,
        "emerg": Severity.CRITICAL,
    }.get((value or "").strip().lower(), Severity.UNKNOWN)


def timestamp(
    value: str | None, fmt: str | None = None, timezone: str | None = None
) -> datetime | None:
    if not value or not value.strip():
        return None
    parsed = datetime.strptime(value, fmt) if fmt else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if timezone is None:
            return None  # Unstated source timezone is not silently treated as UTC.
        try:
            parsed = (
                pd.Timestamp(parsed)
                .tz_localize(timezone, ambiguous="raise", nonexistent="raise")
                .to_pydatetime()
            )
        except Exception as exc:
            raise ValueError("invalid, ambiguous or nonexistent source local time") from exc
    return parsed.astimezone(UTC)
