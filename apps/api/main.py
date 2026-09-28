import hashlib
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.domain.contracts import LogSearchQuery
from src.integrations.log_search import OpenSearchLogSearch
from src.integrations.opensearch import OpenSearch, SearchUnavailable
from src.models.contracts import IncidentCreate, IncidentView
from src.models.database import AuditEvent, IdempotencyRecord, Incident
from src.observability.logging import configure_logging
from src.security.auth import Principal, principal, tool_context, writer
from src.security.guardrails import RequestGuardrails
from src.services.db import make_engine, session_factory
from src.services.errors import (
    InvalidToolInput,
    PermissionDenied,
    ServiceError,
    ToolBusy,
    ToolNotFound,
    ToolTimeout,
)
from src.services.logs import log_registry, search_envelope
from src.services.logs import search_logs as run_log_search
from src.services.settings import Settings

logger = logging.getLogger(__name__)


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as database:
        yield database


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        engine = make_engine(config.database_url)
        app.state.sessions = session_factory(engine)
        auth = (
            (config.opensearch_username, config.opensearch_password.get_secret_value())
            if config.opensearch_username and config.opensearch_password
            else None
        )
        async with httpx.AsyncClient(
            base_url=config.opensearch_url, timeout=config.request_timeout, auth=auth
        ) as client:
            app.state.search = OpenSearch(client)
            app.state.tools = log_registry(OpenSearchLogSearch(app.state.search))
            try:
                yield
            finally:
                await engine.dispose()

    app = FastAPI(
        title="Enterprise AI Operations — Data Foundation", version="0.1.0", lifespan=lifespan
    )
    app.state.settings = config

    @app.middleware("http")
    async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", incoming) else str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": getattr(request.scope.get("route"), "path", "unmatched"),
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(RequestGuardrails, settings=config)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Do not echo raw submitted inputs, secrets, or validator context.
        errors = [
            {"loc": item["loc"], "type": item["type"], "msg": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, _: SQLAlchemyError) -> JSONResponse:
        logger.error(
            "database_failure",
            extra={"request_id": request.state.request_id, "error_category": "database"},
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable", "request_id": request.state.request_id},
        )

    @app.exception_handler(SearchUnavailable)
    @app.exception_handler(httpx.HTTPError)
    async def search_error(request: Request, _: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Search unavailable", "request_id": request.state.request_id},
        )

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, error: ServiceError) -> JSONResponse:
        status = 503
        detail = "Tool service unavailable"
        if isinstance(error, PermissionDenied):
            status, detail = 403, "Tool access denied"
        elif isinstance(error, ToolNotFound):
            status, detail = 404, "Tool not found"
        elif isinstance(error, InvalidToolInput):
            status, detail = 422, "Invalid tool input"
        elif isinstance(error, ToolTimeout):
            status, detail = 504, "Tool timed out"
        return JSONResponse(
            status_code=status,
            content={"detail": detail, "request_id": request.state.request_id},
            headers={"Retry-After": "1"} if isinstance(error, ToolBusy) else None,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "milestone": "1"}

    @app.get("/ready")
    async def ready(database: Annotated[AsyncSession, Depends(session)]) -> JSONResponse:
        dependencies = {"database": False}
        try:
            version = await database.scalar(text("SELECT version_num FROM alembic_version"))
            await database.execute(select(Incident.id).limit(1))
            dependencies["database"] = version == "0001_foundation"
        except SQLAlchemyError:
            pass
        if config.opensearch_required:
            try:
                dependencies["opensearch"] = await app.state.search.ready()
            except (SearchUnavailable, httpx.HTTPError):
                dependencies["opensearch"] = False
        good = all(dependencies.values())
        return JSONResponse(
            status_code=200 if good else 503, content={"ready": good, "dependencies": dependencies}
        )

    @app.post("/api/v1/incidents", response_model=IncidentView, status_code=201)
    async def create_incident(
        body: IncidentCreate,
        request: Request,
        user: Annotated[Principal, Depends(writer)],
        database: Annotated[AsyncSession, Depends(session)],
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128)],
    ) -> Incident:
        key = hashlib.sha256(f"{user.identity}:{idempotency_key}".encode()).hexdigest()
        digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()

        async def replay() -> Incident | None:
            existing = await database.get(IdempotencyRecord, key)
            if existing:
                if existing.request_hash != digest:
                    raise HTTPException(409, "Idempotency key already used with different content")
                incident = await database.get(Incident, existing.incident_id)
                if incident is not None:
                    return incident
            return None

        existing_incident = await replay()
        if existing_incident:
            return existing_incident
        incident = Incident(source=f"api:{user.identity}", **body.model_dump())
        database.add(incident)
        try:
            await database.flush()
            database.add(IdempotencyRecord(key=key, request_hash=digest, incident_id=incident.id))
            database.add(
                AuditEvent(
                    actor=user.identity,
                    action="incident.create",
                    resource_id=incident.id,
                    request_id=request.state.request_id,
                    details={"source": incident.source},
                )
            )
            await database.commit()
        except IntegrityError:
            await database.rollback()
            existing_incident = await replay()
            if existing_incident:
                return existing_incident
            raise HTTPException(409, "Source incident already exists") from None
        return incident

    @app.get("/api/v1/incidents", response_model=list[IncidentView])
    async def list_incidents(
        user: Annotated[Principal, Depends(principal)],
        database: Annotated[AsyncSession, Depends(session)],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        source: str | None = None,
    ) -> list[Incident]:
        statement = select(Incident).order_by(Incident.id).limit(limit).offset(offset)
        if source:
            statement = statement.where(Incident.source == source)
        return list((await database.scalars(statement)).all())

    @app.get("/api/v1/incidents/{incident_id}", response_model=IncidentView)
    async def get_incident(
        incident_id: str,
        user: Annotated[Principal, Depends(principal)],
        database: Annotated[AsyncSession, Depends(session)],
    ) -> Incident:
        incident = await database.get(Incident, incident_id)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        return incident

    @app.get("/api/v1/logs")
    async def search_logs(
        request: Request,
        user: Annotated[Principal, Depends(principal)],
        q: Annotated[str, Query(min_length=1, max_length=500, pattern=r"\S")],
        source: Annotated[str | None, Query(min_length=1, max_length=256, pattern=r"\S")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, JsonValue]:
        result = await run_log_search(
            app.state.tools,
            tool_context(user, request.state.request_id),
            LogSearchQuery(query=q, source=source, limit=limit),
        )
        return search_envelope(result)

    return app


app = create_app()
