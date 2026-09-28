# Contributing

Use Python 3.11 and the locked environment (`uv sync --frozen --python 3.11`). Follow the [Phase A–M plan](docs/target-architecture.md); update implementation status and evidence with each completed step. Keep synthetic fixtures labeled and preserve the existing source provenance.

For runtime changes run:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src apps
uv run pytest -q
uv run python scripts/check_repository.py
```

Run real PostgreSQL/OpenSearch checks through `scripts/run_integration.py` with configured Compose services; CI also verifies these and the container. Schema changes require Alembic migrations and drift checks. Documentation-only changes require checking repository-relative links, diagram structure, status accuracy and ignore rules; do not report historical tests as newly run.

Never commit `.env`, credentials, acquired datasets, generated data or downloaded models. Stage and inspect the intended diff, run the tracked-file exposure check, commit each verified step and push to GitHub. Wait for CI and correct failures. Do not claim cloud deployment, enterprise authentication, agents or retrieval quality based only on interfaces or configuration files.
