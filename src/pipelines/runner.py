import hashlib
import json
import logging
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from filelock import FileLock

from src.ingestion.acquire import sha256_file
from src.pipelines.parsers import Parsed, csv_incidents, log_records, xes_records

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "1"
BASE_FIELDS = [
    ("source", pa.string()),
    ("source_id", pa.string()),
    ("source_file_sha256", pa.string()),
    ("source_record", pa.int64()),
    ("synthetic", pa.bool_()),
    ("attributes", pa.string()),
]
SCHEMAS = {
    "incidents": pa.schema(
        BASE_FIELDS
        + [
            (key, pa.string())
            for key in ["title", "status", "source_status", "opened_at", "closed_at"]
        ]
    ),
    "events": pa.schema(
        BASE_FIELDS
        + [(key, pa.string()) for key in ["incident_source_id", "activity", "occurred_at"]]
    ),
    "logs": pa.schema(
        BASE_FIELDS
        + [
            (key, pa.string())
            for key in [
                "occurred_at",
                "timestamp_raw",
                "severity",
                "source_severity",
                "message",
                "component",
            ]
        ]
    ),
}


def gold(silver: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    incidents = pl.scan_parquet(silver / "incidents.parquet")
    incidents.group_by("source", "status").agg(pl.len().alias("incident_count")).sort(
        "source", "status"
    ).sink_parquet(destination / "incident_status_counts.parquet")
    incidents.select(
        "source", "source_id", "title", "status", "opened_at", "closed_at"
    ).sink_parquet(destination / "incident_history.parquet")
    events = pl.scan_parquet(silver / "events.parquet")
    events.sort("source", "incident_source_id", "occurred_at", "source_id").sink_parquet(
        destination / "incident_timelines.parquet"
    )
    logs = pl.scan_parquet(silver / "logs.parquet")
    logs.group_by("source", "severity", "component").agg(pl.len().alias("log_count")).sink_parquet(
        destination / "log_severity_counts.parquet"
    )
    logs.group_by("source", "message").agg(pl.len().alias("occurrences")).filter(
        pl.col("occurrences") > 1
    ).sink_parquet(destination / "repeated_log_messages.parquet")


def process(
    dataset: str,
    path: Path,
    root: Path,
    entry: dict[str, Any],
    limit: int | None = 100,
    timezone: str | None = None,
) -> dict[str, Any]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive or None")
    if dataset not in {
        "bpi-2013",
        "bpi-2014",
        "loghub-apache",
        "loghub-openstack",
        "loghub-bgl",
        "loghub-hdfs",
        "loghub-zookeeper",
    }:
        raise ValueError("unknown dataset")
    if timezone is not None:
        ZoneInfo(timezone)  # Reject a bad configuration before processing records.
    digest = sha256_file(path)
    config = {
        "version": PIPELINE_VERSION,
        "dataset": dataset,
        "sha256": digest,
        "limit": limit,
        "timezone": timezone,
        "parser": entry["parser"],
    }
    run_id = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:24]
    lock_dir = root / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock_dir / f"{dataset}.lock")):
        manifest_path = root / "manifests" / dataset / f"{run_id}.json"
        if manifest_path.exists():
            previous: dict[str, Any] = json.loads(manifest_path.read_text())
            if all(
                (root / name).exists() and sha256_file(root / name) == sha
                for name, sha in previous["outputs"].items()
            ):
                return previous
        bronze = root / "bronze" / dataset / digest / path.name
        bronze.parent.mkdir(parents=True, exist_ok=True)
        if bronze.exists() and sha256_file(bronze) != digest:
            raise ValueError("immutable Bronze object has been corrupted")
        if not bronze.exists():
            temporary = bronze.with_suffix(bronze.suffix + ".partial")
            shutil.copyfile(path, temporary)
            if sha256_file(temporary) != digest:
                raise ValueError("source changed during copy")
            temporary.replace(bronze)
        silver = root / "silver" / dataset / run_id
        gold_dir = root / "gold" / dataset / run_id
        silver.mkdir(parents=True, exist_ok=True)
        parser = entry["parser"]
        records: Iterator[Parsed]
        if parser == "xes":
            records = xes_records(bronze, dataset, digest, limit)
        elif parser == "bpi-csv":
            records = csv_incidents(bronze, dataset, digest, limit, timezone)
        else:
            records = log_records(bronze, parser, dataset, digest, limit, timezone)
        writers = {
            kind: pq.ParquetWriter(silver / f"{kind}.parquet", schema, compression="zstd")
            for kind, schema in SCHEMAS.items()
        }
        buffers: dict[str, list[dict[str, Any]]] = {kind: [] for kind in SCHEMAS}
        counts = {"incidents": 0, "events": 0, "logs": 0, "quarantined": 0, "duplicates": 0}
        seen: set[tuple[str, str]] = set()
        quarantine: TextIO
        try:
            with (silver / "quarantine.jsonl").open("w", encoding="utf-8") as quarantine:
                for kind, record in records:
                    if kind == "quarantine":
                        counts["quarantined"] += 1
                        quarantine.write(json.dumps(record) + "\n")
                        continue
                    if isinstance(record, dict):
                        raise TypeError("parser returned invalid record")
                    key = kind, record.source_id
                    if key in seen:
                        counts["duplicates"] += 1
                        continue
                    if kind != "logs":
                        seen.add(key)
                    row = record.model_dump(mode="json")
                    row["attributes"] = json.dumps(row["attributes"], sort_keys=True)
                    buffers[kind].append(row)
                    counts[kind] += 1
                    if len(buffers[kind]) >= 1000:
                        writers[kind].write_table(
                            pa.Table.from_pylist(buffers[kind], schema=SCHEMAS[kind])
                        )
                        buffers[kind].clear()
                for kind, buffer in buffers.items():
                    if buffer:
                        writers[kind].write_table(
                            pa.Table.from_pylist(buffer, schema=SCHEMAS[kind])
                        )
        finally:
            for writer in writers.values():
                writer.close()
        gold(silver, gold_dir)
        outputs = {
            str(item.relative_to(root).as_posix()): sha256_file(item)
            for directory in [silver, gold_dir]
            for item in directory.iterdir()
            if item.is_file()
        }
        outputs[str(bronze.relative_to(root).as_posix())] = digest
        result = {
            **config,
            "run_id": run_id,
            "counts": counts,
            "outputs": outputs,
            "silver_path": str(silver),
            "gold_path": str(gold_dir),
            "source_url": entry.get("source"),
            "license": entry.get("license"),
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_manifest = manifest_path.with_suffix(".partial")
        temporary_manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary_manifest.replace(manifest_path)
        logger.info("pipeline_completed", extra={"run_id": run_id, "counts": counts})
        return result
