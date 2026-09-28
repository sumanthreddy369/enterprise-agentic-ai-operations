from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from src.models.contracts import LogRecord

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class AuthorizationContext(DomainModel):
    """Construct only after authentication; never deserialize from public request input."""

    subject: Identifier
    tenant_id: Identifier
    request_id: Identifier
    permissions: frozenset[Identifier]
    allowed_sources: frozenset[Identifier]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("authorization expiry must include a timezone")
        return value.astimezone(UTC)


class SourceReference(DomainModel):
    source: Identifier
    source_id: Annotated[str, Field(min_length=1, max_length=512)]


class Evidence(DomainModel):
    evidence_id: Identifier
    reference: SourceReference
    revision: Identifier
    locator: Identifier
    excerpt: Text
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RetrievalQuery(DomainModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    sources: frozenset[Identifier] = frozenset()
    limit: int = Field(default=10, ge=1, le=100)


class RetrievalMatch(DomainModel):
    evidence: Evidence
    score: float | None = None  # A ranking score, never an asserted probability.


class RetrievalResult(DomainModel):
    matches: tuple[RetrievalMatch, ...] = Field(max_length=100)
    strategy: Literal["keyword", "dense", "hybrid"]
    reranked: bool = False


class LogSearchQuery(DomainModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    source: Identifier | None = None
    limit: int = Field(default=20, ge=1, le=100)


class LogMatch(DomainModel):
    index_id: Identifier
    record: LogRecord
    score: float | None = None


class LogSearchResult(DomainModel):
    matches: tuple[LogMatch, ...] = Field(max_length=100)
    total: int = Field(ge=0)
    total_relation: Literal["eq", "gte"] = "eq"


class InvestigationRequest(DomainModel):
    incident: SourceReference
    question: Text
    idempotency_key: Identifier


class InvestigationSnapshot(DomainModel):
    run_id: Identifier
    tenant_id: Identifier
    incident: SourceReference
    status: Literal["pending", "running", "awaiting_approval", "completed", "failed", "cancelled"]
    revision: int = Field(ge=0)


class Hypothesis(DomainModel):
    statement: Text
    supporting_evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=100)


class InvestigationReport(DomainModel):
    run_id: Identifier
    evidence: tuple[Evidence, ...] = Field(max_length=100)
    hypotheses: tuple[Hypothesis, ...] = Field(max_length=30)

    @model_validator(mode="after")
    def check_citations(self) -> Self:
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence identifiers")
        if any(set(item.supporting_evidence_ids) - set(ids) for item in self.hypotheses):
            raise ValueError("hypothesis references missing evidence")
        return self


class ModelMessage(DomainModel):
    role: Literal["system", "user", "assistant"]
    content: Text


class ModelRequest(DomainModel):
    model_alias: Identifier  # Resolved by trusted deployment policy, not a provider URL.
    messages: tuple[ModelMessage, ...] = Field(min_length=1, max_length=30)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)


class ModelUsage(DomainModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    # None means unreported; zero must mean measured zero.


class ModelResponse(DomainModel):
    text: Text
    provider: Identifier
    model_revision: Identifier
    usage: ModelUsage


class EmbeddingRequest(DomainModel):
    texts: tuple[Text, ...] = Field(min_length=1, max_length=64)


class EmbeddingResult(DomainModel):
    model_revision: Identifier
    dimensions: int = Field(ge=1, le=65536)
    vectors: tuple[tuple[float, ...], ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def consistent_dimensions(self) -> Self:
        if any(len(vector) != self.dimensions for vector in self.vectors):
            raise ValueError("embedding dimensions do not match declared contract")
        return self


class RerankRequest(DomainModel):
    query: Text
    candidates: tuple[Evidence, ...] = Field(min_length=1, max_length=100)


class RerankResult(DomainModel):
    model_revision: Identifier
    matches: tuple[RetrievalMatch, ...] = Field(max_length=100)


class ToolDescriptor(DomainModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")]
    permission: Identifier
    description: Text
    read_only: bool = True
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    max_output_bytes: int = Field(default=262144, ge=128, le=1048576)
