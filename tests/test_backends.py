import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, text

from src.domain.contracts import AuthorizationContext, LogSearchQuery
from src.integrations.log_search import OpenSearchLogSearch
from src.integrations.opensearch import OpenSearch
from src.models.contracts import LogRecord
from src.models.database import ApplicationLog
from src.pipelines.load import load_silver
from src.pipelines.runner import process
from src.services.db import make_engine, session_factory

pytestmark = pytest.mark.integration


async def test_postgres_migration_and_replay(tmp_path: Path) -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    path = tmp_path / "synthetic.log"
    path.write_text(
        f"[Sun Dec 04 04:47:44 2005] [error] synthetic integration {uuid4()}\n",
        encoding="utf-8",
    )
    result = process("loghub-apache", path, tmp_path / "data", {"parser": "Apache"})
    engine = make_engine(url)
    factory = session_factory(engine)
    try:
        for _ in range(2):
            await load_silver(Path(result["silver_path"]), factory)
        async with factory() as database:
            count = await database.scalar(
                select(func.count())
                .select_from(ApplicationLog)
                .where(ApplicationLog.source_id == f"{result['sha256']}:1")
            )
            assert count == 1
            sql = await asyncio.to_thread(Path("infrastructure/analytics.sql").read_text)
            for statement in sql.split(";"):
                if statement.strip():
                    await database.execute(text(statement))
    finally:
        async with factory() as database, database.begin():
            await database.execute(
                delete(ApplicationLog).where(ApplicationLog.source_id == f"{result['sha256']}:1")
            )
        await engine.dispose()


async def test_real_opensearch_index_and_retrieve() -> None:
    url = os.environ.get("TEST_OPENSEARCH_URL")
    if not url:
        pytest.skip("TEST_OPENSEARCH_URL is not configured")
    index = f"ops-test-{uuid4().hex}"
    async with httpx.AsyncClient(base_url=url, timeout=15) as client:
        adapter = OpenSearch(client, index)
        try:
            assert await adapter.ready()
            await adapter.ensure_index()
            record = LogRecord(
                source="synthetic-test",
                source_id="1",
                source_record=1,
                source_file_sha256="0" * 64,
                message="synthetic outage",
                synthetic=True,
            )
            await adapter.index_logs([record])
            await adapter.index_logs([record])
            (await client.post(f"/{index}/_refresh")).raise_for_status()
            results = await adapter.search("outage", "synthetic-test", 10)
            assert results["hits"]["total"]["value"] == 1
            assert results["hits"]["hits"][0]["_source"]["synthetic"] is True
            context = AuthorizationContext(
                subject="integration-test",
                tenant_id="local",
                request_id="backend-test",
                permissions=frozenset({"logs:read"}),
                allowed_sources=frozenset({"synthetic-test"}),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            typed = await OpenSearchLogSearch(adapter).search(
                context, LogSearchQuery(query="outage")
            )
            assert typed.total == 1
            assert typed.matches[0].record == record

        finally:
            await client.delete(f"/{index}")
