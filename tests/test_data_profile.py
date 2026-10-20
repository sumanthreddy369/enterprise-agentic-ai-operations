import polars as pl

from scripts.profile_data import profile


def test_profile_distinguishes_missing_naive_and_duplicate_keys() -> None:
    frame = pl.DataFrame(
        {
            "source": ["synthetic-a", "synthetic-b", "synthetic-a"],
            "source_id": ["1", "1", "1"],
            "synthetic": [True, True, True],
            "occurred_at": [None, "2026-01-01T00:00:00", "2026-01-01T01:00:00+01:00"],
            "message": ["synthetic repeated", "synthetic repeated", "synthetic distinct"],
        }
    )
    result = profile(frame)
    assert result["duplicate_source_keys"] == 1
    assert result["null_counts"]["occurred_at"] == 1
    assert result["timestamps"]["occurred_at"]["naive"] == 1
    assert result["timestamps"]["occurred_at"]["min_utc"] == "2026-01-01T00:00:00+00:00"
    assert result["repeated_message_excess_rows"] == 1
    assert "synthetic repeated" not in str(result)
