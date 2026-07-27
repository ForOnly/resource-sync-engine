"""Pipeline executor — runs the processing pipeline for a single resource."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path

from resource_sync.domain.events import (
    ResourceFailed,
    ResourceFetchCompleted,
    ResourceFetchStarted,
    ResourceHashCompared,
    ResourceSkipped,
    ResourceWritten,
)
from resource_sync.domain.models import HashResult, Resource, ResourceResult, SyncStatus
from resource_sync.domain.pipeline import Pipeline
from resource_sync.domain.stream import (
    CancellationToken,
    PipelineContext,
    Stream,
    drain_stream,
    tee_stream,
)
from resource_sync.eventbus.memory import EventBus

_LOGGER = logging.getLogger(__name__)


class PipelineExecutor:
    """Executes a Pipeline for a single resource. Stateless."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus

    async def execute(
        self,
        pipeline: Pipeline,
        resource: Resource,
        cancel: CancellationToken,
        config: dict | None = None,
        env: dict[str, str] | None = None,
    ) -> ResourceResult:
        ctx = PipelineContext(
            resource=resource, cancel=cancel, env=env or {}, config=config or {},
        )
        stage_times: dict[str, float] = {}

        try:
            # Stage 0: Compute local file hash (if exists)
            local_hash = await self._compute_local_hash(resource)
            stage_times["local_hash"] = 0.0

            # Stage 1: Fetch
            await self._events.emit(ResourceFetchStarted(resource_name=resource.name))
            t0 = time.monotonic()
            fetch_result = await pipeline.source.fetch(resource, ctx)
            stage_times["fetch"] = (time.monotonic() - t0) * 1000
            await self._events.emit(ResourceFetchCompleted(
                resource_name=resource.name, bytes_downloaded=fetch_result.content_length or 0,
            ))
            stream = fetch_result.stream

            # Stage 2-3: Validate + Transform (async generators, no await)
            for stage_name, stages in [
                ("validate", pipeline.validators),
                ("transform", pipeline.transforms),
            ]:
                for stage_fn in stages:
                    t0 = time.monotonic()
                    stream = stage_fn(stream, resource, ctx)
                    stage_times[f"{stage_name}.{type(stage_fn).__name__}"] = (time.monotonic() - t0) * 1000

            # Stage 4: Hash (tee'd — computed as stream is consumed)
            hasher = hashlib.new(resource.algorithm.value)
            stream = tee_stream(stream, lambda c: hasher.update(c))

            # Stage 5: Sink (consume the stream, writing to disk)
            if pipeline.sink is not None:
                t0 = time.monotonic()
                write_result = await pipeline.sink.write(stream, resource, ctx)
                stage_times["sink"] = (time.monotonic() - t0) * 1000
            else:
                await drain_stream(stream)

            # Now the hasher has processed all chunks — finalize
            remote_hash = HashResult(
                algorithm=resource.algorithm,
                hex_digest=hasher.hexdigest(),
            )

            # Stage 6: Compare hashes and determine status
            if local_hash is not None and local_hash.matches(remote_hash):
                # Hash matches — file unchanged. Undo the write.
                self._undo_write(resource)
                stage_times["compare"] = 0.0
                await self._events.emit(ResourceSkipped(resource_name=resource.name))
                await self._events.emit(
                    ResourceHashCompared(resource_name=resource.name, matched=True)
                )
                return ResourceResult(
                    resource_name=resource.name,
                    status=SyncStatus.SKIPPED,
                    local_hash=local_hash,
                    remote_hash=remote_hash,
                    stage_times=stage_times,
                    dry_run=ctx.config.get("dry_run", False),
                )

            # Content changed — report as created or updated
            status = SyncStatus.CREATED if local_hash is None else SyncStatus.UPDATED
            await self._events.emit(
                ResourceWritten(
                    resource_name=resource.name,
                    path=str(resource.path),
                    bytes_written=(
                        write_result.bytes_written if pipeline.sink else 0
                    ),
                )
            )
            await self._events.emit(
                ResourceHashCompared(resource_name=resource.name, matched=False)
            )

            return ResourceResult(
                resource_name=resource.name,
                status=status,
                local_hash=local_hash,
                remote_hash=remote_hash,
                stage_times=stage_times,
                dry_run=ctx.config.get("dry_run", False),
            )

        except Exception as e:
            stage = list(stage_times.keys())[-1] if stage_times else "unknown"
            await self._events.emit(ResourceFailed(
                resource_name=resource.name,
                error=f"{type(e).__name__}: {e}",
                stage=stage,
            ))
            return ResourceResult(
                resource_name=resource.name,
                status=SyncStatus.ERROR,
                error_message=f"{type(e).__name__}: {e}",
                stage_times=stage_times,
                dry_run=ctx.config.get("dry_run", False),
            )

    async def _compute_local_hash(self, resource: Resource) -> HashResult | None:
        """Compute the hash of the local file if it exists.

        Runs in a thread pool executor to avoid blocking the event loop
        on disk I/O for large files.
        """
        target = Path(resource.path)
        if not target.exists():
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_hash_file, target, resource)

    @staticmethod
    def _sync_hash_file(target: Path, resource: Resource) -> HashResult:
        """Synchronous file hashing — runs in thread pool."""
        hasher = hashlib.new(resource.algorithm.value)
        with target.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return HashResult(
            algorithm=resource.algorithm,
            hex_digest=hasher.hexdigest(),
        )

    @staticmethod
    def _undo_write(resource: Resource) -> None:
        """Delete the file that was written but has the same hash.

        This is the 'write then maybe undo' approach: we always write,
        then delete if the content hasn't changed. This preserves the
        streaming pipeline while still supporting SKIPPED status.
        """
        target = Path(resource.path)
        try:
            target.unlink(missing_ok=True)
            _LOGGER.debug("Undid write for '%s' (hash matched)", resource.name)
        except OSError:
            _LOGGER.warning(
                "Could not undo write for '%s': %s", resource.name, target
            )