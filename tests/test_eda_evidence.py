import polars as pl

from scripts.eda_evidence import distribution, lifecycle


def test_empty_and_interpolated_distributions() -> None:
    assert distribution([])["median"] is None
    assert distribution([1.0, 3.0])["median"] == 2.0


def test_lifecycle_orders_records_and_keeps_sources_separate() -> None:
    # Synthetic records: same incident identifier in independent sources must not join.
    frame = pl.DataFrame(
        {
            "source": ["synthetic-a", "synthetic-b", "synthetic-a", "synthetic-a"],
            "incident_source_id": ["1", "1", "1", "1"],
            "source_record": [3, 1, 1, 2],
            "activity": ["closed", "other", "open", "open"],
        }
    )
    result = lifecycle(frame)
    assert result["events_per_incident"]["count"] == 2
    assert result["cases_with_repeated_activity"] == 1
    assert result["unique_paths"] == 2
    assert {"from": "open", "to": "closed", "count": 1} in result["top_transitions"]
    assert all(row["from"] != "other" for row in result["top_transitions"])
