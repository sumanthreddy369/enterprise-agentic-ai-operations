"""Async ports; declaring a protocol does not claim a functioning integration."""

from typing import Protocol

from src.domain.contracts import (
    AuthorizationContext,
    EmbeddingRequest,
    EmbeddingResult,
    InvestigationRequest,
    InvestigationSnapshot,
    LogSearchQuery,
    LogSearchResult,
    ModelRequest,
    ModelResponse,
    RerankRequest,
    RerankResult,
    RetrievalQuery,
    RetrievalResult,
    SourceReference,
)
from src.models.contracts import EventRecord, IncidentRecord


class IncidentReader(Protocol):
    async def get_incident(
        self, context: AuthorizationContext, reference: SourceReference
    ) -> IncidentRecord | None: ...

    async def get_events(
        self, context: AuthorizationContext, reference: SourceReference, *, limit: int
    ) -> tuple[EventRecord, ...]: ...


class LogSearch(Protocol):
    async def search(
        self, context: AuthorizationContext, query: LogSearchQuery
    ) -> LogSearchResult: ...


class EvidenceRetriever(Protocol):
    async def retrieve(
        self, context: AuthorizationContext, query: RetrievalQuery
    ) -> RetrievalResult: ...


class ModelGateway(Protocol):
    async def generate(
        self, context: AuthorizationContext, request: ModelRequest
    ) -> ModelResponse: ...


class Embedder(Protocol):
    async def embed(
        self, context: AuthorizationContext, request: EmbeddingRequest
    ) -> EmbeddingResult: ...


class Reranker(Protocol):
    async def rerank(
        self, context: AuthorizationContext, request: RerankRequest
    ) -> RerankResult: ...


class InvestigationRepository(Protocol):
    async def create(
        self, context: AuthorizationContext, request: InvestigationRequest
    ) -> InvestigationSnapshot: ...

    async def get(
        self, context: AuthorizationContext, run_id: str
    ) -> InvestigationSnapshot | None: ...

    async def transition(
        self,
        context: AuthorizationContext,
        snapshot: InvestigationSnapshot,
        *,
        expected_revision: int,
    ) -> InvestigationSnapshot:
        """Must reject stale revisions and cross-tenant access atomically."""
        ...
