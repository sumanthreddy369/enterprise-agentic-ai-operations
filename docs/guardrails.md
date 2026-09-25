# Guardrails: implementation, evidence and deployment gates

This project demonstrates layered controls used in enterprise engineering. There is no universal checklist that makes every system secure. **Implemented** below means there is an enforcement point in this repository; **planned** means a release requirement for a later capability. This is not a certification or a claim of complete OWASP coverage.

## Enforced in Milestone 1

| Control | Enforcement point | Evidence / boundary |
| --- | --- | --- |
| Authentication fails closed | `src/security/auth.py` | Missing/invalid bearer credentials return 401. No anonymous incident/log access. |
| Least-privilege local roles | Reader versus writer dependency | Reader writes return 403; read and write keys cannot be identical. Shared local keys do not represent named enterprise users. |
| Strict input contracts | Pydantic models, `extra=forbid` | Unknown fields, invalid enums, oversized titles and timezone-naive API timestamps fail validation. |
| Source impersonation prevention | API assigns source from authenticated role | Clients cannot submit a benchmark source or actor identity. Sources are provenance boundaries, **not tenant security boundaries**. |
| Bounded query/results | API query validation | Pagination and search sizes are capped; user input becomes typed SQL parameters/OpenSearch match queries, not raw SQL/DSL. |
| Host-header allowlist | `TrustedHostMiddleware` | Unexpected hosts return 400. Wildcard configuration is refused. |
| Body/header/query limits | `RequestGuardrails` ASGI middleware | 64 KiB default body cap, including chunked transfer; 16 KiB header cap; 4 KiB query-string cap. |
| Content handling | Request middleware | Write requests require JSON. Compressed HTTP request bodies are refused; duplicate Content-Length is rejected. |
| Rate and concurrency controls | Request middleware | Default 120 requests/minute/peer, 32 concurrent requests and bounded client counter storage. Limits are per process, not distributed quotas. |
| Time budgets | Request middleware, httpx | Default body receipt 5 seconds; handler 30 seconds; HTTP dependency timeouts and bounded retries. A timeout after a commit requires idempotent reconciliation, not a claim that nothing happened. |
| Proxy identity safety | Shipped Uvicorn commands disable proxy headers | Forwarded headers cannot change limiter identity in this local configuration. A trusted production proxy needs deliberate configuration. |
| Safe browser response defaults | Response middleware | `no-store`, `nosniff`, deny framing, no referrer; CSP blocks framing/base replacement. This is not a complete browser CSP. No permissive CORS configuration. |
| Error and log minimization | Validation handler / JSON event logging | API errors omit raw submitted input and validation context; DB/search failures return generic messages. Logs omit bodies, authorization values and search queries. Route templates avoid logging incident IDs. |
| Correlation | Validated request IDs / pipeline run IDs | Invalid caller IDs are replaced. Guardrail denials log a category/status without source payloads. |
| Replay protection | Idempotency records, unique source keys, transactions | Same key/body returns original incident; changed body returns 409; API creation and audit record commit together. |
| Audit trail | `audit_events` | Writer action and local identity recorded. This is an application audit record, not immutable/WORM storage or enterprise nonrepudiation. |
| Download egress policy | `src/security/egress.py` | Exact HTTPS provider allowlist, credential/port checks, every redirect revalidated and redirect count bounded. Arbitrary URL ingestion is not exposed by the API. |
| Download integrity and budgets | Acquisition module | Pinned SHA-256, maximum bytes, transport retries, read timeout and streaming time budget; partial files never promoted as successful downloads. |
| Path controls | Dataset/filename validation | Dataset keys and acquired filenames cannot contain traversal/separator syntax. CLI input/root paths remain a trusted operator boundary. |
| Untrusted XML handling | DefusedXML parser | External entities/DTD entity expansion rejected; no automatic archive extraction. Large local XML still requires capacity limits/isolated ingestion. |
| Provenance and data quality | Bronze/Silver/Gold contracts | Original bytes and identifiers retained; malformed records quarantined; source-specific status/severity normalization; unknown timezones stay explicit. |
| UTC and DST safety | Timestamp normalizer + database UTC type | Offset-preserving database round trips; ambiguous/nonexistent explicitly localized times rejected. |
| Recovery and sink isolation | Run manifests, SQL batches, OpenSearch IDs | Corrupt outputs rebuild; corrupt Bronze fails closed; database/index replay repairs partial sink progress. No distributed exactly-once claim. |
| Search failure containment | OpenSearch adapter | Explicit schema, deterministic IDs, bounded bulk retries, permanent item-error detection and circuit breaker. |
| Secret exclusion | Generated `.env`, `.gitignore`, repository check | No committed credentials/raw data/model weights/local databases. The repository scanner is a narrow accidental-exposure check, not comprehensive secret detection. |
| Container boundary | Compose/Dockerfile | Loopback ports, non-root API user, named database volumes; no public deployment automation. Search security is disabled for local use only. |
| No autonomous actions | No executor or action tools in M1 | No shell generated by an LLM can be run because no LLM/action execution path exists. Approval tables alone do not count as implemented approval workflows. |
| Production promotion gate | Settings validator | `ENVIRONMENT=production` fails startup until enterprise identity and deployment review are implemented. Setting `local` does not make public exposure safe. |

