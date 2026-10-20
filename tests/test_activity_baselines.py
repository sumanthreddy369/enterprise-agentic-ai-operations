"""Synthetic sequences test split isolation and unseen-context fallback."""

from scripts.benchmark_activity import evaluate, fit, partition, predict


def test_stable_case_partition() -> None:
    assert partition("synthetic", "case-1") == partition("synthetic", "case-1")
    assert {partition("synthetic", str(i)) for i in range(1000)} == {"train", "validation", "test"}


def test_unseen_context_uses_train_only_fallback() -> None:
    model = fit([["start", "work", "end"], ["start", "work", "end"]], 2)
    before = repr(model)
    assert predict(model, ["unseen"], 2) == "end"  # alphabetical tie break
    result = evaluate(model, [["unseen", "new-label"]], 2)
    assert result["accuracy"] == 0
    assert repr(model) == before


def test_context_changes_prediction() -> None:
    model = fit([["start", "work", "end"]], 1)
    assert predict(model, ["start"], 1) == "work"
    assert predict(model, ["work"], 1) == "end"
