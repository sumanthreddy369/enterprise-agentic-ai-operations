# Tracked repository map

Generated data, environments, caches, local databases, `.env`, `.local`, dependencies, build output, and `.git` are excluded.

```text
.
├── .github/workflows/ci.yml
├── apps/
│   ├── __init__.py
│   ├── api/__init__.py
│   ├── api/main.py
│   └── dashboard/README.md
├── data/
│   ├── bronze/.gitkeep
│   ├── gold/.gitkeep
│   ├── raw/.gitkeep
│   ├── silver/.gitkeep
│   ├── synthetic/.gitkeep
│   └── dataset_manifest.json
├── docs/
│   ├── flows/data-pipeline.md
│   ├── flows/http-api.md
│   ├── flows/log-search.md
│   ├── flows/runtime-ci.md
│   ├── LOGHUB-LICENSE.txt
│   ├── architecture.md
│   ├── datasets.md
│   ├── guardrails.md
│   ├── inference-optimization.md
│   ├── phase-b.md
│   ├── repository-map.md
│   ├── target-architecture.md
│   ├── technology-plan.md
│   └── verification.md
├── infrastructure/
│   ├── migrations/versions/0001_foundation_enterprise_data_foundation.py
│   ├── migrations/env.py
│   ├── migrations/script.py.mako
│   ├── Dockerfile
│   └── analytics.sql
├── notebooks/README.md
├── scripts/
│   ├── build_dataset_manifest.py
│   ├── check_repository.py
│   ├── init_local.py
│   ├── research_datasets.py
│   ├── run_integration.py
│   └── smoke_api.py
├── src/
│   ├── agents/README.md
│   ├── domain/
│   │   ├── __init__.py
│   │   └── contracts.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── acquire.py
│   │   └── cli.py
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── log_search.py
│   │   └── opensearch.py
│   ├── mcp/README.md
│   ├── models/
│   │   ├── __init__.py
│   │   ├── contracts.py
│   │   ├── database.py
│   │   └── types.py
│   ├── observability/
│   │   ├── __init__.py
│   │   └── logging.py
│   ├── orchestration/README.md
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── load.py
│   │   ├── normalize.py
│   │   ├── parsers.py
│   │   └── runner.py
│   ├── rag/README.md
│   ├── security/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── egress.py
│   │   ├── guardrails.py
│   │   └── policy.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── errors.py
│   │   ├── logs.py
│   │   ├── ports.py
│   │   ├── settings.py
│   │   └── tools.py
│   └── __init__.py
├── tests/
│   ├── conftest.py
│   ├── test_acquire.py
│   ├── test_api.py
│   ├── test_backends.py
│   ├── test_domain_contracts.py
│   ├── test_download_security.py
│   ├── test_guardrails.py
│   ├── test_log_service.py
│   ├── test_opensearch.py
│   ├── test_pipeline.py
│   ├── test_resource_limits.py
│   └── test_tools.py
├── .env.example
├── .dockerignore
├── .gitattributes
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── README.md
├── SECURITY.md
├── alembic.ini
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
```
