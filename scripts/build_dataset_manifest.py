# ruff: noqa: E501
"""Regenerate the checked-in manifest from verified local research downloads."""

import csv
import hashlib
import json
from pathlib import Path

research = Path(".local/research")
commit = "dd61d0952749ee7963bde24220d1be5ede023033"
datasets = {}
sizes = {
    "Apache": (56481, "4.90 MiB", "tar.gz"),
    "OpenStack": (207820, "58.61 MiB", "tar.gz"),
    "BGL": (4747963, "708.76 MiB", "zip"),
    "HDFS": (11175629, "1.47 GiB", "zip"),
    "Zookeeper": (74380, "9.95 MiB", "tar.gz"),
}
for name, (records, size, ext) in sizes.items():
    raw = (research / f"{name}.log").read_bytes()
    with (research / f"{name}.csv").open(encoding="utf-8") as f:
        schema = next(csv.reader(f))
    archive = "HDFS_v1" if name == "HDFS" else name
    datasets[f"loghub-{name.lower()}"] = {
        "name": f"Loghub {name}",
        "source": "https://github.com/logpai/loghub",
        "source_revision": commit,
        "license": "Loghub research/academic-use terms; attribution and notice required",
        "license_url": f"https://github.com/logpai/loghub/blob/{commit}/LICENSE",
        "download_url": f"https://raw.githubusercontent.com/logpai/loghub/{commit}/{name}/{name}_2k.log",
        "filename": f"{name}_2k.log",
        "format": "UTF-8 text, source-specific log format",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "record_count": 2000,
        "structured_reference_schema": schema,
        "parser": name,
        "intended_use": "Independent log parsing, severity distributions and repeated-message features",
        "limitations": [
            "Samples are not representative timelines",
            "No shared BPI incident identifiers",
            "Source local timezone is unspecified (BGL epoch is usable)",
            "Raw logs may contain identifiers; do not publish raw data",
        ],
        "full_download_url": f"https://zenodo.org/records/8196385/files/{archive}.{ext}?download=1",
        "full_record_count_publisher": records,
        "full_raw_size_publisher": size,
        "full_download_verification": "Publisher link verified; archive not downloaded/checksummed in milestone 1",
        "download_requirements": "Samples: public HTTPS, no authentication. Full archives: Zenodo, terms apply; checksum must be recorded before local import.",
    }
for article, key, filename, count, parser in [
    (12693914, "bpi-2013", "BPI_Challenge_2013_incidents.xes.gz", 7554, "xes"),
    (12692378, "bpi-2014", "Detail_Incident.csv", 46809, "bpi-csv"),
]:
    meta = json.loads((research / f"{article}.json").read_text())
    raw = (research / filename).read_bytes()
    item = next(f for f in meta["files"] if f["name"] == filename)
    if parser == "xes":
        schema = {
            "trace": ["concept:name"],
            "event": [
                "org:group",
                "resource country",
                "organization country",
                "org:resource",
                "organization involved",
                "org:role",
                "concept:name",
                "impact",
                "product",
                "lifecycle:transition",
                "time:timestamp",
            ],
        }
    else:
        with (research / filename).open(encoding="utf-8-sig") as f:
            schema = next(csv.reader(f, delimiter=";"))
    datasets[key] = {
        "name": meta["title"],
        "source": f"https://figshare.com/articles/dataset/_/{article}",
        "doi": meta.get("doi"),
        "license": meta["license"]["name"],
        "license_url": meta["license"]["url"],
        "download_url": item["download_url"],
        "filename": filename,
        "format": "gzip XES XML" if parser == "xes" else "UTF-8 semicolon CSV",
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "record_count": count,
        "event_count": 65533 if parser == "xes" else None,
        "schema": schema,
        "parser": parser,
        "intended_use": "Historical incident status analysis"
        + (
            " and observed event timelines"
            if parser == "xes"
            else " and closure duration where timestamps are usable"
        ),
        "limitations": [
            "No relationship to Loghub or the other BPI release",
            "Title is not provided; generated display label is not a source description",
            "No narrative corrective-action knowledge is inferred",
            "2013 first event is not guaranteed creation time"
            if parser == "xes"
            else "Date strings use day/month/year and have no timezone; trailing unnamed CSV columns retained",
        ],
        "download_requirements": "Public HTTPS; 4TU General Terms apply; local research use only pending license review for other uses. Full file acquired; pipeline supports bounded subsets or all records.",
    }
Path("data").mkdir(exist_ok=True)
Path("data/dataset_manifest.json").write_text(
    json.dumps(
        {
            "verified_at": "2026-09-25",
            "verification": "Downloaded pinned files; SHA-256, byte counts and row counts measured locally. Schema read from actual files; full Loghub sizes/counts are publisher-reported.",
            "datasets": datasets,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
