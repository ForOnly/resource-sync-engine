"""Tests for ``resource_sync.downloader``."""

from __future__ import annotations

import pytest

from resource_sync.downloader import download_resource
from resource_sync.exceptions import DownloadError


class TestDownloader:
    """Tests for ``download_resource``."""

    def test_successful_download(self, httpx_mock) -> None:
        """A successful request returns the response body."""
        httpx_mock.add_response(
            url="https://example.com/data.txt",
            content=b"hello world",
            status_code=200,
        )
        result = download_resource("https://example.com/data.txt", retry=1)
        assert result == b"hello world"

    def test_with_headers(self, httpx_mock) -> None:
        """Custom headers are sent with the request."""
        httpx_mock.add_response(
            url="https://example.com/data.txt",
            content=b"data",
            status_code=200,
        )
        result = download_resource(
            "https://example.com/data.txt",
            headers={"Authorization": "Bearer token123"},
            retry=1,
        )
        assert result == b"data"

    def test_http_404_raises_error(self, httpx_mock) -> None:
        """A 404 response raises DownloadError."""
        httpx_mock.add_response(
            url="https://example.com/not-found",
            content=b"Not Found",
            status_code=404,
        )
        with pytest.raises(DownloadError, match="HTTP 404"):
            download_resource("https://example.com/not-found", retry=1)

    def test_http_500_raises_error(self, httpx_mock) -> None:
        """A 500 response raises DownloadError."""
        httpx_mock.add_response(
            url="https://example.com/error",
            content=b"Server Error",
            status_code=500,
        )
        with pytest.raises(DownloadError, match="HTTP 500"):
            download_resource("https://example.com/error", retry=1)

    def test_timeout_raises_error(self, httpx_mock) -> None:
        """A timeout raises DownloadError."""
        import httpx

        httpx_mock.add_exception(
            httpx.TimeoutException("Connection timed out"),
            url="https://example.com/slow",
        )
        with pytest.raises(DownloadError, match="Timeout|Failed to download"):
            download_resource("https://example.com/slow", timeout=0.001, retry=1)

    def test_network_error_raises_error(self, httpx_mock) -> None:
        """A network error raises DownloadError."""
        import httpx

        httpx_mock.add_exception(
            httpx.RequestError("Connection refused"),
            url="https://example.com/down",
        )
        with pytest.raises(DownloadError, match="Failed to download"):
            download_resource("https://example.com/down", retry=1)

    def test_retry_on_transient_failure(self, httpx_mock) -> None:
        """The downloader retries on transient failures before giving up."""
        import httpx

        httpx_mock.add_exception(
            httpx.TimeoutException("Timeout 1"),
            url="https://example.com/unstable",
        )
        httpx_mock.add_exception(
            httpx.TimeoutException("Timeout 2"),
            url="https://example.com/unstable",
        )
        httpx_mock.add_response(
            url="https://example.com/unstable",
            content=b"success",
            status_code=200,
        )

        result = download_resource("https://example.com/unstable", timeout=1, retry=3)
        assert result == b"success"

    def test_all_retries_exhausted_raises_error(self, httpx_mock) -> None:
        """After exhausting all retries, an error is raised."""
        import httpx

        for _ in range(3):
            httpx_mock.add_exception(
                httpx.TimeoutException("Timeout"),
                url="https://example.com/dead",
            )

        with pytest.raises(DownloadError, match="after 3 attempts"):
            download_resource("https://example.com/dead", timeout=1, retry=3)

    def test_max_size_content_length_header(self, httpx_mock) -> None:
        """DownloadError is raised when content-length exceeds max_size."""
        httpx_mock.add_response(
            url="https://example.com/big",
            content=b"x" * 100,
            headers={"content-length": "100"},
            status_code=200,
        )
        with pytest.raises(DownloadError, match="exceeds maximum size"):
            download_resource("https://example.com/big", max_size=50, retry=1)

    def test_max_size_actual_content(self, httpx_mock) -> None:
        """DownloadError is raised when actual content exceeds max_size."""
        httpx_mock.add_response(
            url="https://example.com/big",
            content=b"x" * 200,
            status_code=200,
        )
        with pytest.raises(DownloadError, match="exceeds maximum size"):
            download_resource("https://example.com/big", max_size=100, retry=1)

    def test_redirect_is_followed(self, httpx_mock) -> None:
        """Redirects are followed automatically."""
        httpx_mock.add_response(
            url="https://example.com/redirect",
            content=b"redirected content",
            status_code=200,
        )
        result = download_resource("https://example.com/redirect", retry=1)
        assert result == b"redirected content"