# Technology decisions and milestone plan

This document retains technology decisions and the original milestone history. The [enterprise target architecture and Phase A–M plan](target-architecture.md) is now the governing roadmap, including Azure, LiteLLM, pgvector, A2A, DeepEval and the React dashboard. **Milestone 1 and Phase B interfaces are delivered. Phase C is next.** The M1�M4 sections below retain the original grouping; the Phase A�M roadmap governs current execution. See [Phase B](phase-b.md) for the implemented tool boundary.

## What fits and where

| Technology | Decision | Purpose and delivery phase |
| --- | --- | --- |
| Python 3.11+, advanced typing, Pydantic v2 | Use now | Validated source contracts, API models, typed service boundaries; typed agent state in M3. |
| asyncio and httpx | Use now | Async API/database/search I/O, bounded HTTP timeouts, nonblocking pipeline invocation. Bounded concurrent enterprise extraction in M2. |
| Pandas 2.x | Use now | Explicit timezone localization and validation. |
| Polars and PyArrow | Use now | Lazy analytical transformations and batched compressed Parquet; avoid loading large source files into Pandas unnecessarily. |
| PostgreSQL 16, SQLAlchemy 2.x, Alembic | Use now | Source-scoped operational warehouse, transactional upserts, pooled async connections, versioned schema. PostgreSQL 17 compatibility is a later CI matrix expansion. |
| asyncpg / psycopg 3.x | asyncpg now; psycopg conditional | asyncpg is the selected async PostgreSQL driver. Introduce psycopg 3 only if measured COPY/bulk-ingestion requirements justify replacing or supplementing it. No duplicate connectivity layer without a use case. |
| CTEs and window functions | Use in foundation analytics | Source-scoped event sequencing and activity trends; no cross-dataset incident joins. |
| Structured JSON logs, request IDs, Tenacity | Use now | Request and pipeline diagnostics, retryable extraction transport failures. OpenSearch has bounded HTTP/item retries and a circuit breaker. |
| Schema evolution | Version from M1 | Alembic for relational changes; parser version in run identity; preserve Bronze; reject incompatible source headers; replay after changing parser version. Automated source drift approval follows in M2. |
| Redis | Optional Compose profile now; M2 functionality | Durable-job coordination/caching only when introduced with a worker, explicit TTLs and recovery semantics. Not an authoritative incident store. |
| Hourly/daily ETL | M2 | External scheduler invokes an idempotent CLI/job with watermarks, overlap prevention, bounded retries and dead-letter handling. Do not schedule historical benchmark data as if it were a live feed. |
| Futures / concurrent extraction | M2, where needed | Prefer asyncio TaskGroup plus semaphore for network I/O. Use `asyncio.to_thread` for blocking libraries. ProcessPoolExecutor only for measured CPU-bound local work. |
| Ray | Deferred, measurement-gated | Consider distributed embedding/document processing once one-machine throughput or memory is inadequate. Benchmark against local batching first; not needed for 2,000-line samples. |
| MSAL / OAuth 2.0 | M2 | Microsoft Graph app authentication, scoped token acquisition/cache, credential rotation, least-privilege access. ServiceNow and Splunk use supported enterprise auth flows. |
| Docling / Unstructured | Docling first in M2; Unstructured adapter if required | Parse approved documentation with page/section provenance and ACL metadata. Evaluate actual formats before installing both. Neither is needed to parse current CSV/XES/log inputs. |
| Qdrant / HNSW | Primary vector store in M2 | BGE dense embeddings with payload filters. Tune HNSW construction/search parameters against latency, recall and memory; retain exact-search baseline. |
| Milvus | Optional alternative in a later milestone | Implement the same retrieval interface and conformance tests only when a deployment requires it. No second always-on vector service in M1. |
| BM25 | OpenSearch keyword search in M1; document retrieval in M2 | Preserve exact error codes and technical identifiers. Use explicit document ACL/source filters. |
| Hybrid retrieval + Reciprocal Rank Fusion | M2 | Retrieve dense and BM25 candidates, fuse by stable document/chunk ID with RRF, deduplicate, then rerank. Never combine incomparable raw scores by naive addition. |
| BGE reranker | M2 | Cross-encoder reranking of a bounded candidate set, with explicit model revision/license, timeout, batch size and fallback to fused ranking. |
| ONNX + ONNX Runtime | Optional M2 inference backend | Export approved embedding/reranker models to ONNX; benchmark ONNX Runtime against the PyTorch baseline. ONNX is the model format, not an execution engine. |
| OpenVINO | Optional M2 Intel-targeted backend | Benchmark on the actual Intel deployment hardware, using either the direct Sentence Transformers backend or ONNX Runtime's OpenVINO provider. Export/device compatibility must be verified for each model. |
| NDCG and MRR | M2 acceptance tests | Human-labeled relevance judgments; nDCG@10, MRR@10, Recall@k, latency and memory. Compare BM25, dense, fused and reranked retrieval with a held-out query set. No invented performance numbers. |
| LangGraph and ReAct agents | M3, after data/retrieval gates pass | Typed checkpointed state, bounded parallel investigations, read-only allowlisted tools, structured evidence-linked outputs. ReAct only where iterative tool selection adds value. |
| MCP | M3 | Typed read-only investigation tools, bounded results, auth context and audit spans. |
| Langfuse + OpenTelemetry | M3 | Optional local-development tracing; agent/tool spans, token and cost accounting with configured model prices, redaction and sampling. No tokens/costs fabricated for deterministic M1 pipelines. |
| Human approval and predefined remediation | M4 | Immutable action proposal/version, incident/run/action binding, named approver and time, RBAC, execution timeout and rollback. Automatic action execution disabled by default. |

