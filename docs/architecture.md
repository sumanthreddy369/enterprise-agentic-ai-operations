# Architecture decisions

## 001 — Establish evidence before agents

Milestone 1 contains no LangGraph/LLM code. Typed, source-preserving datasets and repeatable ingestion must be demonstrated first. Schemas for future investigation/evidence/approval entities are migrations only, not functioning workflows. See the technology plan for implementation gates.

## 002 — Preserve source boundaries and time uncertainty

The relational uniqueness boundary is `(source, source_id)`. Stable internal IDs are derived from this pair. Independent benchmark sources never acquire inferred foreign keys. Log IDs use file digest plus original line ordinal because the sources do not provide stable enterprise event IDs. Repeated log messages remain separate observations.

BPI 2013 trace IDs and event ordinal are retained; event-derived opening time is marked as first observed. BPI 2014 headers are read from the actual semicolon file; trailing unnamed fields are retained positionally. Source attributes are stored with normalized values. No incident description, resolution narrative, service identity or change relationship is invented.

Offset-bearing timestamps normalize to UTC. Naive timestamps remain unknown unless an explicit timezone assumption is recorded. BGL Unix epoch seconds supply UTC independently of its local time string. API timestamp inputs require offsets.

## 003 — Replay is the recovery mechanism

Acquisition enforces HTTPS, bounded download size, pinned checksum, atomic file promotion and refusal to replace an unexpected raw file. Bronze is content-addressed and immutable. Run identity includes pipeline version and normalization options. Completed output checksums are verified before reuse; incomplete outputs are rebuilt under a dataset file lock.

Database batches and audit/idempotency API writes use transactions. SQL and OpenSearch cannot share a local transaction. Deterministic upserts/index IDs make a failed load safe to replay; there is no exactly-once distributed processing claim. Operators must replay until both sinks finish. A future durable outbox can improve this boundary for live feeds.

## 004 — Separate tabular and search responsibilities

PostgreSQL stores operational records and relations. OpenSearch indexes text with fixed mappings and source filters; arbitrary source attributes are retained but not dynamically indexed. PyArrow writes Silver in batches; Polars constructs Gold analytics. Pandas is used specifically for timezone localization. Very large production ingestion remains subject to capacity testing.

Qdrant will own semantic vectors in M2. BM25 and dense retrieval will use the same document/chunk IDs before RRF/reranking. Milvus is an optional future adapter, not an additional M1 service dependency.

## 005 — Explicit local security boundary

Local development uses randomly generated bearer keys with reader/writer roles. The source namespace and audit actor come from the authenticated principal, not caller-supplied identity. This does not implement enterprise OIDC, multi-tenancy or fine-grained document ACLs. Production promotion requires those controls plus TLS, managed secrets, retention and rate limiting.

No code path executes remediation or model-generated commands. Approval tables are preparatory. Future approval will bind a named identity to an immutable version of a proposed action; an executor will accept predefined allowlisted actions only.

## 006 — Test contracts and real boundaries separately

SQLite tests exercise actual Alembic migrations, API authentication, RBAC, validation, replay, audit writes and pipeline behavior. HTTP mock tests cover request bodies, retries and OpenSearch failures. Dedicated PostgreSQL/OpenSearch tests and container smoke tests run against real services in CI. A skipped backend test must never be described as passed. The verification report records which environment actually ran each check.

## 007 — Evolve without rewriting provenance

Relational changes receive a new Alembic revision. Parser changes increment `PIPELINE_VERSION`, producing a new versioned run while leaving Bronze intact. A checksum/source-schema change requires maintainer review of the manifest and source-specific parser. Unknown statuses/severities remain explicit `unknown`, not arbitrary mappings. Automated drift approval and incremental watermarks are M2 work.
