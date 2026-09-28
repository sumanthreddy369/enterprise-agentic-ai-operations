# Verification history

## Phase B — 2026-09-27

Implementation commit `e302a74`: 64 local tests passed and 2 backend tests skipped without configured local services. Ruff lint/format, MyPy (35 source files), tracked-file exposure checks and live HTTP smoke checks passed. [GitHub CI](https://github.com/sumanthreddy369/enterprise-agentic-ai-operations/actions/runs/36365649081) passed quality, real PostgreSQL/OpenSearch integration (including the typed adapter), image build and container smoke checks. These are recorded implementation results, not a new runtime test during the documentation refresh.

## Milestone 1 verification

Verified locally on 2026-09-25, Windows, Python 3.11.9, uv 0.12.15. These are observed outcomes, not planned test results.

| Check | Result |
| --- | --- |
| Unit/API/security suite: `uv run pytest -q` | **41 passed, 2 skipped**. Skips are the real PostgreSQL/OpenSearch tests without service configuration. |
| MyPy: `uv run mypy src apps` | Passed. Strict checking; PyArrow's untyped third-party calls are explicitly excluded. |
| Ruff lint and format checks | Passed after final formatting. |
| Alembic upgrade + schema drift check | Passed on SQLite; no new upgrade operations detected. |
| Actual Uvicorn HTTP smoke test | Passed: liveness, readiness, unauthenticated 401, authenticated incident list, request ID and OpenAPI. Test server is terminated after checks. |
| Compose configuration | Passed `docker compose config --quiet`. |
| Real public acquisition | Both BPI releases and five pinned Loghub samples downloaded and checksummed. Fresh BPI 2013 acquisition also passed the new egress/redirect controls. |
| Real subset load and replay | Repeated ingestion retained exactly 200 incidents, 1,868 events and 500 log records in the local database. |
| Tracked-file exposure check | Passed. Narrow pattern/filename/size checks; not a comprehensive secret scan. |
| Local container runtime | **Blocked:** Docker Desktop crashes while initializing its local `sailor-ingest.sock` socket; Linux engine pipe is unavailable. No reset/deletion of Docker data performed. |
| Local PostgreSQL/OpenSearch runtime | Not claimed passed. Requires a working Docker engine or separately configured services. |
| GitHub Actions | **Passed** for implementation commit `1bc71e0`: quality checks, 41 unit/API/security tests, 2 real PostgreSQL/OpenSearch integration tests, PostgreSQL SQL analytics, API image build and container readiness. [Verified run](https://github.com/sumanthreddy369/enterprise-agentic-ai-operations/actions/runs/36153715653). |

The successful Linux CI run validates real PostgreSQL/OpenSearch and container execution. The local Windows Docker startup issue remains an environment limitation; it does not represent a failed backend test.

## Full acquired-file validation

`uv run ops-data all --full` validated the complete files acquired for this milestone. Loghub acquisition uses the publisher's 2,000-line samples, not the large archives.

| Dataset | Accepted incidents | Accepted events | Accepted log lines | Quarantined source records |
| --- | ---: | ---: | ---: | ---: |
| BPI 2013 | 7,554 | 65,533 | 0 | 0 |
| BPI 2014 | 46,606 | 0 | 0 | 203 |
| Loghub Apache | 0 | 0 | 2,000 | 0 |
| Loghub OpenStack | 0 | 0 | 2,000 | 0 |
| Loghub BGL | 0 | 0 | 2,000 | 0 |
| Loghub HDFS | 0 | 0 | 2,000 | 0 |
| Loghub Zookeeper | 0 | 0 | 2,000 | 0 |

BPI 2014 has 46,809 source rows, of which 203 lack an incident ID. They are preserved in Bronze and quarantined instead of receiving fabricated identifiers. Default timezone-naive values remain null with original strings retained. This is intentional, not inferred UTC.

Full source validation generated local Parquet and manifests; only the small subset was loaded into the local database. Large Loghub archives were not downloaded. No production connector credentials, LLM calls, retrieval-quality claims, remediation execution, or enterprise deployment tests were involved.

## Reproduce

```sh
uv sync --frozen --python 3.11
uv run python scripts/init_local.py
uv run alembic upgrade head
uv run ops-data all --limit 100 --load
uv run ops-data all --limit 100 --load
uv run python scripts/smoke_api.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src apps
uv run alembic check
```

With a working Docker engine, run `docker compose up -d --build --wait` and `uv run python scripts/run_integration.py`. The repository's CI automates that backend check on Linux.

## Delivery boundary

Milestone 1 plus the requested foundation guardrails and technology plan. Agent/RAG/enterprise-identity controls are documented as later gates in [guardrails.md](guardrails.md); they are not described as implemented. Phase B has since delivered typed interfaces and the tool registry; Phase C durable infrastructure is next.
