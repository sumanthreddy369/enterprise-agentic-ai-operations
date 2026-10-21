"""Local-role investigation submission, cancellation and evidence report API."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import Field

from src.domain.contracts import (
    AuthorizationContext,
    DomainModel,
    InvestigationReport,
    InvestigationRequest,
    InvestigationSnapshot,
    SourceReference,
    Text,
)
from src.security.auth import Principal, principal, writer
from src.services.investigations import SQLInvestigationRepository

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


class Submission(DomainModel):
    incident: SourceReference
    question: Text


class Cancellation(DomainModel):
    expected_revision: int = Field(ge=0)


def context(user: Principal, request: Request) -> AuthorizationContext:
    permissions = {"investigations:read"}
    if user.role == "writer":
        permissions.add("investigations:write")
    return AuthorizationContext(
        subject=user.identity,
        tenant_id="local",
        request_id=request.state.request_id,
        permissions=frozenset(permissions),
        allowed_sources=frozenset({"bpi-2013", "bpi-2014", "api:local-writer"}),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


@router.post("", response_model=InvestigationSnapshot, status_code=202)
async def submit(
    body: Submission,
    request: Request,
    user: Annotated[Principal, Depends(writer)],
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r"\S")],
) -> InvestigationSnapshot:
    return await SQLInvestigationRepository(request.app.state.sessions).create(
        context(user, request),
        InvestigationRequest(**body.model_dump(), idempotency_key=idempotency_key),
    )


@router.get("/{run_id}", response_model=InvestigationSnapshot)
async def get(
    run_id: str, request: Request, user: Annotated[Principal, Depends(principal)]
) -> InvestigationSnapshot:
    result = await SQLInvestigationRepository(request.app.state.sessions).get(
        context(user, request), run_id
    )
    if result is None:
        raise HTTPException(404, "Investigation not found")
    return result


@router.post("/{run_id}/cancel", response_model=InvestigationSnapshot)
async def cancel(
    run_id: str, body: Cancellation, request: Request, user: Annotated[Principal, Depends(writer)]
) -> InvestigationSnapshot:
    repository = SQLInvestigationRepository(request.app.state.sessions)
    auth = context(user, request)
    current = await repository.get(auth, run_id)
    if current is None:
        raise HTTPException(404, "Investigation not found")
    return await repository.transition(
        auth,
        current.model_copy(update={"status": "cancelled"}),
        expected_revision=body.expected_revision,
    )


@router.get("/{run_id}/report", response_model=InvestigationReport)
async def report(
    run_id: str, request: Request, user: Annotated[Principal, Depends(principal)]
) -> InvestigationReport:
    result = await SQLInvestigationRepository(request.app.state.sessions).get_report(
        context(user, request), run_id
    )
    if result is None:
        raise HTTPException(409, "Report is not available")
    return result
