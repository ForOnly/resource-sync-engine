"""Drain sink — discards all data (used in dry-run mode)."""

from __future__ import annotations

import asyncio
from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamSink, WriteResult
from resource_sync.plugin.registry import register_sink


@register_sink("drain")
class DrainSink:
    """No-op sink that discards all data.

    Used in dry-run mode: the stream is consumed (triggering all
    validators and the hasher) but nothing is written to disk.
    """

    name: ClassVar[str] = "drain"

    @classmethod
    def configure(cls, resource: Resource) -> StreamSink:
        return cls()

    async def write(
        self, stream: Stream, resource: Resource, ctx: PipelineContext
    ) -> WriteResult:
        """Consume and discard the entire stream."""
        total = 0
        async for chunk in stream:
            if ctx.cancel.cancelled:
                raise asyncio.CancelledError()
            total += len(chunk)
        return WriteResult(path=str(resource.path), bytes_written=total)

    def commit(self) -> bool:
        """No-op: drain sink has nothing to commit."""
        return True

    def discard(self) -> bool:
        """No-op: drain sink has nothing to discard."""
        return True


def create_drain_sink() -> StreamSink:
    """Factory function to create a drain sink."""
    return DrainSink()