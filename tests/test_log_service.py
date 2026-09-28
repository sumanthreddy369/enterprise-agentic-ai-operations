import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from apps.api.main import create_app
from src.domain.contracts import AuthorizationContext, LogMatch, LogSearchQuery, LogSearchResult
from src.integrations.log_search import OpenSearchLogSearch
from src.integrations.opensearch import OpenSearch
from src.models.contracts import LogRecord
from src.security.policy import authorize, authorize_sources
from src.services.errors import InvalidToolOutput, PermissionDenied, ToolUnavailable
from src.services.logs import log_registry
from src.services.ports import LogSearch
from src.services.settings import Settings


def context(**overrides):
    return AuthorizationContext(
        **(
            dict(
                subject="test",
                tenant_id="local",
                request_id="test-request",
                permissions=frozenset({"logs:read"}),
                allowed_sources=frozenset({"loghub-apache"}),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            | overrides
        )
    )


def record(source="loghub-apache"):
    return LogRecord(
        source=source,
        source_id="synthetic-1",
        source_file_sha256="a" * 64,
        source_record=1,
        synthetic=True,
        message="synthetic error",
    )


def payload(source="loghub-apache"):
    return {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_id": "synthetic-index-id",
                    "_score": 0.5,
                    "_source": record(source).model_dump(mode="json"),
                }
            ],
        }
    }


class FakeLogSearch:
    """Synthetic fixture only, never the production application's dependency."""

    async def search(self, context, query):
        authorize(context, "logs:read")
        if context.tenant_id != "local":
            raise PermissionDenied("Unsupported tenant")
        sources = frozenset({query.source}) if query.source else context.allowed_sources
        authorize_sources(context, sources)
        return LogSearchResult(
            matches=(LogMatch(index_id="synthetic-index-id", record=record(), score=0.5),), total=1
        )


@pytest.mark.parametrize("implementation", ["fake", "opensearch"])
async def test_shared_search_contract(implementation: str) -> None:
    async with httpx.AsyncClient(
        base_url="http://search",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload())),
    ) as client:
        adapter: LogSearch = (
            FakeLogSearch() if implementation == "fake" else OpenSearchLogSearch(OpenSearch(client))
        )
        result = await adapter.search(context(), LogSearchQuery(query="error"))
        assert result.total == 1
        assert result.matches[0].record.synthetic
        for ctx in [
            context(permissions=frozenset()),
            context(tenant_id="another-tenant"),
            context(allowed_sources=frozenset()),
        ]:
            with pytest.raises(PermissionDenied):
                await adapter.search(ctx, LogSearchQuery(query="error"))
        with pytest.raises(PermissionDenied):
            await adapter.search(context(), LogSearchQuery(query="error", source="secret-source"))


async def test_authorization_filters_reach_backend_and_results_are_checked() -> None:
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=payload("secret-source"))

    async with httpx.AsyncClient(
        base_url="http://search", transport=httpx.MockTransport(handler)
    ) as client:
        adapter = OpenSearchLogSearch(OpenSearch(client))
        with pytest.raises(InvalidToolOutput, match="source boundary"):
            await adapter.search(context(), LogSearchQuery(query="error"))
        assert bodies[0]["query"]["bool"]["filter"] == [{"terms": {"source": ["loghub-apache"]}}]


@pytest.mark.parametrize(
    "data",
    [
        {"hits": {}},
        {**payload(), "_shards": None},
        {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": payload()["hits"]["hits"]}},
        {**payload(), "timed_out": True},
        {**payload(), "_shards": {"failed": 1}},
    ],
)
async def test_bad_or_partial_backend_results_rejected(data) -> None:
    async with httpx.AsyncClient(
        base_url="http://search",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)),
    ) as client:
        with pytest.raises((InvalidToolOutput, ToolUnavailable)):
            await OpenSearchLogSearch(OpenSearch(client)).search(
                context(), LogSearchQuery(query="error")
            )


async def test_api_uses_registry_and_preserves_hits_envelope(migrated_url: str) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            database_url=migrated_url,
            allowed_hosts=["test"],
            api_read_key=SecretStr("read-token"),
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload())),
            base_url="http://search",
        ) as backend,
    ):
        app.state.tools = log_registry(OpenSearchLogSearch(OpenSearch(backend)))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            headers = {"Authorization": "Bearer read-token", "X-Tenant-ID": "spoofed"}
            assert (await api.get("/api/v1/logs?q=error")).status_code == 401
            response = await api.get("/api/v1/logs?q=error", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["hits"]["total"]["value"] == 1
            assert response.json()["hits"]["hits"][0]["_source"]["source"] == "loghub-apache"
            assert (
                await api.get("/api/v1/logs?q=error&source=secret-source", headers=headers)
            ).status_code == 403
            assert (await api.get("/api/v1/logs?q=%20%20", headers=headers)).status_code == 422
            assert (
                await api.get("/api/v1/logs?q=error&source=%20", headers=headers)
            ).status_code == 422
