"""Git repository fetcher — retrieves a single file from a Git repository.

URL scheme: ``git+https://github.com/org/repo.git``

The ref (branch/tag/commit) and file path within the repo are specified
in ``resource.metadata``:

.. code-block:: yaml

   resources:
     - name: "config-from-git"
       url: "git+https://github.com/org/repo.git"
       path: "data/config.yaml"
       metadata:
         ref: "main"               # branch, tag, or commit hash (default: main)
         file_path: "config/prod.yaml"  # path within the repo (required)

Authentication is via environment variables:
    - ``GIT_USERNAME`` — Git username (optional)
    - ``GIT_TOKEN`` or ``GIT_PASSWORD`` — Git token/password (optional)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import (
    FetchResult,
    PipelineContext,
    Stream,
    StreamSource,
    chunked_source,
)
from resource_sync.plugin.errors import PluginConfigurationError, PluginExecutionError
from resource_sync.plugin.registry import register_fetcher

_LOGGER = logging.getLogger(__name__)

# URL schemes that should be stripped of the "git+" prefix
_GIT_SCHEME_PREFIX = "git+"
# The default ref (branch/tag/commit) to check out
_DEFAULT_REF = "main"
# Maximum git command timeout in seconds
_GIT_TIMEOUT = 120


@register_fetcher(schemes=frozenset({"git+https", "git+ssh", "git"}))
class GitFetcher:
    """Fetcher that retrieves a single file from a Git repository.

    Clones the repository with ``--depth 1`` to minimize data transfer,
    reads the requested file into memory, then cleans up the temporary
    clone directory.
    """

    # Keep ClassVar for type annotation compatibility; actual use is via
    # the registry's scheme-based dispatch.
    supported_schemes: ClassVar[frozenset[str]] = frozenset({"git+https", "git+ssh", "git"})

    def __init__(self, resource: Resource) -> None:
        self._resource = resource

    @classmethod
    def configure(cls, resource: Resource) -> StreamSource:
        """Create a GitFetcher from a resource definition."""
        return cls(resource)

    async def fetch(self, resource: Resource, ctx: PipelineContext) -> FetchResult:
        """Fetch a file from a Git repository.

        The file is read entirely into memory (O(file_size)) since the
        temporary clone directory is cleaned up before returning.
        """
        # Resolve the actual repository URL (strip "git+" prefix)
        repo_url = self._resolve_repo_url(resource.url)

        # Extract metadata
        ref = resource.metadata.get("ref", _DEFAULT_REF)
        file_path = resource.metadata.get("file_path", "")

        if not file_path:
            raise PluginConfigurationError(
                f"Resource '{resource.name}': 'file_path' is required in "
                f"metadata for git fetcher (e.g. metadata: {{file_path: 'path/in/repo/file.txt'}})"
            )

        if ctx.cancel.cancelled:
            raise asyncio.CancelledError()

        temp_dir: str | None = None
        try:
            temp_dir = tempfile.mkdtemp(prefix=f"git-{resource.name}-")

            # Apply authentication
            auth_url = self._apply_auth(repo_url)

            # Clone the repository (shallow, single branch)
            _LOGGER.debug(
                "Cloning '%s' (ref=%s) into temp dir '%s'",
                repo_url, ref, temp_dir,
            )
            await self._run_git(
                "clone", "--depth", "1", "--branch", ref,
                "--single-branch", auth_url, temp_dir,
                ctx=ctx,
            )

            # Resolve the target file
            target = Path(temp_dir) / file_path

            if not target.exists():
                # Try to list the root for diagnostic purposes
                try:
                    listing = " ".join(sorted(p.name for p in Path(temp_dir).iterdir() if not p.name.startswith(".")))
                except Exception:
                    listing = "(unavailable)"
                raise PluginExecutionError(
                    f"File '{file_path}' not found in repository '{repo_url}' (ref={ref}). "
                    f"Root contents: {listing}"
                )

            if not target.is_file():
                raise PluginExecutionError(
                    f"Path '{file_path}' in repository '{repo_url}' is not a file"
                )

            # Read the file content
            content = target.read_bytes()
            _LOGGER.debug("Read %d bytes from '%s' in repo '%s'", len(content), file_path, repo_url)

            return FetchResult(
                stream=chunked_source(content),
                content_type="application/octet-stream",
                content_length=len(content),
                metadata={"ref": ref, "repo": repo_url, "file_path": file_path},
            )

        finally:
            if temp_dir is not None:
                await self._cleanup(temp_dir)

    # ─── Internal helpers ───

    @staticmethod
    def _resolve_repo_url(url: str) -> str:
        """Strip the ``git+`` prefix to get the actual repository URL.

        Examples:
            ``git+https://github.com/org/repo.git`` → ``https://github.com/org/repo.git``
            ``git+ssh://git@github.com/org/repo.git`` → ``ssh://git@github.com/org/repo.git``
            ``git://github.com/org/repo.git`` → ``git://github.com/org/repo.git``
        """
        if url.startswith(_GIT_SCHEME_PREFIX):
            return url[len(_GIT_SCHEME_PREFIX):]
        return url

    @staticmethod
    def _apply_auth(url: str) -> str:
        """Embed authentication credentials into the URL.

        Reads ``GIT_USERNAME`` and ``GIT_TOKEN`` (or ``GIT_PASSWORD``)
        from the environment. Credentials are only injected if the URL
        does not already contain a ``@`` character (no existing credentials).
        """
        username = os.environ.get("GIT_USERNAME")
        token = os.environ.get("GIT_TOKEN") or os.environ.get("GIT_PASSWORD")

        if username and token and "@" not in url:
            # Insert credentials after the protocol separator
            # e.g. https:// → https://user:token@
            idx = url.find("://")
            if idx != -1:
                url = url[: idx + 3] + f"{username}:{token}@" + url[idx + 3:]
                _LOGGER.debug("Embedded authentication credentials into Git URL")
            else:
                _LOGGER.debug("No protocol separator found in URL — skipping auth injection")
        elif username and not token:
            _LOGGER.debug("GIT_USERNAME set but no GIT_TOKEN/GIT_PASSWORD — skipping auth injection")

        return url

    @staticmethod
    async def _run_git(*args: str, ctx: PipelineContext) -> str:
        """Run a git subprocess and return stdout.

        Runs in a thread pool executor to avoid blocking the event loop.
        Raises ``PluginExecutionError`` on failure.
        """
        loop = asyncio.get_event_loop()

        def _run() -> str:
            try:
                result = subprocess.run(
                    ["git", *args],
                    capture_output=True,
                    text=True,
                    timeout=_GIT_TIMEOUT,
                )
            except FileNotFoundError:
                raise PluginExecutionError(
                    "Git is not installed or not found in PATH"
                ) from None
            except subprocess.TimeoutExpired:
                raise PluginExecutionError(
                    f"Git command timed out after {_GIT_TIMEOUT}s: git {' '.join(args)}"
                ) from None
            except OSError as e:
                raise PluginExecutionError(f"Git execution failed: {e}") from e

            if result.returncode != 0:
                stderr = result.stderr.strip()
                raise PluginExecutionError(
                    f"Git command failed (exit={result.returncode}): "
                    f"git {' '.join(args)}: {stderr}"
                )

            return result.stdout.strip()

        return await loop.run_in_executor(None, _run)

    @staticmethod
    async def _cleanup(temp_dir: str) -> None:
        """Remove a temporary directory, logging but not propagating errors."""
        loop = asyncio.get_event_loop()

        def _rmtree() -> None:
            try:
                shutil.rmtree(temp_dir, ignore_errors=False)
            except OSError as e:
                _LOGGER.warning("Failed to clean up temp dir '%s': %s", temp_dir, e)

        await loop.run_in_executor(None, _rmtree)