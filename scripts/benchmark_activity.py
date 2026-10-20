"""Offline next-activity baselines; incident-disjoint splits and train-only fitting."""

import hashlib
import json
import platform
import time
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl

from scripts.profile_data import analyze


def partition(source: str, incident: str) -> str:
    """Stable case-level 70/15/15 split, independent of observed outcomes."""
    value = int(hashlib.sha256(f"{source}:{incident}".encode()).hexdigest()[:8], 16) % 100
    return "train" if value < 70 else "validation" if value < 85 else "test"


def fit(paths: list[list[str]], order: int) -> dict[tuple[str, ...], Counter[str]]:
    counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for path in paths:
        for i in range(1, len(path)):
            for depth in range(min(order, i) + 1):
                key = tuple(path[i - depth : i]) if depth else ()
                counts[key][path[i]] += 1
    if not counts:
        raise ValueError("Training data contains no next-activity examples")
    return dict(counts)


def predict(counts: dict[tuple[str, ...], Counter[str]], prefix: list[str], order: int) -> str:
    for depth in range(min(order, len(prefix)), -1, -1):
        key = tuple(prefix[-depth:]) if depth else ()
        if key in counts:
            return sorted(counts[key], key=lambda label: (-counts[key][label], label))[0]
    raise ValueError("Model has no fallback distribution")


def evaluate(
    counts: dict[tuple[str, ...], Counter[str]], paths: list[list[str]], order: int
) -> dict[str, object]:
    pairs: Counter[tuple[str, str]] = Counter()
    case_scores = []
    start = time.perf_counter()
    for path in paths:
        correct = 0
        for i in range(1, len(path)):
            guess = predict(counts, path[max(0, i - order) : i], order)
            pairs[path[i], guess] += 1
            correct += guess == path[i]
        if len(path) > 1:
            case_scores.append(correct / (len(path) - 1))
    seconds = time.perf_counter() - start
    labels = sorted({actual for actual, _ in pairs})
    f1s = []
    for label in labels:
        tp = pairs[label, label]
        fp = sum(n for (a, p), n in pairs.items() if p == label and a != label)
        fn = sum(n for (a, p), n in pairs.items() if a == label and p != label)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    total = sum(pairs.values())
    if not total:
        raise ValueError("Evaluation has no next-activity examples")
    return {
        "transitions": total,
        "accuracy": sum(n for (a, p), n in pairs.items() if a == p) / total,
        "macro_f1": sum(f1s) / len(f1s),
        "mean_case_accuracy": sum(case_scores) / len(case_scores),
        "evaluation_seconds": seconds,
        "transitions_per_second": total / seconds,
        "confusion": [{"actual": a, "predicted": p, "count": n} for (a, p), n in pairs.items()],
    }


def main() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = analyze(Path("data"))
    runs = [run for run in report["runs"] if run["dataset"] == "bpi-2013"]
    if len(runs) != 1:
        raise ValueError("Expected exactly one verified full BPI 2013 run")
    run = runs[0]
    frame = pl.read_parquet(Path("data/silver/bpi-2013") / run["run_id"] / "events.parquet")
    groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for source, incident, record, activity in frame.select(
        "source", "incident_source_id", "source_record", "activity"
    ).iter_rows():
        groups[source, incident].append((record, activity))
    splits: dict[str, list[list[str]]] = {"train": [], "validation": [], "test": []}
    for (source, incident), events in sorted(groups.items()):
        splits[partition(source, incident)].append([a for _, a in sorted(events)])
    train_paths = {tuple(path) for path in splits["train"]}
    novel_paths = [p for p in splits["test"] if tuple(p) not in train_paths]
    results = []
    for order, name in enumerate(("Majority", "Markov order 1", "Markov order 2")):
        start = time.perf_counter()
        model = fit(splits["train"], order)
        fit_seconds = time.perf_counter() - start
        results.append(
            {
                "model": name,
                "order": order,
                "fit_seconds": fit_seconds,
                "contexts": len(model),
                "validation": evaluate(model, splits["validation"], order),
                "test": evaluate(model, splits["test"], order),
                "unseen_path_test": evaluate(model, novel_paths, order) if novel_paths else None,
            }
        )
    selected = max(results, key=lambda row: row["validation"]["macro_f1"])
    output = Path("docs/evidence/model-baselines")
    output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "generated_at": report["generated_at"],
        "source_sha256": run["source_sha256"],
        "run_id": run["run_id"],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "execution": "Local CPU; no Azure compute or GPU",
        "split": "SHA256(source:incident), first 8 hex digits modulo 100; 70/15/15",
        "case_counts": {key: len(paths) for key, paths in splits.items()},
        "test_paths_seen_in_train": sum(tuple(p) in train_paths for p in splits["test"]),
        "test_unseen_paths": len(novel_paths),
        "selected_by_validation_macro_f1": selected["model"],
        "results": results,
    }
    (output / "results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax, metric in zip(axes, ("accuracy", "macro_f1"), strict=True):
        values = [row["test"][metric] for row in results]
        bars = ax.bar(
            [row["model"] for row in results], values, color=["#8799a6", "#247b96", "#20805b"]
        )
        ax.bar_label(bars, fmt="%.3f")
        ax.set_ylim(0, 1)
        ax.set_title("Test " + metric.replace("_", " "))
    fig.suptitle("BPI 2013 next activity — incident-disjoint holdout, local CPU")
    fig.savefig(output / "model-comparison.jpg", dpi=180)
    plt.close(fig)
    print(json.dumps({k: v for k, v in evidence.items() if k != "results"}, indent=2))
    for row in results:
        print(row["model"], row["test"]["accuracy"], row["test"]["macro_f1"])


if __name__ == "__main__":
    main()
