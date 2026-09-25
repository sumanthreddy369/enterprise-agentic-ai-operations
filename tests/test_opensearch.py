import json

import httpx
import pytest

from src.integrations.opensearch import OpenSearch, SearchUnavailable
from src.models.contracts import LogRecord


def record() -> LogRecord:
    return LogRecord(
        source="synthetic",
        source_id="1",
        source_file_sha256="a" * 64,
        source_record=1,
        message="synthetic test message",
        synthetic=True,
    )


async def test_bulk_stable_identity_and_partial_failure() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(200, json={"errors": False})

    async with httpx.AsyncClient(
        base_url="http://search", transport=httpx.MockTransport(handler)
    ) as client:
        adapter = OpenSearch(client)
        assert await adapter.index_logs([record()]) == 1
        assert await adapter.index_logs([record()]) == 1
        assert bodies[0] == bodies[1]
        assert json.loads(bodies[0].splitlines()[0])["index"]["_id"]

    async with httpx.AsyncClient(
        base_url="http://search",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"errors": True, "items": [{"index": {"status": 400}}]}
            )
        ),
    ) as client:
        with pytest.raises(SearchUnavailable, match="rejected"):
            await OpenSearch(client).index_logs([record()])


async def test_retry_rate_limit_and_circuit_breaker(monkeypatch) -> None:
    calls = 0

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("src.integrations.opensearch.asyncio.sleep", no_sleep)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "0"})

    async with httpx.AsyncClient(
        base_url="http://search", transport=httpx.MockTransport(handler)
    ) as client:
        adapter = OpenSearch(client)
        for _ in range(3):
            with pytest.raises(SearchUnavailable):
                await adapter.ready()
        assert calls == 9
        with pytest.raises(SearchUnavailable, match="circuit"):
            await adapter.ready()
        assert calls == 9


async def test_index_mapping_and_search_filters() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "HEAD":
            return httpx.Response(404)
        return httpx.Response(200, json={"hits": {"hits": []}})

    async with httpx.AsyncClient(
        base_url="http://search", transport=httpx.MockTransport(handler)
    ) as client:
        adapter = OpenSearch(client)
        await adapter.ensure_index()
        await adapter.search("failure", "loghub-apache", 5)
    mapping = json.loads(requests[1].content)["mappings"]
    assert mapping["dynamic"] == "strict"
    assert mapping["properties"]["attributes"]["enabled"] is False
    query = json.loads(requests[2].content)
    assert query["query"]["bool"]["filter"] == [{"term": {"source": "loghub-apache"}}]
