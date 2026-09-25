import csv
import gzip
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml.ElementTree import iterparse

from src.models.contracts import EventRecord, IncidentRecord, LogRecord
from src.pipelines.normalize import severity, status, timestamp

Record = IncidentRecord | EventRecord | LogRecord
Parsed = tuple[str, Record | dict[str, Any]]


def attributes(element: Element) -> dict[str, str]:
    return {
        child.attrib["key"]: child.attrib["value"]
        for child in element
        if "key" in child.attrib and "value" in child.attrib
    }


def xes_records(path: Path, source: str, digest: str, limit: int | None) -> Iterator[Parsed]:
    """A subset consists of complete traces, never a truncated incident timeline."""
    count = 0
    with gzip.open(path, "rb") as handle:
        context = iterparse(handle, events=("start", "end"))
        _, root = next(context)
        for event, element in context:
            if event != "end" or not element.tag.endswith("}trace"):
                continue
            count += 1
            trace = attributes(element)
            events = [attributes(child) for child in element if child.tag.endswith("}event")]
            try:
                incident_id = trace["concept:name"]
                normalized = []
                for ordinal, item in enumerate(events, 1):
                    occurred = timestamp(item["time:timestamp"])
                    if occurred is None:
                        raise ValueError("XES event timestamp is missing timezone")
                    normalized.append(
                        EventRecord(
                            source=source,
                            source_id=f"{incident_id}:event:{ordinal}",
                            source_file_sha256=digest,
                            source_record=count,
                            incident_source_id=incident_id,
                            activity=item["concept:name"],
                            occurred_at=occurred,
                            attributes=item,
                        )
                    )
                if not normalized:
                    raise ValueError("trace has no events")
                last = max(normalized, key=lambda item: item.occurred_at)
                source_status = last.attributes.get("lifecycle:transition")
                current_status = status(source_status)
                incident = IncidentRecord(
                    source=source,
                    source_id=incident_id,
                    source_file_sha256=digest,
                    source_record=count,
                    title=f"Source incident {incident_id}",
                    status=current_status,
                    source_status=source_status,
                    opened_at=min(item.occurred_at for item in normalized),
                    closed_at=last.occurred_at if current_status.value == "closed" else None,
                    attributes={"trace": trace, "opened_at_semantics": "first observed event"},
                )
                yield "incidents", incident
                for normalized_event in normalized:
                    yield "events", normalized_event
            except (ValueError, KeyError) as exc:
                yield (
                    "quarantine",
                    {"source_record": count, "reason": str(exc), "trace": trace, "events": events},
                )
            element.clear()
            root.clear()
            if limit is not None and count >= limit:
                break


def csv_incidents(
    path: Path, source: str, digest: str, limit: int | None, timezone: str | None
) -> Iterator[Parsed]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        headers = next(reader)
        if not {"Incident ID", "Status", "Open Time", "Close Time"}.issubset(headers):
            raise ValueError("BPI 2014 incident CSV schema differs from manifest")
        for ordinal, values in enumerate(reader, 1):
            # Unnamed trailing columns stay positional; DictReader would silently collapse them.
            row = {
                key: values[index]
                for index, key in enumerate(headers)
                if key and index < len(values)
            }
            try:
                incident_id = row["Incident ID"]
                yield (
                    "incidents",
                    IncidentRecord(
                        source=source,
                        source_id=incident_id,
                        source_file_sha256=digest,
                        source_record=ordinal,
                        title=f"Source incident {incident_id}",
                        status=status(row.get("Status")),
                        source_status=row.get("Status"),
                        opened_at=timestamp(row.get("Open Time"), "%d/%m/%Y %H:%M:%S", timezone),
                        closed_at=timestamp(row.get("Close Time"), "%d/%m/%Y %H:%M:%S", timezone),
                        attributes={
                            "original": row,
                            "original_values": values,
                            "timestamp_timezone_assumption": timezone,
                        },
                    ),
                )
            except (ValueError, KeyError) as exc:
                yield "quarantine", {"source_record": ordinal, "reason": str(exc), "values": values}
            if limit is not None and ordinal >= limit:
                break


PATTERNS = {
    "Apache": r"^\[(?P<time>[^]]+)\] \[(?P<level>[^]]+)\] (?P<message>.*)$",
    "HDFS": r"^(?P<time>\d{6} \d{6}) (?P<pid>\d+) (?P<level>\w+) (?P<component>[^:]+): (?P<message>.*)$",  # noqa: E501
    "OpenStack": r"^(?P<logrecord>\S+) (?P<time>\d{4}-\d{2}-\d{2} \S+) (?P<pid>\d+) (?P<level>\w+) (?P<component>\S+) \[(?P<address>[^]]*)\] (?P<message>.*)$",  # noqa: E501
    "BGL": r"^(?P<label>\S+) (?P<epoch>\d+) (?P<date>\S+) (?P<node>\S+) (?P<time>\S+) (?P<node_repeat>\S+) (?P<type>\S+) (?P<component>\S+) (?P<level>\S+) (?P<message>.*)$",  # noqa: E501
    "Zookeeper": r"^(?P<time>\d{4}-\d{2}-\d{2} \S+) - (?P<level>\w+)\s+\[(?P<component>.*)\] - (?P<message>.*)$",  # noqa: E501
}
FORMATS = {
    "Apache": "%a %b %d %H:%M:%S %Y",
    "HDFS": "%y%m%d %H%M%S",
    "OpenStack": "%Y-%m-%d %H:%M:%S.%f",
    "Zookeeper": "%Y-%m-%d %H:%M:%S,%f",
}


def log_records(
    path: Path, name: str, source: str, digest: str, limit: int | None, timezone: str | None
) -> Iterator[Parsed]:
    pattern = re.compile(PATTERNS[name])
    with path.open(encoding="utf-8", errors="strict") as handle:
        for ordinal, line in enumerate(handle, 1):
            try:
                match = pattern.match(line.rstrip("\r\n"))
                if match is None:
                    raise ValueError("line does not match documented source format")
                fields = match.groupdict()
                occurred = (
                    datetime.fromtimestamp(int(fields["epoch"]), UTC)
                    if name == "BGL"
                    else timestamp(fields["time"], FORMATS[name], timezone)
                )
                yield (
                    "logs",
                    LogRecord(
                        source=source,
                        source_id=f"{digest}:{ordinal}",
                        source_file_sha256=digest,
                        source_record=ordinal,
                        occurred_at=occurred,
                        timestamp_raw=fields["time"],
                        severity=severity(fields["level"]),
                        source_severity=fields["level"],
                        message=fields["message"],
                        component=fields.get("component"),
                        attributes={**fields, "timestamp_timezone_assumption": timezone},
                    ),
                )
            except (ValueError, KeyError) as exc:
                yield "quarantine", {"source_record": ordinal, "reason": str(exc), "raw": line}
            if limit is not None and ordinal >= limit:
                break