## Required before live connectors / RAG (M2)

- **Identity and tenancy:** OIDC/JWT issuer, audience, signature and expiry validation; named service/user principals; separate tenants; tenant/document ACL filters at retrieval and result delivery; deny missing authorization context; never trust a caller/model-supplied tenant ID.
- **Enterprise credentials:** MSAL/OAuth scopes, managed secrets, refresh/rotation, no tokens in prompts/logs/checkpoints; outbound destination allowlists and network egress controls. DNS rebinding protection belongs at the egress proxy/network layer in addition to URL checks.
- **Data permissions and privacy:** classification, PII/secret scanning before embedding, explicit redaction policy, retention/deletion propagation, encrypted storage/transit and access-controlled quarantine. Local benchmark files may contain personal identifiers.
- **Ingestion:** file/MIME allowlists, archive/path validation, document size/page/token/decompression budgets, malware scanning where applicable, sandboxed document parsing, schema-drift approval, connector pagination/rate-limit tests and watermark recovery.
- **Retrieval:** source/document version and ACL metadata, stable chunk IDs, provenance/citations, trusted collection allowlists, tenant-filter negative tests, prompt-injection-bearing document tests, retrieval poisoning review and deletion propagation.
- **Quality:** held-out judgments and nDCG/MRR/Recall@k, latency/memory budgets, evidence sufficiency thresholds, calibrated abstention and versioned index/model rollback. Similarity scores are not probabilities of truth.

## Required before agents / tools (M3)

- Treat incident text, logs, retrieved pages and tool output as **untrusted data**. They cannot change system policy, tool permissions, identity or approval state. Delimit provenance and maintain typed data/control boundaries.
- Use a typed tool registry with an explicit allowlist, parameter schemas, source/tenant scope, deadlines and bounded result size. Deny raw shell, `eval`, arbitrary SQL and arbitrary network destinations.
- Bound each run's steps, wall time, parallel calls, tokens and estimated spend; stop/abstain on exhausted budgets. Retry transient failures only; cap retries at tool and orchestration levels.
- Require evidence IDs for every hypothesis and distinguish facts from hypotheses. Validate citations refer to accessible retrieved evidence; do not treat source instructions as authorization.
- Add prompt-injection and tool-escalation regression tests, including indirect injections in logs/documents. A keyword/regex "jailbreak detector" is not a complete defense.
- Version/checkpoint state with a validated tenant/principal binding; encrypt and expire sensitive checkpoint contents. Reauthorize resumed runs.
- Trace tools/models with Langfuse/OpenTelemetry only after redaction; configure sampling, access and retention. Track actual provider usage and configured prices rather than inventing token/cost estimates.

## Required before remediation (M4)

- Predefined action handlers only, with target allowlists, validated parameters and explicit risk classification. No arbitrary LLM-produced commands.
- A proposal binds incident, run, action, parameters, target, rollback plan and version/digest. Any mutation invalidates approval.
- Named approver, correct role, timestamp, expiry, justification and separation of duties. High-risk actions require dual approval. The submitting agent cannot approve itself.
- Check authorization again at execution; atomically claim an approved proposal to prevent replay/double execution. Define maintenance-window, environment and blast-radius limits.
- Dry-run where supported; prerequisites, resource-health checks, bounded concurrency and timeouts; validate postconditions. On failure, use the reviewed rollback plan and escalate.
- Global kill switch/cancellation, durable audit history and incident response. Automatic remediation remains off by default.

## Production operations gate

Before promotion: TLS, secret manager, least-privilege database roles, managed search security, distributed rate limiting, audit forwarding/WORM retention, SLOs/alerts, dependency/container vulnerability scanning, SBOM/signing, protected branches/reviews, backups/restore drills, disaster recovery, load/chaos tests and a reviewed threat model. Requirements depend on deployment and data classification; none is claimed implemented merely because it appears here.

## Showcase walkthrough

1. Run `uv run pytest -q tests/test_guardrails.py tests/test_api.py` and show denied requests, not only happy paths.
2. Show 401 for absent credentials, 403 for reader writes and 409 for conflicting idempotency use.
3. Show 413 for oversized/chunked payloads, 415 for unsupported body types, 429 for rate limits, 504 for timeout, and generic 422 errors that do not echo input.
4. Show allowed-host and download destination failures, checksum refusal and corrupt-output recovery.
5. Show the real-data quality report: BPI 2014 contains 203 rows without incident IDs, quarantined instead of assigned fabricated identifiers.
6. Walk through the planned agent/approval threat boundaries and explain exactly which tests must exist before those features are enabled.

## References

- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP GenAI risks](https://genai.owasp.org/llm-top-10/)

The design uses these as threat-model references, not as an assertion of certification or full compliance.
