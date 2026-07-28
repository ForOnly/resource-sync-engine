"""Pipeline executor — runs the processing pipeline for a single resource."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from resource_sync.domain.events import (
    ResourceFailed,
    ResourceFetchCompleted,
    ResourceFetchStarted,
    ResourceHashCompared,
    ResourceRemoteUnchanged,
    ResourceSkipped,
    ResourceWritten,
)
from resource_sync.domain.models import HashResult, Resource, ResourceResult, SyncStatus
from resource_sync.domain.pipeline import Pipeline
from resource_sync.domain.stream import (
    CancellationToken,
    PipelineContext,
    Stream,
    StreamTransformer,
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
        config: dict[str, Any] | None = None,
        env: dict[str, Any] | None = None,
    ) -> ResourceResult:
        ctx = PipelineContext(
            resource=resource, cancel=cancel, env=env or {}, config=config or {},
        )
        stage_times: dict[str, float] = {}

        try:
            # Stage 0: Compute local file hash (if exists)
            t0 = time.monotonic()
            local_hash = await self._compute_local_hash(resource)
            stage_times["local_hash"] = (time.monotonic() - t0) * 1000

            # Stage 1: Fetch
            await self._events.emit(ResourceFetchStarted(resource_name=resource.name))
            t0 = time.monotonic()
            fetch_result = await pipeline.source.fetch(resource, ctx)
            stage_times["fetch"] = (time.monotonic() - t0) * 1000
            await self._events.emit(ResourceFetchCompleted(
                resource_name=resource.name, bytes_downloaded=fetch_result.content_length or 0,
            ))
            stream = fetch_result.stream

            # Check for 304 Not Modified (ETag/Last-Modified cache hit)
            if fetch_result.not_modified:
                await self._events.emit(
                    ResourceRemoteUnchanged(resource_name=resource.name)
                )
                await self._events.emit(ResourceSkipped(resource_name=resource.name))
                return ResourceResult(
                    resource_name=resource.name,
                    status=SyncStatus.SKIPPED,
                    local_hash=local_hash,
                    remote_hash=None,
                    stage_times=stage_times,
                    dry_run=bool(ctx.config.get("dry_run", False)),
                )

            # Stage 2-3: Validate + Transform (wrap with timing)
            for stage_name, stages in [
                ("validate", pipeline.validators),
                ("transform", pipeline.transforms),
            ]:
                for stage_fn in stages:
                    stream = _TimedStreamWrapper(
                        stream, stage_fn, resource, ctx, stage_name,
                        stage_times,
                    )

            # Stage 4: Hash (tee'd — computed as stream is consumed)
            hasher = hashlib.new(resource.algorithm.value)
            stream = tee_stream(stream, lambda c: hasher.update(c))

            # Stage 5: Sink (consume the stream, writing to temp file)
            if pipeline.sink is not None:
                t0 = time.monotonic()
                write_result = await pipeline.sink.write(stream, resource, ctx)
                stage_times["sink"] = (time.monotonic() - t0) * 1000
            else:
                await drain_stream(stream)
                write_result = None

            # Now the hasher has processed all chunks — finalize
            remote_hash = HashResult(
                algorithm=resource.algorithm,
                hex_digest=hasher.hexdigest(),
            )

            # Stage 6: Compare hashes and determine status
            if local_hash is not None and local_hash.matches(remote_hash):
                # Hash matches — file unchanged. Discard the temp file.
                self._discard_temp(pipeline, resource, ctx)
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
                    dry_run=bool(ctx.config.get("dry_run", False)),
                )

            # Content changed — commit the temp file
            self._commit_temp(pipeline, resource, ctx)

            status = SyncStatus.CREATED if local_hash is None else SyncStatus.UPDATED
            await self._events.emit(
                ResourceWritten(
                    resource_name=resource.name,
                    path=str(resource.path),
                    bytes_written=(
                        write_result.bytes_written if write_result else 0
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
                dry_run=bool(ctx.config.get("dry_run", False)),
            )

        except Exception as e:
            # Ensure temp file is cleaned up on error
            self._discard_temp(pipeline, resource, ctx)
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
                dry_run=bool(ctx.config.get("dry_run", False)),
            )

    async def _compute_local_hash(self, resource: Resource) -> HashResult | None:
        """Compute the hash of the local file if it exists.

        Runs in a thread pool executor to avoid blocking the event loop
        on disk I/O for large files.
        """
        target = Path(resource.path)
        if not target.exists():
            return None

        loop = asyncio.get_running_loop()
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
    def _commit_temp(pipeline: Pipeline, resource: Resource, ctx: PipelineContext) -> None:
        """Commit the temp file to the target path.

        Delegates to the sink's commit() method. All sinks support
        two-phase commit via the StreamSink protocol.
        """
        sink = pipeline.sink
        if sink is not None:
            sink.commit()

    @staticmethod
    def _discard_temp(pipeline: Pipeline, resource: Resource, ctx: PipelineContext) -> None:
        """Discard the temp file if any.

        Safe to call even if no temp file exists. Delegates to the
        sink's discard() method via the StreamSink protocol.
        """
        sink = pipeline.sink
        if sink is not None:
            sink.discard()


def _extract_stage_name(stage_fn: StreamTransformer) -> str:
    """Extract a human-readable name from a stage function.

    For bound methods (e.g. validator_instance._validate), returns the
    class name (e.g. 'EmptyValidator'). For regular functions, returns
    the function name.
    """
    owner = getattr(stage_fn, "__self__", None)
    if owner is not None:
        return type(owner).__name__

    name = getattr(stage_fn, "__name__", None)
    if isinstance(name, str):
        return name

    return type(stage_fn).__name__


class _TimedStreamWrapper:
    """Wraps a stream with a stage function, measuring actual execution time.

    Validator/transform functions are async generators — they don't
    execute until the stream is consumed. This wrapper measures the
    actual time spent processing chunks in the wrapped stage.
    """

    def __init__(
        self,
        stream: Stream,
        stage_fn: StreamTransformer,
        resource: Resource,
        ctx: PipelineContext,
        stage_name: str,
        stage_times: dict[str, float],
    ) -> None:
        self._stream = stream
        self._stage_fn = stage_fn
        self._resource = resource
        self._ctx = ctx
        self._stage_name = stage_name
        self._stage_times = stage_times
        self._fn_name = _extract_stage_name(stage_fn)
        # Cache the async generator so multiple __aiter__ calls (e.g. when
        # HtmlErrorValidator iterates the same stream in two phases: first to
        # fill the head buffer, then to forward the rest) share the same
        # underlying generator. Without this, the second __aiter__ call would
        # create a fresh generator over an already-exhausted underlying stream.
        self._cached_aiter: Stream | None = None

    def __aiter__(self) -> Stream:
        if self._cached_aiter is None:
            self._cached_aiter = self._aiter_impl()
        return self._cached_aiter

    async def _aiter_impl(self) -> Stream:
        t0 = time.monotonic()
        processed = self._stage_fn(self._stream, self._resource, self._ctx)
        # Measure time spent consuming the processed stream
        async for chunk in processed:
            yield chunk
        elapsed = (time.monotonic() - t0) * 1000
        key = f"{self._stage_name}.{self._fn_name}"
        self._stage_times[key] = elapsed