## Milestone gates

### M1 — Enterprise data foundation (current)

Deliver reproducible acquisition for both BPI incident datasets and five Loghub samples, immutable Bronze, validated Silver, analytical Gold, PostgreSQL schema/migrations, OpenSearch indexing/search, initial authenticated incident API, tests/static checks, container definitions, CI, README and a factual verification report. Keep unrelated sources independent. The original delivery stopped here as requested. Further development follows the Phase A–M plan.

### M2 — Live extraction and evaluated retrieval (next)

1. Define async connector protocols and equivalent mock/real ServiceNow, Splunk and Graph implementations.
2. Add MSAL/OAuth, pagination, Retry-After support, incremental watermarks, extraction concurrency and recoverable hourly/daily jobs.
3. Ingest authorized operational documents through Docling, preserving source version, chunk coordinates and ACLs.
4. Build BGE/Qdrant HNSW and OpenSearch BM25 indexes; implement RRF and bounded BGE reranking behind a retrieval interface.
5. Publish the evaluation dataset provenance and results for nDCG@10/MRR@10/Recall@k and p95 latency. Set release thresholds from a measured baseline.
6. Benchmark PyTorch, ONNX Runtime and OpenVINO for embedding/reranker inference using the [inference optimization plan](inference-optimization.md). Promote a backend only after quality, latency, memory and compatibility gates pass.
7. Benchmark throughput before deciding on Ray, Milvus, Unstructured or a psycopg COPY path.

### M3 — Evidence-grounded multi-agent investigations

Implement the five primary specialist workers in the governing architecture, retaining the original nine-agent brief as worker skills and review stages, using LangGraph, conditional routes, durable checkpointing, bounded concurrency and no unnecessary LLM calls. Expose investigation, evidence and report APIs. Every hypothesis references evidence and states uncertainty. Add Langfuse/OpenTelemetry and MCP tool instrumentation.

### M4 — Approval-controlled actions and operational hardening

Implement proposal approval/rejection, identity-bound audit records, allowlisted handlers, timeout/rollback tests, deployment secrets/TLS, authorization isolation, backup/restore and load testing. No arbitrary model-generated shell execution.

## Sources informing the plan

- [Qdrant hybrid query and fusion API](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Sentence Transformers retrieval evaluation](https://www.sbert.net/docs/package_reference/sentence_transformer/evaluation.html)
- [Sentence Transformers reranking evaluation](https://www.sbert.net/docs/package_reference/cross_encoder/evaluation.html)
- [Ray task execution model](https://docs.ray.io/en/latest/ray-core/tasks.html)

These references guide planned implementation; presence in this document does not mean the dependency or feature is installed.
