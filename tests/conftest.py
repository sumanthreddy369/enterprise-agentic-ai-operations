import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from apps.api.main import create_app
from src.services.settings import Settings


@pytest.fixture
def migrated_url(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
async def client(migrated_url: str) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        Settings(
            _env_file=None,
            allowed_hosts=["test"],
            database_url=migrated_url,
            api_read_key=SecretStr("test-reader"),
            api_write_key=SecretStr("test-writer"),
            opensearch_required=False,
        )
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client
