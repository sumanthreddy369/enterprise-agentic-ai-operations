# Runtime and CI flow

## Local runtime

`scripts/init_local.py` creates `.env` with SQLite configuration and random PostgreSQL/API secrets. It uses exclusive creation and never prints secret values.

`docker-compose.yml` defines PostgreSQL 16.6, OpenSearch 2.19.1, a one-shot Alembic service, and the API image. Backends must be healthy before dependents start. The API must pass `/ready`.

Ports bind to loopback. OpenSearch disables its security plugin locally. Redis 7.4.2 and Qdrant 1.13.4 use the `future` profile and are not application dependencies.

## Image and CI

`infrastructure/Dockerfile` uses Python 3.11 slim, installs `uv==0.12.15`, syncs locked production dependencies, creates UID 10001, and runs Uvicorn as that user. It excludes tests and acquired data.

The quality job runs exposure, Ruff, MyPy, non-integration tests, Alembic upgrade, and drift detection. The backend job starts PostgreSQL/OpenSearch, runs integration tests, builds the image, and checks API readiness. Cleanup always runs.

Status: **Complete** for Compose and GitHub Actions. Kubernetes, Azure infrastructure, image publication, deployment environments, and rollback workflows do not exist.
