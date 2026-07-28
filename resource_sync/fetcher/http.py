"""HTTP/HTTPS fetcher — streaming download with connection pooling."""

from __future__ import annotations

import asyncio
import logging

import httpx

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import (
    CancellationToken,
    FetchResult,
    PipelineContext,
    Stream,
    StreamSource,
)
from resource_sync.fetcher.cache import EtagCache, EtagInfo
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.plugin.registry import register_fetcher

_LOGGER = logging.getLogger(__name__)

# Shared connection pool — all HttpFetcher instances share this transport
_shared_transport: httpx.AsyncHTTPTransport | None = None

# Shared ETag cache — populated by the CLI bootstrap
_etag_cache: EtagCache | None = None


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


async def close_shared_transport() -> None:
    """Close and reset the shared HTTP transport if it was created."""
    global _shared_transport
    if _shared_transport is not None:
        await _shared_transport.aclose()
        _shared_transport = None


def set_etag_cache(cache: EtagCache) -> None:
    """Set the shared ETag cache for all HttpFetcher instances.

    Called during CLI bootstrap — pipeline builder injects the cache
    once config is loaded and the repo root is known.
    """
    global _etag_cache
    _etag_cache = cache


def _get_etag_cache() -> EtagCache | None:
    """Get the shared ETag cache, if set."""
    return _etag_cache


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

        If ETag caching is enabled, sends conditional request headers
        (If-None-Match / If-Modified-Since) and returns a 304 Not Modified
        result when the server indicates the content hasn't changed.
        """
        headers = dict(resource.headers) if resource.headers else {}

        # Inject ETag/Last-Modified conditional headers if cached
        cache = _get_etag_cache()
        cached: EtagInfo | None = cache.get(resource.url) if cache is not None else None
        if cached is not None:
            if cached.etag:
                headers.setdefault("If-None-Match", cached.etag)
            if cached.last_modified:
                headers.setdefault("If-Modified-Since", cached.last_modified)

        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            if ctx.cancel.cancelled:
                raise asyncio.CancelledError()

            try:
                request = self._client.build_request(
                    "GET", resource.url, headers=headers
                )
                response = await self._client.send(request, stream=True)

                # Handle 304 Not Modified — content unchanged
                if response.status_code == 304:
                    await response.aclose()
                    _LOGGER.debug("304 Not Modified for '%s'", resource.name)
                    return FetchResult(
                        stream=self._empty_stream(),
                        not_modified=True,
                    )

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

                # Update ETag cache on successful response
                if cache is not None:
                    etag = response.headers.get("etag")
                    last_modified = response.headers.get("last-modified")
                    if etag or last_modified:
                        cache.set(resource.url, EtagInfo(etag=etag, last_modified=last_modified))
                        cache.save()

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

    @staticmethod
    async def _empty_stream() -> Stream:
        """An empty stream, used for 304 Not Modified responses."""
        # The if False branch is never reached but makes the generator
        # syntactically valid so it yields nothing.
        if False:  # pragma: no cover
            yield b""

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()