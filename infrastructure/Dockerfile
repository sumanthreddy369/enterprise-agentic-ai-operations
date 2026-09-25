FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.15
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY apps ./apps
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home ops
COPY alembic.ini ./
COPY infrastructure/migrations ./infrastructure/migrations
COPY data/dataset_manifest.json ./data/dataset_manifest.json
COPY docs/LOGHUB-LICENSE.txt ./docs/LOGHUB-LICENSE.txt
USER ops
EXPOSE 8000
CMD ["/opt/venv/bin/uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
