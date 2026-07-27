"""HTML error page validator — detects error pages disguised as 2xx responses."""

from __future__ import annotations

import re
from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamTransformer
from resource_sync.plugin.errors import PluginExecutionError
from resource_sync.plugin.registry import register_validator

_HTML_TAG = re.compile(r"<(html|head|body)[^>]*>", re.IGNORECASE)
_HTML_ERROR_TITLE = re.compile(r"<title>\s*(404|403|500|502|503)\s", re.IGNORECASE)
_CHECK_SIZE = 2048


@register_validator
class HtmlErrorValidator:
    """Detects HTML error pages returned with a 2xx status code."""
    name: ClassVar[str] = "html_error"

    @classmethod
    def should_apply(cls, resource: Resource) -> bool:
        return True

    def __call__(self) -> StreamTransformer:
        return self._validate

    async def _validate(self, stream: Stream, resource: Resource, ctx: PipelineContext) -> Stream:
        head = b""
        rest: list[bytes] = []
        async for chunk in stream:
            needed = _CHECK_SIZE - len(head)
            if needed > 0:
                head += chunk[:needed]
                if len(chunk) > needed:
                    rest.append(chunk[needed:])
            else:
                rest.append(chunk)
        _check_html_error(head, resource.name)
        yield head
        for r in rest:
            yield r
        async for chunk in stream:
            yield chunk


def _check_html_error(data: bytes, name: str) -> None:
    try:
        head = data.decode("utf-8", errors="replace")
    except Exception:
        return
    if _HTML_TAG.search(head) and _HTML_ERROR_TITLE.search(head):
        m = re.search(r"<title>\s*([^<]+?)\s*</title>", head, re.IGNORECASE)
        title = m.group(1).strip() if m else "unknown"
        raise PluginExecutionError(f"Content for '{name}' appears to be an HTML error page (title: '{title}')")