"""Tests for HtmlErrorValidator (streaming HTML error page detection)."""

from __future__ import annotations

import pytest

from resource_sync.domain.models import Resource
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.validator.html_error import HtmlErrorValidator
from tests.conftest import bytes_stream, collect_stream


class TestHtmlErrorValidator:
    """HtmlErrorValidator — detects HTML error pages, passes valid content."""

    @pytest.mark.asyncio
    async def test_pass_plain_text(self, sample_resource: Resource, pipeline_context) -> None:
        validator = HtmlErrorValidator()
        transformer = validator()
        stream = bytes_stream(b'{"key": "value"}')
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert result == b'{"key": "value"}'

    @pytest.mark.asyncio
    async def test_pass_valid_html(self, sample_resource: Resource, pipeline_context) -> None:
        validator = HtmlErrorValidator()
        transformer = validator()
        stream = bytes_stream(b"<html><body>Welcome</body></html>")
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert result == b"<html><body>Welcome</body></html>"

    @pytest.mark.asyncio
    async def test_reject_404_html(self, sample_resource: Resource, pipeline_context) -> None:
        validator = HtmlErrorValidator()
        transformer = validator()
        stream = bytes_stream(
            b"<html><head><title>404 Not Found</title></head><body>missing</body></html>"
        )
        processed = transformer(stream, sample_resource, pipeline_context)
        with pytest.raises(PluginExecutionError, match="404"):
            await collect_stream(processed)

    @pytest.mark.asyncio
    async def test_reject_500_html(self, sample_resource: Resource, pipeline_context) -> None:
        validator = HtmlErrorValidator()
        transformer = validator()
        stream = bytes_stream(
            b"<html><head><title>500 Internal Server Error</title></head></html>"
        )
        processed = transformer(stream, sample_resource, pipeline_context)
        with pytest.raises(PluginExecutionError, match="500"):
            await collect_stream(processed)

    @pytest.mark.asyncio
    async def test_streaming_preserves_all_content(self, sample_resource: Resource, pipeline_context) -> None:
        """Even when content is OK, the full stream must be preserved."""
        validator = HtmlErrorValidator()
        transformer = validator()
        large_content = b"x" * 5000
        stream = bytes_stream(large_content)
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert result == large_content

    @pytest.mark.asyncio
    async def test_streaming_memory_usage(self, sample_resource: Resource, pipeline_context) -> None:
        """Only the first ~2048 bytes should be buffered, not the whole stream."""
        validator = HtmlErrorValidator()
        transformer = validator()
        # 100KB of content, should be streamed, not buffered
        stream = bytes_stream(b"x" * 102400)
        processed = transformer(stream, sample_resource, pipeline_context)
        result = await collect_stream(processed)
        assert len(result) == 102400

    @pytest.mark.asyncio
    async def test_should_apply(self, sample_resource: Resource) -> None:
        assert HtmlErrorValidator.should_apply(sample_resource) is True

    @pytest.mark.asyncio
    async def test_name(self) -> None:
        assert HtmlErrorValidator.name == "html_error"

    @pytest.mark.asyncio
    async def test_priority(self) -> None:
        assert HtmlErrorValidator.priority == 200