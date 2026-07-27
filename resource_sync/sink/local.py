"""Local file sink — atomic streaming write to disk."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamSink, WriteResult
from resource_sync.plugin.registry import register_sink

_LOGGER = logging.getLogger(__name__)


@register_sink("local")
class LocalSink:
    """Streaming local file writer with atomic writes."""
    name: ClassVar[str] = "local"

    @classmethod
    def configure(cls, resource: Resource) -> StreamSink:
        return cls()

    async def write(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> WriteResult:
        target = Path(resource.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(dir=str(target.parent), prefix=f".{resource.name}.", suffix=".tmp")
        tmp_path = Path(tmp_path_str)
        hasher = hashlib.new(resource.algorithm.value)
        total = 0
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in stream:
                    if ctx.cancel.cancelled:
                        raise asyncio.CancelledError()
                    hasher.update(chunk)
                    total += len(chunk)
                    f.write(chunk)
            tmp_path.replace(target)
            _LOGGER.info("Wrote %d bytes to '%s'", total, target)
            return WriteResult(path=str(target), bytes_written=total, hash_value=hasher.hexdigest())
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise