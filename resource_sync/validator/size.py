"""Streaming size validator — rejects content exceeding max_size."""

from __future__ import annotations

from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamTransformer
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.plugin.registry import register_validator


@register_validator
class SizeValidator:
    """Validates content does not exceed max_size."""
    name: ClassVar[str] = "size"
    priority: ClassVar[int] = 300  # Run last — checks every chunk

    @classmethod
    def should_apply(cls, resource: Resource) -> bool:
        return resource.max_size > 0

    def __call__(self) -> StreamTransformer:
        return self._validate

    async def _validate(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> Stream:
        total = 0
        async for chunk in stream:
            total += len(chunk)
            if total > resource.max_size:
                raise PluginExecutionError(
                    f"Content exceeded max_size {resource.max_size} ({total} bytes)"
                )
            yield chunk