"""ASGI resource controls for the local API; not a distributed gateway replacement."""

import asyncio
import logging
import re
import time
from collections import OrderedDict
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.services.settings import Settings

logger = logging.getLogger(__name__)


class RequestGuardrails:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.clients: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self.inflight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin1")
        request_id = incoming if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", incoming) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"frame-ancestors 'none'; base-uri 'none'"),
                ]
                if not any(k.lower() == b"x-request-id" for k, _ in message["headers"]):
                    message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        async def reject(code: int, reason: str, retry: bool = False) -> None:
            logger.warning(
                "guardrail_rejected",
                extra={
                    "status_code": code,
                    "error_category": reason,
                    "request_id": scope.get("state", {}).get("request_id"),
                },
            )
            response = JSONResponse(
                {"detail": reason},
                status_code=code,
                headers={"Retry-After": "60"} if retry else None,
            )
            await response(scope, receive, secure_send)

        if sum(len(k) + len(v) for k, v in scope["headers"]) > 16384:
            await reject(431, "Request headers too large")
            return
        if len(scope.get("query_string", b"")) > 4096:
            await reject(414, "Query string too large")
            return
        headers = {key.lower(): value for key, value in scope["headers"]}
        if headers.get(b"content-encoding", b"identity").lower() != b"identity":
            await reject(415, "Compressed request bodies are not supported")
            return
        lengths = [v for k, v in scope["headers"] if k.lower() == b"content-length"]
        if len(lengths) > 1:
            await reject(400, "Duplicate Content-Length")
            return
        try:
            length = int(lengths[0]) if lengths else 0
        except ValueError:
            await reject(400, "Invalid Content-Length")
            return
        if length < 0 or length > self.settings.max_request_bytes:
            await reject(413, "Request body too large")
            return
        if scope["method"] in {"POST", "PUT", "PATCH"}:
            if headers.get(b"content-type", b"").split(b";", 1)[0].lower() != b"application/json":
                await reject(415, "Content-Type must be application/json")
                return
        if scope["path"] != "/health":
            peer = str((scope.get("client") or ("unknown", 0))[0])
            now = time.monotonic()
            # Fixed windows and a bounded map prevent unbounded memory growth.
            if (
                peer not in self.clients
                and len(self.clients) >= self.settings.max_rate_limit_clients
            ):
                self.clients = OrderedDict(
                    (k, v) for k, v in self.clients.items() if now - v[0] < 60
                )
                if len(self.clients) >= self.settings.max_rate_limit_clients:
                    await reject(429, "Rate limit capacity reached", True)
                    return
            started, count = self.clients.get(peer, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            if count >= self.settings.requests_per_minute:
                await reject(429, "Request rate limit exceeded", True)
                return
            self.clients[peer] = started, count + 1
        if self.inflight >= self.settings.max_concurrent_requests:
            await reject(503, "Request concurrency limit reached", True)
            return
        self.inflight += 1
        try:
            body = bytearray()
            try:
                async with asyncio.timeout(self.settings.body_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > self.settings.max_request_bytes:
                            await reject(413, "Request body too large")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "Request body timed out")
                return
            consumed = False
            response_started = False

            async def buffered_receive() -> Message:
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            async def tracked_send(message: Message) -> None:
                nonlocal response_started
                if message["type"] == "http.response.start":
                    response_started = True
                await secure_send(message)

            try:
                async with asyncio.timeout(self.settings.handler_timeout_seconds):
                    await self.app(scope, buffered_receive, tracked_send)
            except TimeoutError:
                if not response_started:
                    await reject(504, "Request processing timed out")
        finally:
            self.inflight -= 1
