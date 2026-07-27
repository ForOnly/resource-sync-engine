"""Tests for stream utilities (CancellationToken, tee_stream, drain_stream)."""

from __future__ import annotations

import asyncio

import pytest

from resource_sync.domain.stream import CancellationToken, drain_stream, tee_stream
from tests.conftest import bytes_stream, collect_stream


class TestCancellationToken:
    """CancellationToken lifecycle."""

    @pytest.mark.asyncio
    async def test_initial_state(self) -> None:
        token = CancellationToken()
        assert not token.cancelled

    @pytest.mark.asyncio
    async def test_cancel(self) -> None:
        token = CancellationToken()
        token.cancel()
        assert token.cancelled

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        token = CancellationToken()
        token.cancel()
        assert token.cancelled
        token.reset()
        assert not token.cancelled

    @pytest.mark.asyncio
    async def test_child_token(self) -> None:
        parent = CancellationToken()
        child = parent.child()
        assert not child.cancelled
        assert not parent.cancelled
        parent.cancel()
        assert child.cancelled
        assert parent.cancelled

    @pytest.mark.asyncio
    async def test_child_cancel_propagates_to_parent(self) -> None:
        """Cancelling a child propagates up to the parent (cascading)."""
        parent = CancellationToken()
        child = parent.child()
        child.cancel()
        assert child.cancelled
        assert parent.cancelled

    @pytest.mark.asyncio
    async def test_wait(self) -> None:
        token = CancellationToken()

        async def delayed_cancel():
            await asyncio.sleep(0.01)
            token.cancel()

        asyncio.create_task(delayed_cancel())
        await token.wait()
        assert token.cancelled


class TestTeeStream:
    """tee_stream — side-effect callback without consuming the stream."""

    @pytest.mark.asyncio
    async def test_tee_preserves_content(self) -> None:
        """tee_stream should preserve all content through the stream."""
        collected: list[bytes] = []
        stream = bytes_stream(b"hello ", b"world")
        tee = tee_stream(stream, lambda c: collected.append(c))
        result = await collect_stream(tee)
        assert result == b"hello world"
        assert collected == [b"hello ", b"world"]

    @pytest.mark.asyncio
    async def test_tee_empty_stream(self) -> None:
        """tee_stream with empty stream should call callback zero times."""
        collected: list[bytes] = []
        stream = bytes_stream()
        tee = tee_stream(stream, lambda c: collected.append(c))
        result = await collect_stream(tee)
        assert result == b""
        assert collected == []

    @pytest.mark.asyncio
    async def test_tee_multiple_chunks(self) -> None:
        """tee_stream should call the callback for each chunk."""
        lengths: list[int] = []
        stream = bytes_stream(b"a", b"bc", b"def")
        tee = tee_stream(stream, lambda c: lengths.append(len(c)))
        await collect_stream(tee)
        assert lengths == [1, 2, 3]


class TestDrainStream:
    """drain_stream — consume a stream without storing it."""

    @pytest.mark.asyncio
    async def test_drain_empty(self) -> None:
        stream = bytes_stream()
        await drain_stream(stream)  # Should not raise

    @pytest.mark.asyncio
    async def test_drain_small(self) -> None:
        stream = bytes_stream(b"hello")
        await drain_stream(stream)  # Should not raise

    @pytest.mark.asyncio
    async def test_drain_large(self) -> None:
        stream = bytes_stream(b"a" * 1000, b"b" * 1000, b"c" * 1000)
        await drain_stream(stream)  # Should not raise