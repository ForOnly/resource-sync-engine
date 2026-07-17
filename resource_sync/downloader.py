"""
HTTP/HTTPS resource downloader.

Uses ``httpx`` for synchronous downloads with configurable timeouts,
headers, and retry logic.
"""

from __future__ import annotations

import logging

import httpx

from resource_sync.exceptions import DownloadError

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: float = 30.0
_DEFAULT_RETRY: int = 3
_DEFAULT_MAX_SIZE: int = 500 * 1024 * 1024  # 500 MB


def download_resource(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    retry: int = _DEFAULT_RETRY,
    max_size: int = _DEFAULT_MAX_SIZE,
) -> bytes:
    """Download a resource from an HTTP(S) URL.

    Args:
        url: The URL to fetch.
        headers: Optional HTTP headers to include in the request.
        timeout: Request timeout in seconds (default: 30).
        retry: Number of retry attempts on transient failures (default: 3).
        max_size: Maximum allowed response body size (default: 500 MB).

    Returns:
        The raw byte content of the response body.

    Raises:
        DownloadError: On network error, timeout, non-2xx status, or
                       oversized response.
    """
    last_exception: Exception | None = None

    for attempt in range(1, retry + 1):
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
                response = client.get(url, headers=headers or {})

                # Check content-length header upfront to avoid large downloads
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_size:
                    raise DownloadError(
                        f"Resource at '{url}' exceeds maximum size "
                        f"({content_length} bytes > {max_size} bytes)"
                    )

                response.raise_for_status()
                content = response.content

                if len(content) > max_size:
                    raise DownloadError(
                        f"Downloaded content for '{url}' exceeds maximum size "
                        f"({len(content)} bytes > {max_size} bytes)"
                    )

                _LOGGER.debug(
                    "Downloaded '%s' (%d bytes, HTTP %d)",
                    url,
                    len(content),
                    response.status_code,
                )
                return content

        except httpx.TimeoutException as e:
            last_exception = DownloadError(f"Timeout downloading '{url}': {e}")
            _LOGGER.warning(
                "Attempt %d/%d timed out for '%s'", attempt, retry, url
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            error_body = _try_decode_error(e.response.content)
            raise DownloadError(
                f"HTTP {status} downloading '{url}': {error_body}"
            )
        except httpx.RequestError as e:
            last_exception = DownloadError(f"Request failed for '{url}': {e}")
            _LOGGER.warning(
                "Attempt %d/%d failed for '%s': %s",
                attempt,
                retry,
                url,
                e,
            )

        if attempt < retry:
            _LOGGER.info("Retrying '%s' (attempt %d/%d)...", url, attempt + 1, retry)

    raise DownloadError(
        f"Failed to download '{url}' after {retry} attempts"
    ) from last_exception


def _try_decode_error(content: bytes) -> str:
    """Try to decode error response body as text, falling back to size info."""
    try:
        text = content.decode("utf-8", errors="replace")
        if len(text) > 200:
            text = text[:200] + "..."
        return text.strip()
    except Exception:
        return f"({len(content)} bytes)"