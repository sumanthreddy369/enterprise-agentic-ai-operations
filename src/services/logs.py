from pydantic import JsonValue

from src.domain.contracts import (
    AuthorizationContext,
    LogSearchQuery,
    LogSearchResult,
    ToolDescriptor,
)
from src.services.ports import LogSearch
from src.services.tools import ToolRegistry, TypedTool


def log_registry(search: LogSearch) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        TypedTool(
            descriptor=ToolDescriptor(
                name="logs.search",
                permission="logs:read",
                description="Search authorized operational log sources.",
            ),
            input_model=LogSearchQuery,
            output_model=LogSearchResult,
            handler=search.search,
        )
    )
    registry.seal()
    return registry


async def search_logs(
    registry: ToolRegistry, context: AuthorizationContext, query: LogSearchQuery
) -> LogSearchResult:
    result = await registry.execute(
        "logs.search",
        context,
        {
            "query": query.query,
            "source": query.source,
            "limit": query.limit,
        },
    )
    return LogSearchResult.model_validate(result.model_dump())


def search_envelope(result: LogSearchResult) -> dict[str, JsonValue]:
    """Preserve the documented OpenSearch hits envelope without leaking backend internals."""
    return {
        "hits": {
            "total": {"value": result.total, "relation": result.total_relation},
            "hits": [
                {
                    "_id": hit.index_id,
                    "_score": hit.score,
                    "_source": hit.record.model_dump(mode="json"),
                }
                for hit in result.matches
            ],
        }
    }
