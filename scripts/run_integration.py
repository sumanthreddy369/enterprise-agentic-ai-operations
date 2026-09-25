"""Run migrated PostgreSQL/OpenSearch tests against the local Compose services."""

import os
import subprocess
import sys

from dotenv import dotenv_values

values = dotenv_values(".env")
password = values.get("POSTGRES_PASSWORD")
if not password:
    raise SystemExit("Generate .env with scripts/init_local.py first")
url = f"postgresql+asyncpg://ops:{password}@localhost:55432/operations"
environment = {
    **os.environ,
    "DATABASE_URL": url,
    "TEST_DATABASE_URL": url,
    "TEST_OPENSEARCH_URL": "http://localhost:19200",
}
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=environment, check=True)
subprocess.run([sys.executable, "-m", "alembic", "check"], env=environment, check=True)
subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "-m", "integration"], env=environment, check=True
)
