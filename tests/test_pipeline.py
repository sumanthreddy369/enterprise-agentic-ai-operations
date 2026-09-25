import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from sqlalchemy import func, select

from src.models.database import ApplicationLog, Incident, IncidentEvent
from src.pipelines.load import load_silver, stable_id
from src.pipelines.normalize import severity, status, timestamp
from src.pipelines.runner import process
from src.services.db import make_engine, session_factory

# All inline fixtures are synthetic and exist only inside temporary test directories.
APACHE = "[Sun Dec 04 04:47:44 2005] [error] synthetic test message\n"


def test_timestamp_policy() -> None:
    assert timestamp("2026-01-01T12:00:00+02:00") == datetime(2026, 1, 1, 10, tzinfo=UTC)
    assert timestamp("2026-01-01T12:00:00") is None
    assert timestamp("") is None
    assert timestamp("2026-01-01T12:00:00", timezone="UTC") is not None
    with pytest.raises(ValueError):
        timestamp("not-a-date")
    with pytest.raises(ValueError, match="ambiguous"):
        timestamp("2025-10-26T02:30:00", timezone="Europe/Amsterdam")
    with pytest.raises(ValueError, match="nonexistent"):
        timestamp("2025-03-30T02:30:00", timezone="Europe/Amsterdam")
    assert status("unexpected") == "unknown"
    assert severity("NOTICE") == "info"


def test_pipeline_replay_quarantine_and_recovery(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.log"
    path.write_text(APACHE + APACHE + "invalid synthetic line\n", encoding="utf-8")
    root = tmp_path / "data"
    entry = {"parser": "Apache"}
    first = process("loghub-apache", path, root, entry, None)
    assert first["counts"] == {
        "incidents": 0,
        "events": 0,
        "logs": 2,
        "quarantined": 1,
        "duplicates": 0,
    }
    assert process("loghub-apache", path, root, entry, None) == first
    logs = pl.read_parquet(Path(first["silver_path"]) / "logs.parquet")
    assert logs["source_id"].n_unique() == 2  # Repeated content is not a duplicate event.
    assert logs["occurred_at"].null_count() == 2
    repeated = pl.read_parquet(Path(first["gold_path"]) / "repeated_log_messages.parquet")
    assert repeated["occurrences"].to_list() == [2]
    (Path(first["silver_path"]) / "logs.parquet").write_bytes(b"corrupted")
    repaired = process("loghub-apache", path, root, entry, None)
    assert repaired == first
    bronze = next((root / "bronze").rglob("synthetic.log"))
    assert bronze.read_bytes() == path.read_bytes()
    bronze.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Bronze"):
        process("loghub-apache", path, root, entry, None)


async def test_replay_safe_database_load(tmp_path: Path, migrated_url: str) -> None:
    path = tmp_path / "synthetic.log"
    path.write_text(APACHE, encoding="utf-8")
    result = process("loghub-apache", path, tmp_path / "data", {"parser": "Apache"})
    engine = make_engine(migrated_url)
    for _ in range(2):
        await load_silver(Path(result["silver_path"]), session_factory(engine))
    async with session_factory(engine)() as database:
        assert await database.scalar(select(func.count()).select_from(ApplicationLog)) == 1
        assert await database.scalar(select(func.count()).select_from(Incident)) == 0
    assert stable_id("bpi-2013", "same") != stable_id("bpi-2014", "same")
    await engine.dispose()


async def test_xes_complete_trace_and_event_relationship(tmp_path: Path, migrated_url: str) -> None:
    path = tmp_path / "synthetic.xes.gz"
    trace = """<trace><string key="concept:name" value="synthetic-1"/>
    <event><string key="concept:name" value="Accepted"/>
    <string key="lifecycle:transition" value="In Progress"/>
    <date key="time:timestamp" value="2020-01-01T01:00:00+01:00"/></event>
    <event><string key="concept:name" value="Completed"/>
    <string key="lifecycle:transition" value="Closed"/>
    <date key="time:timestamp" value="2020-01-01T02:00:00+01:00"/></event></trace>"""
    path.write_bytes(
        gzip.compress(f'<log xmlns="http://www.xes-standard.org/">{trace}{trace}</log>'.encode())
    )
    result = process("bpi-2013", path, tmp_path / "data", {"parser": "xes"}, 1)
    assert result["counts"]["incidents"] == 1
    assert result["counts"]["events"] == 2
    engine = make_engine(migrated_url)
    await load_silver(Path(result["silver_path"]), session_factory(engine))
    async with session_factory(engine)() as database:
        incident = (await database.scalars(select(Incident))).one()
        assert incident.status == "closed"
        events = list(await database.scalars(select(IncidentEvent)))
        assert len(events) == 2
        assert all(event.incident_id == incident.id for event in events)
    await engine.dispose()


def test_csv_empty_values_and_duplicate_source_ids(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    path.write_text(
        "Incident ID;Status;Open Time;Close Time;;\n"
        "TEST;Closed;01/02/2020 03:00:00;;;\n"
        "TEST;Closed;01/02/2020 03:00:00;;;\n;Closed;bad;;;\n",
        encoding="utf-8",
    )
    result = process("bpi-2014", path, tmp_path / "data", {"parser": "bpi-csv"}, None)
    assert result["counts"]["incidents"] == 1
    assert result["counts"]["duplicates"] == 1
    assert result["counts"]["quarantined"] == 1
    row = pl.read_parquet(Path(result["silver_path"]) / "incidents.parquet").to_dicts()[0]
    assert row["opened_at"] is None
    assert len(json.loads(row["attributes"])["original_values"]) == 6


@pytest.mark.parametrize(
    "name,line",
    [
        ("HDFS", "081109 203615 148 INFO dfs.Test: synthetic message"),
        (
            "BGL",
            "- 1117838570 2005.06.03 node 2005-06-03-15.42.50.675872 "
            "node RAS KERNEL INFO synthetic message",
        ),
        (
            "OpenStack",
            "nova.log 2017-05-16 00:00:00.008 25746 INFO nova.test [req-test] synthetic message",
        ),
        ("Zookeeper", "2015-07-29 17:41:44,747 - INFO  [node:test@774] - synthetic message"),
    ],
)
def test_log_formats(tmp_path: Path, name: str, line: str) -> None:
    path = tmp_path / "synthetic.log"
    path.write_text(line + "\n", encoding="utf-8")
    result = process(f"loghub-{name.lower()}", path, tmp_path / "data", {"parser": name})
    assert result["counts"]["logs"] == 1
    assert result["counts"]["quarantined"] == 0
