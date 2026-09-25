import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pyarrow.parquet as pq
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.integrations.opensearch import OpenSearch
from src.models.contracts import EventRecord, IncidentRecord, LogRecord
from src.models.database import ApplicationLog, Incident, IncidentEvent


def stable_id(source: str, source_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"enterprise-ops:{source}:{source_id}"))


async def upsert(
    session: AsyncSession,
    model: type[Incident] | type[IncidentEvent] | type[ApplicationLog],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    insert = (
        pg_insert
        if session.bind is not None and session.bind.dialect.name == "postgresql"
        else sqlite_insert
    )
    statement = insert(model).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["source", "source_id"],
        set_={
            key: getattr(statement.excluded, key)
            for key in rows[0]
            if key not in {"id", "source", "source_id"}
        },
    )
    await session.execute(statement)


async def load_silver(
    silver: Path, factory: async_sessionmaker[AsyncSession], search: OpenSearch | None = None
) -> dict[str, int]:
    """Commit batches atomically; replay sink failures through deterministic upserts."""
    counts: dict[str, int] = {}
    if search:
        await search.ensure_index()
    targets: list[
        tuple[
            str,
            type[Incident] | type[IncidentEvent] | type[ApplicationLog],
            type[IncidentRecord] | type[EventRecord] | type[LogRecord],
        ]
    ] = [
        ("incidents", Incident, IncidentRecord),
        ("events", IncidentEvent, EventRecord),
        ("logs", ApplicationLog, LogRecord),
    ]
    for kind, model, contract in targets:
        counts[kind] = 0
        for batch in pq.ParquetFile(silver / f"{kind}.parquet").iter_batches(batch_size=50):
            rows = []
            logs = []
            for item in batch.to_pylist():
                item["attributes"] = json.loads(item["attributes"])
                record = contract.model_validate(item)
                row = record.model_dump()
                row["id"] = stable_id(record.source, record.source_id)
                row["attributes"] = {
                    **record.attributes,
                    "provenance": {
                        key: row.pop(key)
                        for key in ["source_file_sha256", "source_record", "synthetic"]
                    },
                }
                if isinstance(record, EventRecord):
                    row["incident_id"] = stable_id(record.source, row.pop("incident_source_id"))
                if isinstance(record, LogRecord):
                    row.pop("timestamp_raw")
                    row.pop("source_severity")
                    logs.append(record)
                rows.append(row)
            async with factory() as session, session.begin():
                await upsert(session, model, rows)
            if search and logs:
                await search.index_logs(logs)
            counts[kind] += len(rows)
    return counts
