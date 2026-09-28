# Agent instructions

## Project overview

This is a Python 3.11 FastAPI and data-pipeline repository. The implemented scope is public dataset acquisition, Bronze/Silver/Gold processing, SQL persistence, incident APIs, OpenSearch log search, and a typed read-only tool boundary. Agent, MCP, RAG, dashboard, enterprise identity, approval execution, and Azure runtime work are planned or stubbed.

## Structure map

```text
apps/api/                  # FastAPI application and routes
data/dataset_manifest.json # Source metadata and checksums
docs/                      # Architecture, flows, status, datasets, security
infrastructure/            # Dockerfile, SQL, Alembic migrations
scripts/                   # Setup, verification, research helpers
src/domain/                # Frozen Pydantic domain contracts
src/ingestion/             # CLI and bounded acquisition
src/integrations/          # OpenSearch and typed adapter
src/models/                # Pydantic records and SQLAlchemy schema
src/pipelines/             # Parsers, normalization, products, loading
src/security/              # Auth, policy, egress, ASGI guardrails
src/services/              # Settings, ports, tools, database helpers
tests/                     # Unit, API, security, integration tests
```

Placeholder directories are `src/agents`, `src/mcp`, `src/orchestration`, `src/rag`, `apps/dashboard`, and `notebooks`.

## Build and verification

```sh
uv sync --frozen --python 3.11
uv run python scripts/check_repository.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src apps
uv run pytest -q
uv run alembic upgrade head
uv run alembic check
```

Real backend verification:

```sh
uv run python scripts/init_local.py
docker compose up -d --wait postgres opensearch
uv run python scripts/run_integration.py
```

## Code conventions

- Use Python 3.11 syntax and strict MyPy-compatible annotations.
- Keep Ruff line length at 100 and rules `E`, `F`, `I`, `UP`, `B`, and `ASYNC`.
- Use Pydantic v2 models with forbidden extra fields at trust boundaries.
- Use timezone-aware UTC values. Reject naive persisted timestamps.
- Keep source identity as `(source, source_id)`. Do not join independent datasets by similar IDs or times.
- Preserve source checksum, record, parser version, limit, and timezone policy.
- Bound async HTTP and database work with timeouts, retries, batches, and result limits.
- Log fixed metadata. Exclude authorization headers, request bodies, source payloads, and unsafe exception text.
- Treat SQLite as local/test support and PostgreSQL as deployment database semantics.
- Add Alembic revisions for ORM schema changes and run `alembic check`.
- Mark synthetic fixtures with `synthetic=True`.

## Do

- Read `README.md`, `docs/target-architecture.md`, and the relevant flow document before changing a boundary.
- Keep implemented, partial, stubbed, and planned status claims distinct.
- Test validation, replay, authorization, cancellation, and backend failure behavior.
- Preserve Bronze immutability and checksum gates.
- Route read-only tools through `ToolRegistry`; construct authorization context on the server.
- Inspect staged changes and run `scripts/check_repository.py` before committing.

## Don't

- Do not claim a protocol, table, interface, Compose declaration, or placeholder is a working feature.
- Do not add consequential tools to the read-only registry. Approval-controlled execution is not implemented.
- Do not accept tenant, permission, or identity claims from request headers.
- Do not fabricate incident relationships, root causes, resolutions, metrics, costs, or deployment results.
- Do not commit `.env`, raw data, Parquet, local databases, credentials, model weights, or research downloads.
- Do not expose the local OpenSearch configuration publicly; its Compose security plugin is disabled.
- Do not move or reorganize folders without owner approval. Put proposals in `docs/restructure-proposal.md`.
