# Investigation worker runtime verification

On October 21, 2026, the local runtime completed an investigation through separate
API and worker containers backed by PostgreSQL. The report retained the incident's
source identity and its excerpt matched the stored SHA-256 checksum. The fixture
was explicitly synthetic and removed after verification.

| Check | Observed result |
| --- | --- |
| Local non-integration suite | 76 passed |
| PostgreSQL/OpenSearch integration suite | 6 passed |
| Alembic PostgreSQL upgrade and drift check | Revision 0003; no new operations |
| Independent PostgreSQL worker pools | One claim won; stale completion rejected after reclaim |
| Separate API/worker processes with SQLite | Authorization, replay, restart queue and cancellation passed |
| API and worker containers with PostgreSQL | Report and source/checksum checks passed |
| Ruff, formatting, MyPy and tracked-file exposure checks | Passed |

The SQLite smoke run observed 1,052.98 ms to completion after worker launch and
1,060.55 ms after restart. The container smoke run observed 967.30 ms from
submission to report. These are individual synthetic observations with startup or
polling overhead, not comparable latency benchmarks or service-level guarantees.
They establish execution of the current deterministic incident snapshot handler.

The PostgreSQL worker test uses separate connection pools and deliberately expires
a lease. It does not terminate a container during a leased job. The separate-process
test stops a worker between jobs, queues work, restarts the process and verifies
completion. Neither test establishes recovery from every failure mode.

Reproduce with:

```sh
uv run python scripts/smoke_investigation.py
docker compose up -d --build --wait api worker
uv run python scripts/run_integration.py
uv run python scripts/smoke_compose.py
```

Create the ignored `.env` first with `scripts/init_local.py` if it does not exist.
On Linux, configure `vm.max_map_count=262144` for OpenSearch. Published ports bind
to loopback. The worker's Compose restart policy permits three process retries.

Azure deployment, model-backed reasoning, load benchmarks, GPU memory measurements
and enterprise identity are outside this evidence. The application still rejects
production configuration until its identity and deployment requirements are met.
