"""Core decision-path tests for PipelineExecutor.execute."""

from __future__ import annotations

from pathlib import Path

import pytest

from resource_sync.domain.events import Event
from resource_sync.domain.models import Resource, SyncStatus
from resource_sync.domain.pipeline import Pipeline
from resource_sync.domain.stream import (
    CancellationToken,
    FetchResult,
    PipelineContext,
    Stream,
    WriteResult,
    chunked_source,
)
from resource_sync.engine.executor import PipelineExecutor
from resource_sync.eventbus.memory import EventBus


class _Source:
    def __init__(self, data: bytes, not_modified: bool = False) -> None:
        self._data = data
        self._not_modified = not_modified

    async def fetch(self, resource: Resource, ctx: PipelineContext) -> FetchResult:
        return FetchResult(
            stream=chunked_source(self._data, chunk_size=3),
            content_length=len(self._data),
            not_modified=self._not_modified,
        )


class _Sink:
    def __init__(self) -> None:
        self.content = bytearray()
        self.committed = False
        self.discarded = False

    async def write(
        self,
        stream: Stream,
        resource: Resource,
        ctx: PipelineContext,
    ) -> WriteResult:
        async for chunk in stream:
            self.content.extend(chunk)
        return WriteResult(path=str(resource.path), bytes_written=len(self.content))

    def commit(self) -> bool:
        self.committed = True
        return True

    def discard(self) -> bool:
        self.discarded = True
        return True


class _Observer:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_event(self, event: Event) -> None:
        self.events.append(type(event).__name__)


def _resource(path: Path) -> Resource:
    return Resource(
        name="rules",
        url="https://example.com/rules.txt",
        path=path,
    )


@pytest.mark.asyncio
async def test_execute_creates_missing_resource(tmp_path: Path) -> None:
    event_bus = EventBus()
    observer = _Observer()
    event_bus.register_observer(observer)
    executor = PipelineExecutor(event_bus)
    resource = _resource(tmp_path / "rules.txt")
    sink = _Sink()

    result = await executor.execute(
        Pipeline(source=_Source(b"new rules"), sink=sink),
        resource,
        CancellationToken(),
    )

    assert result.status is SyncStatus.CREATED
    assert bytes(sink.content) == b"new rules"
    assert sink.committed is True
    assert sink.discarded is False
    assert "ResourceWritten" in observer.events
    assert "ResourceHashCompared" in observer.events


@pytest.mark.asyncio
async def test_execute_discards_unchanged_resource(tmp_path: Path) -> None:
    target = tmp_path / "rules.txt"
    target.write_bytes(b"same rules")
    resource = _resource(target)
    sink = _Sink()
    executor = PipelineExecutor(EventBus())

    result = await executor.execute(
        Pipeline(source=_Source(b"same rules"), sink=sink),
        resource,
        CancellationToken(),
    )

    assert result.status is SyncStatus.SKIPPED
    assert result.local_hash == result.remote_hash
    assert sink.committed is False
    assert sink.discarded is True


@pytest.mark.asyncio
async def test_execute_skips_sink_for_not_modified(tmp_path: Path) -> None:
    target = tmp_path / "rules.txt"
    target.write_bytes(b"existing")
    resource = _resource(target)
    sink = _Sink()
    executor = PipelineExecutor(EventBus())

    result = await executor.execute(
        Pipeline(source=_Source(b"", not_modified=True), sink=sink),
        resource,
        CancellationToken(),
    )

    assert result.status is SyncStatus.SKIPPED
    assert sink.content == bytearray()
    assert sink.committed is False
    assert sink.discarded is False


@pytest.mark.asyncio
async def test_execute_reports_validator_failure(tmp_path: Path) -> None:
    async def reject(
        stream: Stream,
        resource: Resource,
        ctx: PipelineContext,
    ) -> Stream:
        raise ValueError("invalid content")
        if False:
            yield b""

    event_bus = EventBus()
    observer = _Observer()
    event_bus.register_observer(observer)
    resource = _resource(tmp_path / "rules.txt")
    sink = _Sink()
    executor = PipelineExecutor(event_bus)

    result = await executor.execute(
        Pipeline(
            source=_Source(b"bad"),
            validators=(reject,),
            sink=sink,
        ),
        resource,
        CancellationToken(),
    )

    assert result.status is SyncStatus.ERROR
    assert result.error_message == "ValueError: invalid content"
    assert sink.discarded is True
    assert "ResourceFailed" in observer.events
