import asyncio
import hashlib
import json
import time
from collections.abc import Sequence
from typing import Any

import httpx

from src.models.contracts import LogRecord


class SearchUnavailable(RuntimeError):
    pass


class OpenSearch:
    """Async, bounded and replay-safe log indexing, with a per-client circuit breaker."""

    def __init__(self, client: httpx.AsyncClient, index: str = "operations-logs-v1") -> None:
        self.client = client
        self.index = index
        self.failures = 0
        self.open_until = 0.0

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if time.monotonic() < self.open_until:
            raise SearchUnavailable("search circuit is open")
        for attempt in range(3):
            response: httpx.Response | None = None
            try:
                response = await self.client.request(method, path, **kwargs)
                if response.status_code != 429 and response.status_code < 500:
                    self.failures = 0
                    return response
            except httpx.TransportError:
                pass
            if attempt < 2:
                delay = float(2**attempt)
                if response is not None:
                    try:
                        delay = min(
                            10.0, max(0.0, float(response.headers.get("retry-after", delay)))
                        )
                    except ValueError:
                        pass
                await asyncio.sleep(delay)
        self.failures += 1
        if self.failures >= 3:
            self.open_until = time.monotonic() + 30
        raise SearchUnavailable("search request exhausted bounded retries")

    async def ensure_index(self) -> None:
        response = await self.request("HEAD", f"/{self.index}")
        if response.status_code == 200:
            return
        response.raise_for_status() if response.status_code != 404 else None
        properties = {
            key: {"type": "keyword"}
            for key in [
                "source",
                "source_id",
                "source_file_sha256",
                "severity",
                "source_severity",
                "component",
            ]
        }
        mapping: dict[str, Any] = {
            **properties,
            "occurred_at": {"type": "date"},
            "timestamp_raw": {"type": "keyword", "index": False},
            "message": {"type": "text"},
            "source_record": {"type": "long"},
            "synthetic": {"type": "boolean"},
            "attributes": {"type": "object", "enabled": False},
        }
        response = await self.request(
            "PUT",
            f"/{self.index}",
            json={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {"dynamic": "strict", "properties": mapping},
            },
        )
        if (
            response.status_code == 400
            and response.json().get("error", {}).get("type") == "resource_already_exists_exception"
        ):
            return
        response.raise_for_status()

    async def index_logs(self, records: Sequence[LogRecord]) -> int:
        if len(records) > 1000:
            raise ValueError("bulk batch cannot exceed 1000 records")
        if not records:
            return 0
        body: list[str] = []
        for record in records:
            key = hashlib.sha256(f"{record.source}\0{record.source_id}".encode()).hexdigest()
            body.extend(
                [
                    json.dumps({"index": {"_index": self.index, "_id": key}}),
                    record.model_dump_json(),
                ]
            )
        payload = "\n".join(body) + "\n"
        for attempt in range(3):
            response = await self.request(
                "POST", "/_bulk", content=payload, headers={"Content-Type": "application/x-ndjson"}
            )
            response.raise_for_status()
            result = response.json()
            if not result.get("errors"):
                return len(records)
            failures = [item["index"] for item in result["items"] if item["index"]["status"] >= 300]
            if any(item["status"] not in {429, 500, 502, 503, 504} for item in failures):
                raise SearchUnavailable("bulk item rejected; inspect index schema before replay")
            if attempt < 2:
                await asyncio.sleep(2**attempt)
        raise SearchUnavailable("bulk items exhausted retries; replay is safe")

    async def search(self, query: str, source: str | None, limit: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "size": limit,
            "query": {
                "bool": {
                    "must": [{"match": {"message": query}}],
                    "filter": [{"term": {"source": source}}] if source else [],
                }
            },
        }
        response = await self.request("POST", f"/{self.index}/_search", json=body)
        response.raise_for_status()
        return dict(response.json())

    async def ready(self) -> bool:
        response = await self.request("GET", "/_cluster/health", params={"timeout": "2s"})
        return response.is_success and response.json().get("status") in {"yellow", "green"}
