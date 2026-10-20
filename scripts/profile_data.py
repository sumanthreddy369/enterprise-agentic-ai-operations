"""Aggregate-only EDA of checksum-verified pipeline outputs; no source text export."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from src.ingestion.acquire import sha256_file


def profile(frame: pl.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {
        "rows": frame.height,
        "null_counts": frame.null_count().to_dicts()[0],
        "duplicate_source_keys": frame.height - frame.select("source", "source_id").unique().height,
        "synthetic_rows": frame.filter(pl.col("synthetic")).height,
    }
    for column in ("status", "severity"):
        if column in frame.columns:
            result[column + "_counts"] = frame.group_by(column).len().sort(column).to_dicts()
    result["timestamps"] = {}
    for column in ("opened_at", "closed_at", "occurred_at"):
        if column not in frame.columns:
            continue
        values = frame[column].drop_nulls().to_list()
        parsed = [datetime.fromisoformat(value) for value in values]
        naive = sum(value.tzinfo is None for value in parsed)
        aware = [value.astimezone(UTC) for value in parsed if value.tzinfo is not None]
        result["timestamps"][column] = {
            "present": len(values),
            "naive": naive,
            "min_utc": min(aware).isoformat() if aware else None,
            "max_utc": max(aware).isoformat() if aware else None,
        }
    if "message" in frame.columns:
        result["repeated_message_excess_rows"] = frame.height - frame["message"].n_unique()
    if "closed_at" in frame.columns:
        durations = [
            (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
            for start, end in frame.select("opened_at", "closed_at").drop_nulls().iter_rows()
        ]
        result["duration_pairs"] = len(durations)
        result["negative_duration_pairs"] = sum(value < 0 for value in durations)
    return result


def analyze(root: Path) -> dict[str, Any]:
    runs = []
    for path in sorted((root / "manifests").glob("*/*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["limit"] is not None or run["timezone"] is not None:
            continue  # Compare full inputs under the default unknown-timezone policy only.
        for name, checksum in run["outputs"].items():
            output = (root / name).resolve()
            if not output.is_relative_to(root.resolve()):
                raise ValueError("Manifest output escapes data root")
            if sha256_file(output) != checksum:
                raise ValueError("Output checksum mismatch")
        silver = root / "silver" / run["dataset"] / run["run_id"]
        frames = {
            kind: pl.read_parquet(silver / f"{kind}.parquet")
            for kind in ("incidents", "events", "logs")
        }
        tables = {kind: profile(frame) for kind, frame in frames.items() if frame.height}
        events = frames["events"]
        missing = events.join(
            frames["incidents"].select("source", "source_id"),
            left_on=["source", "incident_source_id"],
            right_on=["source", "source_id"],
            how="anti",
        ).height
        runs.append(
            {
                "dataset": run["dataset"],
                "run_id": run["run_id"],
                "source_sha256": run["sha256"],
                "parser": run["parser"],
                "pipeline_version": run["version"],
                "timezone": run["timezone"],
                "counts": run["counts"],
                "tables": tables,
                "events_without_source_incident": missing,
            }
        )
    if not runs:
        raise ValueError("No full default-timezone runs found; acquire and process data first")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "runs": runs,
        "scope": "Independent historical datasets; no cross-dataset joins or causal claims",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path(".local/eda/profile.json"))
    args = parser.parse_args()
    report = analyze(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Profiled {len(report['runs'])} verified runs; aggregate report: {args.output}")


if __name__ == "__main__":
    main()
