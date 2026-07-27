"""Tests for SizeValidator."""

from __future__ import annotations

import pytest

from resource_sync.domain.models import Resource
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.validator.size import SizeValidator
from tests.conftest import bytes_stream, collect_stream


class TestSizeValidator:
    """SizeValidator — rejects content exceeding max_size."""

    @pytest.mark.asyncio
    async def test_pass_under_limit(self, sample_resource: Resource, pipeline_context) -> None:
        """Content under max_size should pass through."""
        validator = SizeValidator()
        transformer = validator()
        # sample_resource has max_size=1MB, so 100 bytes is fine
        stream = bytes_stream(b"x" * 100)
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert result == b"x" * 100

    @pytest.mark.asyncio
    async def test_reject_over_limit(self, sample_resource: Resource, pipeline_context) -> None:
        """Content over max_size should be rejected."""
        validator = SizeValidator()
        transformer = validator()
        # sample_resource has max_size=1MB, exceed it
        stream = bytes_stream(b"x" * (1024 * 1024 + 1))
        processed = transformer(stream, sample_resource, pipeline_context)
        with pytest.raises(PluginExecutionError, match="max_size"):
            await collect_stream(processed)

    @pytest.mark.asyncio
    async def test_zero_max_size_skips(self, sample_resource_no_size: Resource, pipeline_context) -> None:
        """max_size=0 means no limit — should_apply returns False."""
        assert SizeValidator.should_apply(sample_resource_no_size) is False

    @pytest.mark.asyncio
    async def test_exact_limit(self, sample_resource: Resource, pipeline_context) -> None:
        """Content exactly at max_size should pass."""
        validator = SizeValidator()
        transformer = validator()
        stream = bytes_stream(b"x" * (1024 * 1024))
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert len(result) == 1024 * 1024

    @pytest.mark.asyncio
    async def test_name(self) -> None:
        assert SizeValidator.name == "size"

    @pytest.mark.asyncio
    async def test_priority(self) -> None:
        assert SizeValidator.priority == 300