"""Identity transform — passes through the stream unchanged.

Useful as a default / no-op transform and as a reference implementation
for custom transform plugins.
"""

from __future__ import annotations

from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamTransformer
from resource_sync.plugin.registry import register_transform


@register_transform("identity")
class IdentityTransform:
    """Pass-through transform — yields chunks unchanged."""

    name: ClassVar[str] = "identity"

    @classmethod
    def should_apply(cls, resource: Resource) -> bool:
        return False  # Not applied by default; only when explicitly configured

    def __call__(self) -> StreamTransformer:
        return self._transform

    async def _transform(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> Stream:
        async for chunk in stream:
            yield chunk