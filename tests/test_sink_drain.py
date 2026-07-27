"""Tests for DrainSink — no-op dry-run sink."""

from __future__ import annotations

import pytest

from resource_sync.sink.drain import DrainSink, create_drain_sink
from tests.conftest import bytes_stream


class TestDrainSink:
    """DrainSink — consumes stream without persisting."""

    @pytest.mark.asyncio
    async def test_drain_consumes_stream(self, sample_resource: Resource, pipeline_context) -> None:
        sink = create_drain_sink()
        stream = bytes_stream(b"some content")
        result = await sink.write(stream, sample_resource, pipeline_context)
        assert result.bytes_written == 12
        assert result.hash_value is None

    @pytest.mark.asyncio
    async def test_drain_empty(self, sample_resource: Resource, pipeline_context) -> None:
        sink = create_drain_sink()
        stream = bytes_stream()
        result = await sink.write(stream, sample_resource, pipeline_context)
        assert result.bytes_written == 0

    @pytest.mark.asyncio
    async def test_drain_sink_class(self, sample_resource: Resource, pipeline_context) -> None:
        sink = DrainSink()
        stream = bytes_stream(b"data")
        result = await sink.write(stream, sample_resource, pipeline_context)
        assert result.bytes_written == 4