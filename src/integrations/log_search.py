"""Typed adapter for the existing local benchmark log index."""

from typing import Any

from pydantic import ValidationError

from src.domain.contracts import AuthorizationContext, LogMatch, LogSearchQuery, LogSearchResult
from src.integrations.opensearch import OpenSearch
from src.models.contracts import LogRecord
from src.security.policy import authorize, authorize_sources
from src.services.errors import InvalidToolOutput, PermissionDenied, ToolUnavailable


class OpenSearchLogSearch:
    def __init__(self, backend: OpenSearch) -> None:
        self.backend = backend

    async def search(self, context: AuthorizationContext, query: LogSearchQuery) -> LogSearchResult:
        authorize(context, "logs:read")
        # Existing benchmark index has no tenant field. Fail closed for every other namespace.
        if context.tenant_id != "local":
            raise PermissionDenied("This index only supports the local benchmark namespace")
        sources = frozenset({query.source}) if query.source else context.allowed_sources
        authorize_sources(context, sources)
        raw = await self.backend.search(
            query.query, query.source, query.limit, allowed_sources=sorted(sources)
        )
        try:
            if raw.get("timed_out", False) or raw.get("_shards", {}).get("failed", 0):
                raise ToolUnavailable("Search returned incomplete results")
            hits: dict[str, Any] = raw["hits"]
            entries = hits["hits"]
            if not isinstance(entries, list) or len(entries) > query.limit:
                raise InvalidToolOutput("Search returned too many or malformed results")
            matches = []
            for item in entries:
                record = LogRecord.model_validate(item["_source"])
                if record.source not in sources:
                    raise InvalidToolOutput("Search violated the authorized source boundary")
                matches.append(
                    LogMatch(index_id=item["_id"], record=record, score=item.get("_score"))
                )
            total = hits["total"]
            result = LogSearchResult(
                matches=tuple(matches), total=total["value"], total_relation=total["relation"]
            )
            if result.total < len(result.matches):
                raise InvalidToolOutput("Search result count is inconsistent")
        except (KeyError, TypeError, AttributeError, ValidationError):
            raise InvalidToolOutput("Search returned an invalid result") from None
        authorize(context, "logs:read")
        return result
