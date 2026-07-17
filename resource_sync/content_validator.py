"""
Content safety validation for downloaded resources.

Validates that downloaded content is safe to write to disk by checking
for empty files, excessive size, and HTML error pages disguised as
successful responses.
"""

from __future__ import annotations

import logging
import re

from resource_sync.exceptions import ContentError

_LOGGER = logging.getLogger(__name__)

# Pattern to detect HTML document structure tags.
_HTML_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<(html|head|body)[^>]*>", re.IGNORECASE
)

# Pattern to detect an HTML <title> containing an HTTP error status code.
_HTML_ERROR_TITLE_PATTERN: re.Pattern[str] = re.compile(
    r"<title>\s*(404|403|500|502|503)\s", re.IGNORECASE
)


def validate_content(
    data: bytes,
    max_size: int | None = None,
    name: str | None = None,
) -> None:
    """Validate downloaded content before writing to disk.

    Performs three checks in order:
      1. Empty file detection.
      2. Maximum file size limit (if ``max_size`` is provided).
      3. HTML error page detection (heuristic: checks for ``<html>`` /
         ``<head>`` / ``<body>`` tags combined with a 4xx/5xx title).

    Args:
        data: The raw byte content to validate.
        max_size: Maximum allowed file size in bytes. ``None`` disables
                  this check.
        name: Optional resource name for error messages (default: ``None``).

    Raises:
        ContentError: If any validation check fails.
    """
    label = name or "unknown"

    # 1. Empty file detection
    if not data:
        raise ContentError(f"Downloaded content for '{label}' is empty (0 bytes)")

    # 2. Maximum file size limit
    if max_size is not None and len(data) > max_size:
        raise ContentError(
            f"Downloaded content for '{label}' exceeds maximum size "
            f"({len(data)} bytes > {max_size} bytes)"
        )

    # 3. HTML error page detection
    _check_html_error_page(data, label)

    _LOGGER.debug(
        "Content validation passed for '%s' (%d bytes)", label, len(data)
    )


def _check_html_error_page(data: bytes, label: str) -> None:
    """Detect HTML error pages returned with a 2xx status code.

    Uses a heuristic: if the content looks like HTML (contains
    ``<html>``, ``<head>``, or ``<body>``) **AND** has a title containing
    a 404/403/500/502/503 status code, it is likely an error page.
    Normal HTML pages with valid titles pass this check.

    Raises:
        ContentError: If the content appears to be an HTML error page.
    """
    try:
        head = data[:2048].decode("utf-8", errors="replace")
    except Exception:
        return  # Binary file; skip HTML check

    has_html_tag = bool(_HTML_TAG_PATTERN.search(head))
    has_error_title = bool(_HTML_ERROR_TITLE_PATTERN.search(head))

    if has_html_tag and has_error_title:
        # Extract the title for a better error message
        title_match = re.search(
            r"<title>\s*([^<]+?)\s*</title>", head, re.IGNORECASE
        )
        title = title_match.group(1).strip() if title_match else "unknown"

        raise ContentError(
            f"Downloaded content for '{label}' appears to be an HTML error "
            f"page (title: '{title}'). The server may have returned an error "
            f"page with a 2xx status code."
        )