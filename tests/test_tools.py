import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, Field

from src.domain.contracts import AuthorizationContext, ToolDescriptor
from src.services.errors import (
    InvalidToolInput,
    InvalidToolOutput,
    PermissionDenied,
    ToolBusy,
    ToolNotFound,
    ToolTimeout,
    ToolUnavailable,
)
from src.services.tools import ToolRegistry, TypedTool


class Request(BaseModel):
    number: int = Field(ge=1)


class Response(BaseModel):
    value: str


def context(**overrides):
    fields = dict(
        subject="test",
        tenant_id="local",
        request_id="request-1",
        permissions=frozenset({"test:read"}),
        allowed_sources=frozenset({"synthetic"}),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return AuthorizationContext(**(fields | overrides))


def registry(handler, **options):
    result = ToolRegistry(max_concurrent=1)
    tool = TypedTool(
        descriptor=ToolDescriptor(
            name="test.read", permission="test:read", description="Synthetic test tool", **options
        ),
        input_model=Request,
        output_model=Response,
        handler=handler,
    )
    result.register(tool)
    result.seal()
    return result


async def test_authorization_and_input_checked_before_dispatch() -> None:
    calls = []

    async def handler(ctx, request):
        calls.append(request)
        return Response(value="ok")

    tools = registry(handler)
    for ctx in [
        context(permissions=frozenset()),
        context(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
    ]:
        with pytest.raises(PermissionDenied):
            await tools.execute("test.read", ctx, {"number": 1})
    with pytest.raises(InvalidToolInput):
        await tools.execute("test.read", context(), {"number": 0})
    with pytest.raises(ToolNotFound):
        await tools.execute("arbitrary.command", context(), {})
    assert not calls
    result = await tools.execute("test.read", context(), {"number": 1})
    assert result == Response(value="ok")
    assert len(calls) == 1
    assert tools.descriptors(context(permissions=frozenset())) == ()
    assert tools.descriptors(context())[0].name == "test.read"


async def test_read_only_sealed_and_duplicate_registration() -> None:
    async def handler(ctx, request):
        return Response(value="ok")

    tools = ToolRegistry()
    tool = TypedTool(
        descriptor=ToolDescriptor(
            name="test.write", permission="write", description="test", read_only=False
        ),
        input_model=Request,
        output_model=Response,
        handler=handler,
    )
    with pytest.raises(PermissionDenied):
        tools.register(tool)
    read = TypedTool(
        descriptor=ToolDescriptor(name="test.read", permission="read", description="test"),
        input_model=Request,
        output_model=Response,
        handler=handler,
    )
    tools.register(read)
    with pytest.raises(ValueError, match="duplicate"):
        tools.register(read)
    tools.seal()
    with pytest.raises(ValueError, match="sealed"):
        tools.register(read)


async def test_output_budget_and_invalid_constructed_output() -> None:
    async def oversized(ctx, request):
        return Response(value="x" * 500)

    with pytest.raises(InvalidToolOutput, match="limit"):
        await registry(oversized, max_output_bytes=128).execute(
            "test.read", context(), {"number": 1}
        )

    async def invalid(ctx, request):
        return Response.model_construct(value=None)

    with pytest.raises(InvalidToolOutput, match="invalid"):
        await registry(invalid).execute("test.read", context(), {"number": 1})


async def test_timeout_and_sensitive_exception_not_exposed(caplog) -> None:
    async def slow(ctx, request):
        await asyncio.sleep(1)
        return Response(value="never")

    with pytest.raises(ToolTimeout):
        await registry(slow, timeout_seconds=0.01).execute("test.read", context(), {"number": 1})
    secret = "sensitive-provider-error"

    async def failing(ctx, request):
        raise RuntimeError(secret)

    with caplog.at_level("INFO"), pytest.raises(ToolUnavailable) as failure:
        await registry(failing).execute("test.read", context(), {"number": 1})
    assert secret not in str(failure.value)
    assert secret not in caplog.text


async def test_concurrency_cancellation_and_slot_recovery() -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold(ctx, request):
        entered.set()
        await release.wait()
        return Response(value="ok")

    tools = registry(hold)
    task = asyncio.create_task(tools.execute("test.read", context(), {"number": 1}))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        with pytest.raises(ToolBusy):
            await tools.execute("test.read", context(), {"number": 1})
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    release.set()
    assert await tools.execute("test.read", context(), {"number": 1}) == Response(value="ok")


async def test_expired_results_are_not_released() -> None:
    async def slow(ctx, request):
        await asyncio.sleep(0.03)
        return Response(value="late")

    with pytest.raises(PermissionDenied):
        await registry(slow).execute(
            "test.read",
            context(expires_at=datetime.now(UTC) + timedelta(seconds=0.01)),
            {"number": 1},
        )
