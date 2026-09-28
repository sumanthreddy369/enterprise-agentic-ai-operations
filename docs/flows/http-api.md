# HTTP API flow

## Startup and dependencies

`apps.api.main.create_app` creates settings, the async SQLAlchemy engine, session factory, HTTP client, OpenSearch client, and sealed log tool registry. Shutdown disposes the engine.

`/health` reports process liveness. `/ready` verifies Alembic revision `0001_foundation` and queries the incident table. It checks OpenSearch when `OPENSEARCH_REQUIRED=true`.

## Request boundary

`TrustedHostMiddleware` enforces `ALLOWED_HOSTS`. `RequestGuardrails` validates header size, query size, transfer encoding, content length, content type, body size, body read time, rate, concurrency, and handler time. It adds no-store, MIME, frame, referrer, and CSP headers.

The limiter uses the socket peer address. It ignores `X-Forwarded-For`. It is an in-memory fixed window and does not coordinate across workers. `/health` bypasses rate counting.

The request logger accepts an incoming ID only when it matches `[a-zA-Z0-9_-]{1,64}`. Otherwise it generates a UUID. Logs use route templates and exclude query strings.

## Authentication and incident operations

`security.auth.principal` compares bearer values with `secrets.compare_digest`. It returns `local-reader` or `local-writer`. These are local roles, not users, tenants, OAuth scopes, or Entra claims.

List limits are 1 to 200 with offsets from 0 to 100000. The source filter is exact. Get uses the internal incident UUID.

Create requires a writer and `Idempotency-Key`. The key hash includes identity. The request digest covers the validated body. Incident, idempotency, and audit rows commit together. Integrity races roll back and attempt one replay lookup.

Status: **Complete** for local create/list/get. Investigation, reports, approvals, WebSockets, and enterprise identity are **Planned**.
