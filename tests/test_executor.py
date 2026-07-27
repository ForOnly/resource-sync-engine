"""Tests for PipelineExecutor and _TimedStreamWrapper."""

from __future__ import annotations

import pytest

from resource_sync.domain.models import Resource, HashAlgorithm
from resource_sync.domain.stream import CancellationToken, PipelineContext
from resource_sync.engine.executor import _TimedStreamWrapper, _extract_stage_name
from tests.conftest import bytes_stream, collect_stream


class TestTimedStreamWrapper:
    """_TimedStreamWrapper — stream wrapping with timing."""

    @pytest.fixture
    def resource(self) -> Resource:
        return Resource(
            name="test",
            url="https://example.com/f",
            path="/tmp/f",
            algorithm=HashAlgorithm.SHA256,
        )

    @pytest.fixture
    def ctx(self, resource: Resource) -> PipelineContext:
        return PipelineContext(
            resource=resource,
            cancel=CancellationToken(),
            env={},
            config={},
        )

    @pytest.mark.asyncio
    async def test_passthrough(self, resource: Resource, ctx: PipelineContext) -> None:
        """Wrapper should pass through all chunks unchanged."""
        stage_times = {}
        stream = bytes_stream(b"hello ", b"world")

        async def identity(s, r, c):
            async for chunk in s:
                yield chunk

        wrapped = _TimedStreamWrapper(stream, identity, resource, ctx, "test", stage_times)
        result = await collect_stream(wrapped)
        assert result == b"hello world"
        assert "test.identity" in stage_times

    @pytest.mark.asyncio
    async def test_multiple_aiter_calls_share_generator(
        self, resource: Resource, ctx: PipelineContext,
    ) -> None:
        """Multiple __aiter__ calls should share the same underlying generator.

        This is critical for validators like HtmlErrorValidator that
        iterate the same stream in two phases: first to fill a head
        buffer, then to forward the remaining chunks.
        """
        stage_times = {}
        counter = 0

        async def counting_gen(s, r, c):
            nonlocal counter
            async for chunk in s:
                counter += 1
                yield chunk

        stream = bytes_stream(b"a", b"b", b"c")
        wrapped = _TimedStreamWrapper(stream, counting_gen, resource, ctx, "test", stage_times)

        # First iteration: consume all chunks
        result1 = await collect_stream(wrapped)
        assert result1 == b"abc"
        assert counter == 3

        # Second iteration through __aiter__: should use the cached generator,
        # which is already exhausted, so no more chunks.
        result2 = await collect_stream(wrapped)
        assert result2 == b""  # generator already exhausted
        assert counter == 3  # counter should not increase

    @pytest.mark.asyncio
    async def test_two_phase_iteration(
        self, resource: Resource, ctx: PipelineContext,
    ) -> None:
        """Simulate HtmlErrorValidator's two-phase iteration pattern.

        Phase 1: consume chunks until a threshold, then break.
        Phase 2: consume remaining chunks via a second async for loop.
        """
        stage_times = {}
        # A simulated validator that reads in two phases
        async def two_phase_reader(s, r, c):
            head = b""
            # Phase 1: consume until we have enough
            async for chunk in s:
                head += chunk
                if len(head) >= 3:
                    break
            yield head
            # Phase 2: consume the rest
            async for chunk in s:
                yield chunk

        stream = bytes_stream(b"ab", b"cd", b"ef")
        wrapped = _TimedStreamWrapper(stream, two_phase_reader, resource, ctx, "test", stage_times)

        # Simulate a downstream validator that reads the wrapper
        async def downstream(s, r, c):
            async for chunk in s:
                yield chunk

        result = await collect_stream(downstream(wrapped, resource, ctx))
        # All content should be preserved
        assert result == b"abcdef"


class TestExtractStageName:
    """_extract_stage_name — human-readable stage function names."""

    class FakeValidator:
        async def validate(self, s, r, c):
            yield b""

    def test_bound_method(self) -> None:
        """Bound methods should return the class name."""
        v = self.FakeValidator()
        name = _extract_stage_name(v.validate)
        assert name == "FakeValidator"

    def test_regular_function(self) -> None:
        """Regular functions should return the function name."""
        async def my_func(s, r, c):
            yield b""
        name = _extract_stage_name(my_func)
        assert name == "my_func"

    def test_lambda(self) -> None:
        """Lambdas should fall back to a reasonable name."""
        name = _extract_stage_name(lambda s, r, c: None)
        assert name is not None