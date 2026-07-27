"""Tests for EmptyValidator."""

from __future__ import annotations

import pytest

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import Stream
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.validator.empty import EmptyValidator
from tests.conftest import bytes_stream, collect_stream


class TestEmptyValidator:
    """EmptyValidator — rejects empty streams, passes non-empty."""

    @pytest.mark.asyncio
    async def test_pass_non_empty(self, sample_resource: Resource, pipeline_context) -> None:
        validator = EmptyValidator()
        transformer = validator()
        stream = bytes_stream(b"some content")
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert result == b"some content"

    @pytest.mark.asyncio
    async def test_reject_empty(self, sample_resource: Resource, pipeline_context) -> None:
        validator = EmptyValidator()
        transformer = validator()
        stream = bytes_stream()  # empty stream
        processed = transformer(stream, sample_resource, pipeline_context)
        with pytest.raises(PluginExecutionError, match="empty"):
            await collect_stream(processed)

    @pytest.mark.asyncio
    async def test_should_apply(self, sample_resource: Resource) -> None:
        assert EmptyValidator.should_apply(sample_resource) is True

    @pytest.mark.asyncio
    async def test_name(self) -> None:
        assert EmptyValidator.name == "empty"

    @pytest.mark.asyncio
    async def test_priority(self) -> None:
        assert EmptyValidator.priority == 100