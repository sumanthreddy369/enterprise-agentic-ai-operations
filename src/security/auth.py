import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.domain.contracts import AuthorizationContext
from src.services.settings import Settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str


async def principal(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Principal:
    settings: Settings = request.app.state.settings
    if credentials is None:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    for key, role in [(settings.api_write_key, "writer"), (settings.api_read_key, "reader")]:
        if key is not None and secrets.compare_digest(
            credentials.credentials, key.get_secret_value()
        ):
            return Principal(f"local-{role}", role)
    raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})


async def writer(user: Annotated[Principal, Depends(principal)]) -> Principal:
    if user.role != "writer":
        raise HTTPException(403, "Writer role required")
    return user


def tool_context(user: Principal, request_id: str) -> AuthorizationContext:
    # Only authenticated local roles exist today. Do not accept identity/scope headers.
    permissions = frozenset({"logs:read"}) if user.role in {"reader", "writer"} else frozenset()
    return AuthorizationContext(
        subject=user.identity,
        tenant_id="local",
        request_id=request_id,
        permissions=permissions,
        allowed_sources=frozenset(
            {"loghub-apache", "loghub-openstack", "loghub-bgl", "loghub-hdfs", "loghub-zookeeper"}
        ),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
