# Authorized log-search flow

`GET /api/v1/logs` validates query, source, and limit, authenticates a local role, and creates `AuthorizationContext` on the server. The context lasts five minutes, includes `logs:read`, uses tenant `local`, and allows five Loghub sources.

`services.logs.log_registry` registers `logs.search` and seals the registry. The registry refuses write-capable descriptors. It validates typed input and a fresh copy of output, caps serialized output, limits concurrency, applies a deadline, preserves cancellation, and sanitizes dependency exceptions.

Authorization runs before invocation and before output release. Expired results are not returned. Tool logs exclude arguments, results, credentials, and exception strings.

`OpenSearchLogSearch` rejects non-local tenants and unauthorized sources. It sends filters upstream and validates returned records again. Partial shards, timeouts, malformed hits, excess hits, inconsistent totals, and invalid records fail closed.

`OpenSearch` performs message match plus exact source filters. Requests retry 429 and server failures three times. A per-client breaker opens for 30 seconds after three exhausted requests.

Status: **Complete** for OpenSearch keyword search. Dense vectors, hybrid fusion, reranking, document ACLs, and enterprise tenant isolation are **Planned**.
