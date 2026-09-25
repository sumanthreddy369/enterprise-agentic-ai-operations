"""Generate ignored local development credentials. Never print secrets."""

import secrets
from pathlib import Path

destination = Path(".env")
with destination.open("x", encoding="utf-8") as handle:
    handle.write("DATABASE_URL=sqlite+aiosqlite:///./operations.db\n")
    handle.write("OPENSEARCH_URL=http://localhost:19200\nOPENSEARCH_REQUIRED=false\n")
    for name in ["POSTGRES_PASSWORD", "API_READ_KEY", "API_WRITE_KEY"]:
        handle.write(f"{name}={secrets.token_hex(32)}\n")
print("Created ignored .env with random local credentials.")
