"""Core stream types — the foundation of the streaming pipeline architecture.

The entire system is built on the concept of data as a stream of bytes.
Each processing stage is a transformation on the stream, allowing
O(chunk_size) memory usage regardless of file size.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from resource_sync.domain.models import Resource

# ─── Stream type alias ───
Stream = AsyncIterator[bytes]
"""A stream of bytes — the fundamental data type of the pipeline."""


# ─── Cancellation ───

class CancellationToken:
    """Cooperative cancellation token propagated through the pipeline.

    Once cancelled, a token should typically be discarded rather than
    reset. The reset() method is provided for testing and for
    token-reuse scenarios where the same pipeline structure runs
    multiple times.
    """

    def __init__(self, parent: CancellationToken | None = None) -> None:
        self._parent = parent
        self._cancelled = False
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled = True
        self._event.set()
        if self._parent is not None:
            self._parent.cancel()

    def reset(self) -> None:
        """Reset the token to the uncancelled state.

        Does NOT reset parent tokens. Call with care — prefer creating
        a fresh token via child() or CancellationToken() instead.
        """
        self._cancelled = False
        self._event = asyncio.Event()

    @property
    def cancelled(self) -> bool:
        if self._cancelled:
            return True
        if self._parent is not None:
            return self._parent.cancelled
        return False

    async def wait(self) -> None:
        await self._event.wait()

    def child(self) -> CancellationToken:
        return CancellationToken(parent=self)


# ─── Pipeline context ───

@dataclass(frozen=True)
class PipelineContext:
    """Execution context carried through the pipeline."""
    resource: Resource
    cancel: CancellationToken
    env: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


# ─── Fetch / Write results ───

@dataclass(frozen=True)
class FetchResult:
    """Result of a fetch operation — stream plus metadata."""
    stream: Stream
    content_type: str | None = None
    content_length: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    not_modified: bool = False
    """True when the server returned 304 Not Modified (ETag/Last-Modified match)."""


@dataclass(frozen=True)
class WriteResult:
    """Result of a write operation."""
    path: str
    bytes_written: int
    hash_value: str | None = None


# ─── Pipeline protocols ───

class StreamTransformer(Protocol):
    """Protocol for a stream transformer — receives a stream, returns a stream."""
    def __call__(
        self,
        stream: Stream,
        resource: Resource,
        ctx: PipelineContext,
    ) -> Stream: ...


class StreamSource(Protocol):
    """Protocol for a data source — produces a stream."""
    async def fetch(
        self,
        resource: Resource,
        ctx: PipelineContext,
    ) -> FetchResult: ...


class StreamSink(Protocol):
    """Protocol for a data sink — consumes a stream and supports two-phase commit.

    The two-phase commit pattern allows the executor to:
    1. write()  — stream data to a temporary location
    2. commit() — finalize (atomically move temp → target) if content changed
    3. discard() — delete the temp data if content is unchanged or on error
    """
    async def write(
        self,
        stream: Stream,
        resource: Resource,
        ctx: PipelineContext,
    ) -> WriteResult: ...

    def commit(self) -> bool:
        """Commit the pending write. Returns True on success."""
        ...

    def discard(self) -> bool:
        """Discard the pending write. Returns True on success."""
        ...


# ─── Utilities ───

async def tee_stream(
    stream: Stream,
    side_channel: Callable[[bytes], None],
) -> Stream:
    """Split a stream: pass through chunks while feeding a side channel."""
    async for chunk in stream:
        side_channel(chunk)
        yield chunk


async def drain_stream(stream: Stream) -> None:
    """Consume and discard a stream."""
    async for _ in stream:
        pass


async def collect_stream(stream: Stream) -> bytes:
    """Collect all chunks from a stream into a single bytes object."""
    chunks: list[bytes] = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


async def chunked_source(data: bytes, chunk_size: int = 65536) -> Stream:
    """Convert bytes into a stream of fixed-size chunks."""
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]