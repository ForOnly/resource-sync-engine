"""Tests for LocalSink — two-phase commit write."""

from __future__ import annotations

from pathlib import Path

import pytest

from resource_sync.domain.models import Resource, HashAlgorithm
from resource_sync.sink.local import LocalSink
from tests.conftest import bytes_stream


class TestLocalSink:
    """LocalSink — two-phase commit lifecycle."""

    @pytest.fixture
    def resource(self, tmp_path: Path) -> Resource:
        return Resource(
            name="test",
            url="https://example.com/f",
            path=str(tmp_path / "output.json"),
            algorithm=HashAlgorithm.SHA256,
        )

    @pytest.mark.asyncio
    async def test_write_creates_temp_file(self, resource: Resource, pipeline_context) -> None:
        """Write creates a temp file but not the target file."""
        sink = LocalSink()
        stream = bytes_stream(b'{"key": "value"}')
        result = await sink.write(stream, resource, pipeline_context)

        assert result.path == str(resource.path)
        assert result.bytes_written == 16
        assert result.hash_value is not None
        # Target file should NOT exist yet
        assert not Path(resource.path).exists()
        # Temp file should exist
        assert sink._temp_path is not None
        assert sink._temp_path.exists()

        # Clean up
        sink.discard()

    @pytest.mark.asyncio
    async def test_commit_moves_file(self, resource: Resource, pipeline_context) -> None:
        """Commit moves temp file to target path."""
        sink = LocalSink()
        stream = bytes_stream(b"test content")
        await sink.write(stream, resource, pipeline_context)

        assert not Path(resource.path).exists()
        assert sink.commit() is True
        # Target file should now exist
        assert Path(resource.path).exists()
        assert Path(resource.path).read_text() == "test content"

    @pytest.mark.asyncio
    async def test_discard_deletes_temp(self, resource: Resource, pipeline_context) -> None:
        """Discard deletes the temp file without writing to target."""
        sink = LocalSink()
        stream = bytes_stream(b"test content")
        await sink.write(stream, resource, pipeline_context)

        temp_path = sink._temp_path
        assert temp_path is not None
        assert temp_path.exists()
        assert sink.discard() is True
        assert not temp_path.exists()
        assert not Path(resource.path).exists()

    def test_commit_without_write(self) -> None:
        """Commit without a prior write should return False."""
        sink = LocalSink()
        assert sink.commit() is False

    def test_discard_without_write(self) -> None:
        """Discard without a prior write should return False."""
        sink = LocalSink()
        assert sink.discard() is False

    @pytest.mark.asyncio
    async def test_double_discard_safe(self, resource: Resource, pipeline_context) -> None:
        """Double discard should be safe (second call returns False)."""
        sink = LocalSink()
        stream = bytes_stream(b"test")
        await sink.write(stream, resource, pipeline_context)
        assert sink.discard() is True
        assert sink.discard() is False