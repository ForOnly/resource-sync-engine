"""Tests for ``resource_sync.content_validator``."""

from __future__ import annotations

import pytest

from resource_sync.content_validator import validate_content
from resource_sync.exceptions import ContentError


class TestValidateContent:
    """Tests for ``validate_content``."""

    def test_valid_binary_content(self) -> None:
        """Valid binary content passes validation."""
        validate_content(b"\x00\x01\x02\x03", max_size=1_000_000, name="test")

    def test_valid_text_content(self) -> None:
        """Valid text content passes validation."""
        validate_content(b"hello world\n", max_size=1_000_000, name="test")

    def test_empty_content_raises_error(self) -> None:
        """Empty content raises ContentError."""
        with pytest.raises(ContentError, match="empty"):
            validate_content(b"", max_size=1_000_000, name="empty-file")

    def test_oversized_content_raises_error(self) -> None:
        """Content exceeding max_size raises ContentError."""
        data = b"x" * 10_000
        with pytest.raises(ContentError, match="exceeds maximum size"):
            validate_content(data, max_size=100, name="big-file")

    def test_max_size_none_skips_size_check(self) -> None:
        """When max_size is None, size check is skipped."""
        data = b"x" * 1_000_000
        validate_content(data, max_size=None, name="big-file")  # No error

    def test_max_size_exact_boundary(self) -> None:
        """Content exactly at max_size passes."""
        data = b"x" * 100
        validate_content(data, max_size=100, name="test")  # No error

    def test_html_error_page_404_title(self) -> None:
        """Content with HTML error title raises ContentError."""
        html = b"""<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body><h1>Not Found</h1></body>
</html>"""
        with pytest.raises(ContentError, match="HTML error page"):
            validate_content(html, name="404-page")

    def test_html_error_page_403_title(self) -> None:
        """Content with HTML 403 title raises ContentError."""
        html = b"""<html><head><title>403 Forbidden</title></head><body>Forbidden</body></html>"""
        with pytest.raises(ContentError, match="HTML error page"):
            validate_content(html, name="403-page")

    def test_html_without_error_code_passes(self) -> None:
        """HTML content without an error code passes validation."""
        html = b"""<!DOCTYPE html>
<html>
<head><title>Welcome</title></head>
<body><h1>Hello</h1></body>
</html>"""
        validate_content(html, name="normal-page")  # No error

    def test_plain_html_without_error_title_passes(self) -> None:
        """Plain HTML content without error titles passes validation."""
        html = b"<html><body>some content</body></html>"
        validate_content(html, name="bare-page")  # No error

    def test_pure_binary_file_passes(self) -> None:
        """Binary content (no HTML tags) passes."""
        data = bytes(range(256))  # Binary data
        validate_content(data, name="binary-file")  # No error

    def test_partial_html_error_at_2k_boundary(self) -> None:
        """HTML error page detection only checks first 2048 bytes."""
        # Content with error title beyond 2048 bytes
        data = b"x" * 2048 + b"<html><head><title>404 Not Found</title></head></html>"
        validate_content(data, name="boundary-test")  # No error, title beyond first 2KB

    def test_long_text_passes(self) -> None:
        """Long text content passes."""
        data = b"Hello, World! " * 1000
        validate_content(data, name="long-text")  # No error