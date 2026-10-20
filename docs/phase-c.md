# Phase C: durable investigation infrastructure

Status: **Partial**. The first step implements SQL-backed submission, lookup and
cancellation. PostgreSQL is authoritative; SQLite remains local/test support.
The local SQL polling worker now claims requests and produces deterministic incident
evidence reports through the read-only tool registry. Redis coordination, model-backed
agent execution and approval execution remain outside this implementation.
A 202 response acknowledges persistence, not completion.

## HTTP contract

- `POST /api/v1/investigations` requires the writer role and `Idempotency-Key`.
  Body: `{"incident":{"source":"bpi-2013","source_id":"existing-source-id"},"question":"What happened?"}`.
  Returns a snapshot with run ID, local tenant, source reference, status and revision.
- `GET /api/v1/investigations/{run_id}` accepts reader or writer roles.
- `POST /api/v1/investigations/{run_id}/cancel` requires the writer role and
  `{"expected_revision":0}`. Stale revisions and terminal-state transitions return 409.

The server assigns the local authorization context. Only BPI 2013, BPI 2014 and
`api:local-writer` incident sources are enabled at this boundary. Client identity,
tenant and permission claims are not accepted. These shared local roles provide
no per-user ownership or enterprise tenancy; the production gate remains closed.

## Persistence and transitions

`src/services/investigations.py` implements the Phase B repository protocol.
Submission hashes a structured tuple of tenant, authenticated subject and key.
A unique SQL index arbitrates concurrent submissions. The validated request digest
must match on replay. The question is persisted, but is excluded from logs and audit
details. SQL commits the run and audit event together. Replays return the current
snapshot and do not add another creation audit event.

Transitions compare tenant, source identity, status and expected revision. An atomic
SQL update increments the revision and commits an audit event in the same transaction.
The initial API status is `pending`. Supported transitions are `pending` to
`running` or `cancelled`, and `running` to `failed` or `cancelled`.
Running/failed transitions require an internal permission never issued by the API.
Completed and awaiting-approval transitions are unavailable until their actual
workflows exist. There is no arbitrary HTTP status-update endpoint.

Each repository operation has a ten-second deadline. Task cancellation propagates
and uncommitted changes roll back. SQL failures and deadlines return a sanitized
503. A lost response after commit has an uncertain client outcome: retry submission
with the same key or GET the run before retrying a cancellation. No automatic
retry of a potentially committed transition is performed.

Migration `0002_investigation_runs` is additive. Existing placeholder rows receive
the local tenant and revision zero; nullable submission metadata preserves them.
Such rows are excluded from the new repository rather than inventing requests.
Readiness now requires this revision. No dataset rows or approval history are changed.

## Remaining Phase C work

Extend worker verification to real PostgreSQL and process crashes. Consider Redis
wakeups only if SQL polling latency or load justifies them. No Redis-loss test is
claimed because application code does not use Redis. Agent outcomes remain Phase F.

## Local evidence worker

Migration `0003_worker_leases` adds attempt counters, expiring lease tokens and
report storage. Run `uv run alembic upgrade head`, then
`uv run python -m src.services.incident_worker` in a separate terminal.
The API does not automatically launch a worker.

The worker polls SQL once per second, handles one run at a time, and gives a handler
58 seconds within a 60-second lease. Atomic revision-and-token checks fence stale
completion after cancellation or reclaim. Expired leases are eligible for another
attempt; after three claims, the next poll marks an exhausted run failed.
SQL polling resumes after bounded database failures. No Redis dependency is used.
Workers rely on synchronized host clocks for lease expiry; no heartbeat extends
long-running work. Cancellation prevents publication immediately but an already
running read-only handler may continue until its deadline.

`GET /api/v1/investigations/{run_id}/report` uses the same local source authorization
as lookup. It returns 409 until a completed report exists. The worker's initial
handler calls `incident.read` through `ToolRegistry` and records a hashed, source-linked
snapshot of title and status. It deliberately emits no root-cause hypotheses.
It does not yet answer the user's investigation question or retrieve event history.

Next work: live PostgreSQL worker verification, process-level crash tests,
incident-history and log tools, model-backed investigation and evaluated citations.
The earlier lifecycle description above documents the submission-only API;
worker completion and retry transitions now use the separately fenced worker path.

## Verification on October 20, 2026

The complete local suite passed: **76 passed, 5 integration tests deselected**.
Ruff passed, MyPy passed across 39 source files, and SQLite migrations upgraded
through `0003_worker_leases` with no schema drift reported by `alembic check`.
Worker tests use synthetic incidents and simulate restart by recreating connections
and expiring a lease; they do not kill a live worker process.
Docker was stopped, so this run does not establish PostgreSQL or Azure worker
execution. Azure Blob dataset storage is independent of this local worker.
