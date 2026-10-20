# Durable investigation submission flow

Status: **Complete** for SQL submission, lookup, revision-checked cancellation and
internal lifecycle transitions. A local SQL worker now executes deterministic
incident snapshot reports; Redis and model-backed agents remain future work.

```mermaid
flowchart TD
    API["Writer POST investigation"] --> Auth["Server-derived local authorization"]
    Auth --> Source["Existing source-scoped incident"]
    Source --> Insert["SQL insert with unique submission key"]
    Insert --> Replay{"Existing request digest matches?"}
    Replay -->|"no"| Conflict["409 conflict"]
    Replay -->|"yes"| Current["Return current durable snapshot"]
    Insert --> New["New run and audit in one transaction"]
    New --> Stored["Request stored; SQL worker claims expiring lease"]
    Stored --> Tool["Authorized incident.read tool"]
    Tool --> Report["Fenced atomic report completion"]
    Stored --> Recover["Expired lease: reclaim with new token"]
    Stored --> Cancel["Writer cancellation with expected revision"]
    Cancel --> CAS{"Atomic revision update succeeds?"}
    CAS -->|"no"| Conflict
    CAS -->|"yes"| Commit["Cancelled status and audit committed together"]
```

`apps/api/investigations.py` owns HTTP inputs and local-role authorization.
`src/services/investigations.py` owns SQL transactions and transition policy.
`src/models/database.py` and migration `0002_investigation_runs` own persistence.
`tests/test_investigations.py` covers replay races, transition races, pool recreation,
authorization, cancellation rollback and sanitized database failures; its integration
case runs the same lifecycle against PostgreSQL.

`src/services/worker.py` owns claims, retry bounds and fenced completion.
`src/services/incident_worker.py` supplies the deterministic read-only handler.
`tests/test_worker.py` tests competing claims, expired-lease reclaim, stale result
rejection, cancellation, report persistence and handler failure exhaustion locally.
The worker returns evidence only, without asserting a cause or proposing an action.

Read the [Phase C contract and limits](../phase-c.md) before changing this boundary.
