"""Shared test fixtures and helpers."""

from __future__ import annotations

import pytest

from resource_sync.domain.models import Resource, ResourceResult, SyncReport, SyncStatus, HashAlgorithm, HashResult
from resource_sync.domain.stream import CancellationToken, PipelineContext, Stream


# ─── Fixtures ───


@pytest.fixture
def sample_resource() -> Resource:
    return Resource(
        name="test-resource",
        url="https://example.com/data.json",
        path="/tmp/test-resource.json",
        algorithm=HashAlgorithm.SHA256,
        max_size=1024 * 1024,
        headers={"Authorization": "Bearer test-token"},
    )


@pytest.fixture
def sample_resource_no_size() -> Resource:
    return Resource(
        name="test-resource-no-size",
        url="https://example.com/data.json",
        path="/tmp/test-resource-no-size.json",
        algorithm=HashAlgorithm.SHA256,
        max_size=0,
    )


@pytest.fixture
def cancel_token() -> CancellationToken:
    return CancellationToken()


@pytest.fixture
def pipeline_context(sample_resource: Resource, cancel_token: CancellationToken) -> PipelineContext:
    return PipelineContext(
        resource=sample_resource,
        cancel=cancel_token,
        env={},
        config={"dry_run": False},
    )


# ─── Stream helpers ───


async def bytes_stream(*chunks: bytes) -> Stream:
    """Create a stream from byte chunks."""
    for chunk in chunks:
        yield chunk


async def collect_stream(stream: Stream) -> bytes:
    """Collect all chunks from a stream into bytes."""
    result = bytearray()
    async for chunk in stream:
        result.extend(chunk)
    return bytes(result)


# ─── Assertion helpers ───


def assert_result_status(
    report: SyncReport,
    resource_name: str,
    expected_status: SyncStatus,
) -> None:
    """Assert that a specific resource result has the expected status."""
    for result in report.results:
        if result.resource_name == resource_name:
            assert result.status == expected_status, (
                f"Expected {resource_name} to be {expected_status.value}, "
                f"got {result.status.value}"
            )
            return
    pytest.fail(f"Resource '{resource_name}' not found in report results")