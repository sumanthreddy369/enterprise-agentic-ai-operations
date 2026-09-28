# Phase B: typed boundaries and read-only tools

Phase B adds Pydantic domain contracts and asynchronous service protocols for incidents, investigations, retrieval, model access, embeddings and reranking. These are contracts, not live enterprise or model integrations. Evidence-linked reports reject missing citation IDs; model usage remains unknown unless reported.

The existing log API now calls a sealed tool registry and the typed OpenSearch adapter. The registry validates input and output, checks server-derived permissions before execution and before returning results, limits concurrent calls, applies deadlines, propagates cancellation, caps serialized output and sanitizes dependency failures. Consequential tools cannot be registered; an approved executor is future work. Trusted handlers must cooperate with asyncio cancellation; registration metadata is not a sandbox for arbitrary code.

Authorization contexts come from authenticated local roles, never client-supplied identity or tenant headers. The current benchmark index only supports the local namespace and five configured Loghub sources. The adapter applies source filters upstream and checks returned records again. This is not enterprise tenant isolation or Entra authentication. Production remains gated.

`GET /api/v1/logs` preserves the `hits.total` and `hits.hits` envelope, including document IDs, scores and source records. Raw backend diagnostics are omitted. Unauthorized sources return 403; invalid input returns 422; dependency or invalid-output failures return 503; deadlines return 504. Saturation returns 503 with Retry-After. Logs record tool name, request ID, outcome and duration without arguments or result content. These logs are not a durable audit ledger or OpenTelemetry spans.

Tests cover domain validation, denied/expired access, malformed outputs, timeouts, cancellation, saturation, source filtering and the real API dispatch path. Synthetic fixtures and mocked HTTP are explicitly test-only. The backend CI suite additionally exercises the typed adapter against real OpenSearch; local backend tests require configured services.

Next: Phase C implements durable investigation infrastructure. LangGraph, MCP, model providers, RAG, Redis coordination, human approvals and Azure deployment are not implemented by this step.
