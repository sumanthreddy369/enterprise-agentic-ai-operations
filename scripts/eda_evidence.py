"""Build aggregate EDA evidence from independently checksum-verified source runs."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from scripts.profile_data import analyze


def distribution(values: list[float]) -> dict[str, float | int | None]:
    """Linear-interpolated quantiles; empty populations remain explicitly absent."""
    if not values:
        return {"count": 0, "min": None, "median": None, "p90": None, "p95": None, "max": None}
    series = pl.Series(values)
    return {
        "count": len(values),
        "min": min(values),
        "median": series.quantile(0.5, interpolation="linear"),
        "p90": series.quantile(0.9, interpolation="linear"),
        "p95": series.quantile(0.95, interpolation="linear"),
        "max": max(values),
    }


def lifecycle(events: pl.DataFrame) -> dict[str, Any]:
    """Analyze source-order paths; never infer timestamp order or causality."""
    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for source, incident, record, activity in events.select(
        "source", "incident_source_id", "source_record", "activity"
    ).iter_rows():
        groups.setdefault((source, incident), []).append((record, activity))
    paths: Counter[tuple[str, ...]] = Counter()
    transitions: Counter[tuple[str, str]] = Counter()
    for records in groups.values():
        path = tuple(activity for _, activity in sorted(records))
        paths[path] += 1
        transitions.update(zip(path, path[1:], strict=False))
    return {
        "ordering": "source_record within source and incident; not inferred time order",
        "events_per_incident": distribution([float(len(rows)) for rows in groups.values()]),
        "unique_paths": len(paths),
        "cases_with_repeated_activity": sum(
            count for path, count in paths.items() if len(set(path)) < len(path)
        ),
        "top_transitions": [
            {"from": pair[0], "to": pair[1], "count": count}
            for pair, count in transitions.most_common(12)
        ],
        "top_path_counts": [count for _, count in paths.most_common(10)],
    }


def build(root: Path, output: Path) -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = analyze(root)
    output.mkdir(parents=True, exist_ok=True)
    coverage_labels, coverage_values = [], []
    duration_values: list[float] = []
    for run in report["runs"]:
        silver = root / "silver" / run["dataset"] / run["run_id"]
        for kind, table in run["tables"].items():
            frame = pl.read_parquet(silver / f"{kind}.parquet")
            table["missing_percent"] = {
                col: round(100 * count / frame.height, 3)
                for col, count in table["null_counts"].items()
            }
            if kind == "events":
                table["lifecycle"] = lifecycle(frame)
            if kind == "incidents":
                durations = []
                for start, end in frame.select("opened_at", "closed_at").drop_nulls().iter_rows():
                    opened, closed = datetime.fromisoformat(start), datetime.fromisoformat(end)
                    if opened.tzinfo is not None and closed.tzinfo is not None:
                        durations.append((closed - opened).total_seconds() / 3600)
                table["observed_duration_hours"] = distribution(durations)
                if run["dataset"] == "bpi-2013":
                    duration_values = durations
            if kind == "logs":
                table["message_length_chars"] = distribution(
                    [float(value) for value in frame["message"].str.len_chars().to_list()]
                )
                table["distinct_nonnull_components"] = frame["component"].drop_nulls().n_unique()
            for field, stats in table["timestamps"].items():
                coverage_labels.append(f"{run['dataset']} / {kind} / {field}")
                coverage_values.append(100 * (stats["present"] - stats["naive"]) / frame.height)

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(12, 6), layout="constrained")
    bars = ax.barh(coverage_labels, coverage_values, color="#247b96")
    ax.bar_label(bars, fmt="%.1f%%", padding=4)
    ax.set_xlim(0, 115)
    ax.set_xlabel("Rows with timezone-aware normalized timestamps (%)")
    ax.set_title("Timestamp readiness — historical public datasets")
    fig.suptitle("Missing normalized time does not mean missing raw time", fontsize=10)
    fig.savefig(output / "01-timestamp-readiness.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.hist(duration_values, bins=60, color="#247b96")
    ax.set_yscale("log")
    ax.set_xlabel("Hours from first observed event to normalized closing time")
    ax.set_ylabel("Incident count (log scale)")
    ax.set_title(f"BPI 2013 observed durations — {len(duration_values):,} complete pairs")
    fig.suptitle(
        "Incomplete cases excluded; not an SLA or original creation-time measure", fontsize=10
    )
    fig.savefig(output / "02-observed-durations.png", dpi=160)
    plt.close(fig)

    event_run = next(run for run in report["runs"] if "events" in run["tables"])
    transitions = event_run["tables"]["events"]["lifecycle"]["top_transitions"]
    fig, ax = plt.subplots(figsize=(12, 6), layout="constrained")
    ax.barh(
        [f"{row['from']} → {row['to']}" for row in transitions][::-1],
        [row["count"] for row in transitions][::-1],
        color="#247b96",
    )
    ax.set_xlabel("Adjacent event pairs in source-record order")
    ax.set_title("BPI 2013 common activity transitions")
    fig.suptitle(
        "Repeated activity is not automatically a reopening, failure or root cause", fontsize=10
    )
    fig.savefig(output / "03-activity-transitions.png", dpi=160)
    plt.close(fig)
    (output / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = build(Path("data"), Path("docs/evidence/eda"))
    print(f"Built aggregate evidence for {len(result['runs'])} verified runs")
