"""Read-only tool dispatch shared by the API and future agent/protocol adapters."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, JsonValue, ValidationError

from src.domain.contracts import AuthorizationContext, ToolDescriptor
from src.security.policy import authorize
from src.services.errors import (
    InvalidToolInput,
    InvalidToolOutput,
    PermissionDenied,
    ServiceError,
    ToolBusy,
    ToolNotFound,
    ToolTimeout,
    ToolUnavailable,
)

logger = logging.getLogger(__name__)
Input = TypeVar("Input", bound=BaseModel)
Output = TypeVar("Output", bound=BaseModel)


class BoundTool(Protocol):
    @property
    def descriptor(self) -> ToolDescriptor: ...

    async def invoke(
        self, context: AuthorizationContext, arguments: Mapping[str, JsonValue]
    ) -> BaseModel: ...


@dataclass(frozen=True)
class TypedTool(Generic[Input, Output]):
    descriptor: ToolDescriptor
    input_model: type[Input]
    output_model: type[Output]
    handler: Callable[[AuthorizationContext, Input], Awaitable[Output]]

    async def invoke(
        self, context: AuthorizationContext, arguments: Mapping[str, JsonValue]
    ) -> Output:
        try:
            request = self.input_model.model_validate(dict(arguments))
        except ValidationError:
            raise InvalidToolInput("Tool arguments are invalid") from None
        result = await self.handler(context, request)
        try:
            # Revalidate a fresh copy: do not trust model_construct or a mutated result.
            output = self.output_model.model_validate(result.model_dump())
            if len(output.model_dump_json().encode()) > self.descriptor.max_output_bytes:
                raise InvalidToolOutput("Tool output exceeds the configured limit")
            return output
        except (ValidationError, AttributeError):
            raise InvalidToolOutput("Tool returned an invalid result") from None


class ToolRegistry:
    def __init__(self, *, max_concurrent: int = 8) -> None:
        if not 1 <= max_concurrent <= 128:
            raise ValueError("max_concurrent must be between 1 and 128")
        self._tools: dict[str, BoundTool] = {}
        self._active = 0
        self._max_concurrent = max_concurrent
        self._sealed = False

    def register(self, tool: BoundTool) -> None:
        if self._sealed:
            raise ValueError("tool registry is sealed")
        if not tool.descriptor.read_only:
            raise PermissionDenied("Consequential tools require the future approval executor")
        if tool.descriptor.name in self._tools:
            raise ValueError("duplicate tool registration")
        self._tools[tool.descriptor.name] = tool

    def seal(self) -> None:
        self._sealed = True

    def descriptors(self, context: AuthorizationContext) -> tuple[ToolDescriptor, ...]:
        visible = []
        for tool in self._tools.values():
            try:
                authorize(context, tool.descriptor.permission)
            except PermissionDenied:
                continue
            visible.append(tool.descriptor)
        return tuple(visible)

    async def execute(
        self, name: str, context: AuthorizationContext, arguments: Mapping[str, JsonValue]
    ) -> BaseModel:
        started = time.perf_counter()
        outcome = "denied"
        acquired = False
        try:
            tool = self._tools.get(name)
            if tool is None:
                raise ToolNotFound("Unknown tool")
            authorize(context, tool.descriptor.permission)
            if self._active >= self._max_concurrent:
                raise ToolBusy("Tool concurrency limit reached")
            self._active += 1
            acquired = True
            try:
                async with asyncio.timeout(tool.descriptor.timeout_seconds):
                    result = await tool.invoke(context, arguments)
            except TimeoutError:
                raise ToolTimeout("Tool deadline exceeded") from None
            authorize(context, tool.descriptor.permission)  # Expired results are not released.
            outcome = "success"
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except ServiceError as exc:
            outcome = type(exc).__name__
            raise
        except Exception:
            outcome = "ToolUnavailable"
            raise ToolUnavailable("Tool dependency failed") from None
        finally:
            if acquired:
                self._active -= 1
            # Never log arguments, results, exception strings or authorization credentials.
            logger.info(
                "tool_call",
                extra={
                    "request_id": context.request_id,
                    "tool_name": name if name in self._tools else "unknown",
                    "error_category": outcome,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
