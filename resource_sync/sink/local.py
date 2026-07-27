"""Local file sink — atomic streaming write to disk via temp file."""

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
    """Streaming local file writer with two-phase commit.

    Phase 1 - write(): writes the stream to a temporary file.
    Phase 2 - commit() or discard(): atomically moves the temp file
    to the target path, or deletes it if the content hasn't changed.

    This avoids the "write-then-undo" pattern where files are written
    to the target path only to be deleted moments later when the hash
    matches.
    """

    name: ClassVar[str] = "local"

    def __init__(self) -> None:
        self._temp_path: Path | None = None
        self._target_path: Path | None = None

    @classmethod
    def configure(cls, resource: Resource) -> StreamSink:
        return cls()

    async def write(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> WriteResult:
        """Write the stream to a temporary file.

        The file is NOT moved to the target path yet. Call commit()
        to finalize the write, or discard() to cancel it.
        """
        target = Path(resource.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{resource.name}.",
            suffix=".tmp",
        )
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
            self._temp_path = tmp_path
            self._target_path = target
            _LOGGER.debug("Wrote %d bytes to temp '%s'", total, tmp_path)
            return WriteResult(
                path=str(target),
                bytes_written=total,
                hash_value=hasher.hexdigest(),
            )
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._temp_path = None
            raise

    def commit(self) -> bool:
        """Atomically move the temp file to the target path.

        Returns True on success, False if no temp file exists.
        """
        if self._temp_path is None or self._target_path is None:
            return False
        try:
            self._temp_path.replace(self._target_path)
            _LOGGER.info("Committed '%s'", self._target_path)
            self._temp_path = None
            return True
        except OSError as e:
            _LOGGER.error("Failed to commit '%s': %s", self._target_path, e)
            return False

    def discard(self) -> bool:
        """Delete the temp file without committing.

        Returns True on success, False if no temp file exists.
        """
        if self._temp_path is None:
            return False
        try:
            self._temp_path.unlink(missing_ok=True)
            _LOGGER.debug("Discarded temp '%s'", self._temp_path)
            self._temp_path = None
            return True
        except OSError as e:
            _LOGGER.warning("Failed to discard temp '%s': %s", self._temp_path, e)
            return False