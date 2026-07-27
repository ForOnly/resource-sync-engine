"""HTTP/HTTPS fetcher — streaming download with connection pooling."""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

import httpx

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import (
    CancellationToken,
    FetchResult,
    PipelineContext,
    Stream,
    StreamSource,
)
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.plugin.registry import register_fetcher

_LOGGER = logging.getLogger(__name__)

# Shared connection pool — all HttpFetcher instances share this transport
_shared_transport: httpx.AsyncHTTPTransport | None = None


def _get_shared_transport() -> httpx.AsyncHTTPTransport:
    """Get or create the shared HTTP connection pool."""
    global _shared_transport
    if _shared_transport is None:
        _shared_transport = httpx.AsyncHTTPTransport(
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=100,
            ),
        )
    return _shared_transport


@register_fetcher(schemes=frozenset({"http", "https"}))
class HttpFetcher:
    """Streaming HTTP/HTTPS fetcher with connection pooling.

    All instances share a single connection pool, maximizing connection
    reuse across concurrent downloads.
    """

    def __init__(self, timeout: float = 30.0, max_retries: int = 3) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            transport=_get_shared_transport(),
        )

    @classmethod
    def configure(cls, resource: Resource) -> StreamSource:
        """Create an HttpFetcher from a resource definition."""
        return cls(timeout=resource.timeout, max_retries=resource.retry)

    async def fetch(self, resource: Resource, ctx: PipelineContext) -> FetchResult:
        """Fetch a resource via HTTP(S) and return a streaming result.

        The response stream is kept alive until the pipeline consumes it.
        Uses httpx.send() with stream=True to avoid closing the response
        on return.
        """
        headers = dict(resource.headers) if resource.headers else {}
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            if ctx.cancel.cancelled:
                raise asyncio.CancelledError()

            try:
                request = self._client.build_request(
                    "GET", resource.url, headers=headers
                )
                response = await self._client.send(request, stream=True)

                # Pre-check content-length to avoid large downloads
                cl = response.headers.get("content-length")
                if cl and int(cl) > resource.max_size:
                    await response.aclose()
                    raise PluginExecutionError(
                        f"Content-Length {cl} exceeds max_size {resource.max_size}"
                    )

                # Check HTTP status
                if response.status_code >= 400:
                    body = await response.aread()
                    await response.aclose()
                    raise PluginExecutionError(
                        f"HTTP {response.status_code}: "
                        f"{body[:200].decode(errors='replace')}"
                    )

                return FetchResult(
                    stream=self._wrap_stream(response, ctx.cancel),
                    content_type=response.headers.get("content-type"),
                    content_length=int(cl) if cl else None,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )

            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_exc = e
                if attempt < self._max_retries:
                    wait = 2.0 ** attempt  # Exponential backoff
                    await asyncio.sleep(wait)
                continue

        raise PluginExecutionError(
            f"Failed after {self._max_retries} attempts"
        ) from last_exc

    async def _wrap_stream(
        self,
        response: httpx.Response,
        cancel: CancellationToken,
    ) -> Stream:
        """Wrap httpx streaming response, handling cancellation and cleanup."""
        try:
            async for chunk in response.aiter_bytes():
                if cancel.cancelled:
                    raise asyncio.CancelledError()
                yield chunk
        finally:
            await response.aclose()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()