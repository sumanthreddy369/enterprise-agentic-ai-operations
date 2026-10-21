# Runtime and CI flow

## Local runtime

`scripts/init_local.py` creates `.env` with SQLite configuration and random PostgreSQL/API secrets. It uses exclusive creation and never prints secret values.

`docker-compose.yml` defines PostgreSQL 16.6, OpenSearch 2.19.1, a one-shot Alembic service, the API and the deterministic incident worker. Backends must be healthy before dependents start. The API must pass `/ready`. The worker starts after migrations and polls SQL; it publishes no host ports and retries process failures at most three times through Compose.

Ports bind to loopback. OpenSearch disables its security plugin locally. Redis 7.4.2 and Qdrant 1.13.4 use the `future` profile and are not application dependencies.

## Image and CI

`infrastructure/Dockerfile` uses Python 3.11 slim, installs `uv==0.12.15`, syncs locked production dependencies, creates UID 10001, and runs Uvicorn as that user. It excludes tests and acquired data.

The quality job runs exposure, Ruff, MyPy, non-integration tests, a separate-process investigation smoke test, Alembic upgrade, and drift detection. The backend job starts PostgreSQL/OpenSearch, runs integration tests, builds the image, and checks API readiness. Cleanup always runs.

## Investigation process verification

Run `uv run python scripts/smoke_investigation.py`. It creates a temporary SQLite
database, migrates it, seeds an explicitly synthetic incident, and starts a real
Uvicorn process and a separate worker process. Random credentials are passed through
the environment and never printed. All child processes are stopped and temporary
data is removed on exit.

The check verifies unauthorized and reader submissions are rejected, idempotent
submission reuses the same run, reports preserve source identity and evidence
checksums, queued work completes after stopping and restarting the worker, and
cancelled runs publish no report. JSON output includes observed completion times
with worker startup and polling overhead. These single-run measurements are a smoke
check, not a throughput or model benchmark. This check does not kill a worker while
it holds a lease; the unit suite covers expired-lease reclaim and stale completion.

`tests/test_worker_backends.py` checks competing claims through independent
PostgreSQL connection pools, expired-lease reclaim and stale-result rejection.
The backend CI job includes it through `scripts/run_integration.py`.

After `docker compose up -d --build --wait api worker`, run
`uv run python scripts/smoke_compose.py`. This creates a uniquely identified,
explicitly synthetic incident in the local PostgreSQL database, submits it through
the container API, waits for the container worker and verifies report identity,
source and checksum. It removes only its own incident, investigation and audit
records. CI runs this check after starting both containers. Credentials come from
the ignored local `.env` and are never printed.

Container crash recovery, Azure runtime performance and GPU memory require their
own measurements. These checks exercise deterministic evidence collection; no
model-backed agent runtime is included.

Status: **Complete** for Compose and GitHub Actions. Kubernetes, Azure infrastructure, image publication, deployment environments, and rollback workflows do not exist.
