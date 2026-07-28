"""Behavior tests for the streaming HTTP fetcher."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

import resource_sync.fetcher.http as http_module
from resource_sync.domain.models import Resource
from resource_sync.domain.stream import CancellationToken, PipelineContext
from resource_sync.fetcher.http import HttpFetcher
from resource_sync.plugin.errors import PluginExecutionError
from tests.conftest import collect_stream


def _resource(max_size: int = 1024) -> Resource:
    return Resource(
        name="rules",
        url="https://example.com/rules.txt",
        path="/tmp/rules.txt",
        max_size=max_size,
    )


def _context(resource: Resource) -> PipelineContext:
    return PipelineContext(resource=resource, cancel=CancellationToken())


def _fetcher(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> HttpFetcher:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(http_module, "_get_shared_transport", lambda: transport)
    monkeypatch.setattr(http_module, "_etag_cache", None)
    return HttpFetcher(timeout=1.0, max_retries=1)


@pytest.mark.asyncio
async def test_fetch_streams_successful_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "11", "etag": '"v1"'},
            content=b"hello world",
            request=request,
        )

    fetcher = _fetcher(monkeypatch, handler)
    resource = _resource()
    try:
        result = await fetcher.fetch(resource, _context(resource))
        content = await collect_stream(result.stream)
    finally:
        await fetcher.close()

    assert content == b"hello world"
    assert result.content_length == 11
    assert result.etag == '"v1"'
    assert result.not_modified is False


@pytest.mark.asyncio
async def test_fetch_returns_not_modified_for_304(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, request=request)

    fetcher = _fetcher(monkeypatch, handler)
    resource = _resource()
    try:
        result = await fetcher.fetch(resource, _context(resource))
        content = await collect_stream(result.stream)
    finally:
        await fetcher.close()

    assert result.not_modified is True
    assert content == b""


@pytest.mark.asyncio
async def test_fetch_rejects_content_length_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "20"},
            content=b"x" * 20,
            request=request,
        )

    fetcher = _fetcher(monkeypatch, handler)
    resource = _resource(max_size=10)
    try:
        with pytest.raises(PluginExecutionError, match="exceeds max_size"):
            await fetcher.fetch(resource, _context(resource))
    finally:
        await fetcher.close()


@pytest.mark.asyncio
async def test_fetch_raises_for_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"unavailable", request=request)

    fetcher = _fetcher(monkeypatch, handler)
    resource = _resource()
    try:
        with pytest.raises(PluginExecutionError, match="HTTP 503"):
            await fetcher.fetch(resource, _context(resource))
    finally:
        await fetcher.close()
