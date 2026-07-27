"""Empty content validator — rejects zero-byte downloads."""

from __future__ import annotations

from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamTransformer
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.plugin.registry import register_validator


@register_validator
class EmptyValidator:
    """Validates that downloaded content is not empty."""
    name: ClassVar[str] = "empty"

    @classmethod
    def should_apply(cls, resource: Resource) -> bool:
        return True

    def __call__(self) -> StreamTransformer:
        return self._validate

    async def _validate(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> Stream:
        first = b""
        async for chunk in stream:
            first = chunk
            break
        if not first:
            raise PluginExecutionError(f"Content for '{resource.name}' is empty (0 bytes)")
        yield first
        async for chunk in stream:
            yield chunk