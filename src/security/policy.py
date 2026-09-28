from datetime import UTC, datetime

from src.domain.contracts import AuthorizationContext
from src.services.errors import PermissionDenied


def authorize(context: AuthorizationContext, permission: str) -> None:
    if context.expires_at <= datetime.now(UTC):
        raise PermissionDenied("Authorization has expired")
    if permission not in context.permissions:
        raise PermissionDenied("Required tool permission is missing")


def authorize_sources(context: AuthorizationContext, sources: frozenset[str]) -> None:
    if not sources or not sources.issubset(context.allowed_sources):
        raise PermissionDenied("Source access is not permitted")
