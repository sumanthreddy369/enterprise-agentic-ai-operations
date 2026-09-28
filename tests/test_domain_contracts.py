from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.contracts import (
    AuthorizationContext,
    EmbeddingResult,
    Evidence,
    Hypothesis,
    InvestigationReport,
    LogSearchQuery,
    ModelUsage,
    SourceReference,
)


def context(**overrides):
    values = dict(
        subject="test-reader",
        tenant_id="local",
        request_id="test-request",
        permissions=frozenset({"logs:read"}),
        allowed_sources=frozenset({"loghub-apache"}),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return AuthorizationContext(**(values | overrides))


def test_context_frozen_and_expiry_aware() -> None:
    value = context()
    with pytest.raises(ValidationError):
        value.tenant_id = "other"
    with pytest.raises(ValidationError):
        context(expires_at=datetime(2026, 1, 1))
    assert AuthorizationContext.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": " "},
        {"query": "error", "limit": 101},
        {"query": "error", "tenant_id": "spoof"},
        {"query": "error", "source": " "},
    ],
)
def test_query_rejects_bad_or_authorization_input(kwargs) -> None:
    with pytest.raises(ValidationError):
        LogSearchQuery(**kwargs)


def test_citations_resolve_within_report() -> None:
    evidence = Evidence(
        evidence_id="e1",
        reference=SourceReference(source="synthetic-test", source_id="1"),
        revision="v1",
        locator="line:1",
        excerpt="Synthetic observed error",
        content_sha256="a" * 64,
    )
    hypothesis = Hypothesis(statement="Synthetic hypothesis", supporting_evidence_ids=("e1",))
    InvestigationReport(run_id="run", evidence=(evidence,), hypotheses=(hypothesis,))
    with pytest.raises(ValidationError, match="missing evidence"):
        InvestigationReport(run_id="run", evidence=(), hypotheses=(hypothesis,))
    with pytest.raises(ValidationError, match="duplicate evidence"):
        InvestigationReport(run_id="run", evidence=(evidence, evidence), hypotheses=())
    with pytest.raises(ValidationError):
        Hypothesis(statement="Unsupported guess", supporting_evidence_ids=())


def test_embedding_dimensions_and_finite_values() -> None:
    EmbeddingResult(model_revision="test-v1", dimensions=2, vectors=((0.1, 0.2),))
    with pytest.raises(ValidationError, match="dimensions"):
        EmbeddingResult(model_revision="test-v1", dimensions=2, vectors=((0.1,),))
    with pytest.raises(ValidationError):
        EmbeddingResult(model_revision="test-v1", dimensions=1, vectors=((float("nan"),),))


def test_missing_usage_is_not_zero() -> None:
    assert ModelUsage().input_tokens is None
    assert ModelUsage().cost_usd is None
    with pytest.raises(ValidationError):
        ModelUsage(input_tokens=-1)
