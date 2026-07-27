"""Git sink — writes files and commits to Git repository."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import ClassVar

from resource_sync.domain.models import Resource
from resource_sync.domain.stream import PipelineContext, Stream, StreamSink, WriteResult
from resource_sync.plugin.registry import register_sink
from resource_sync.sink.local import LocalSink

_LOGGER = logging.getLogger(__name__)


@register_sink("git")
class GitSink:
    """Git-aware file writer: writes via LocalSink, then stages and commits.

    Unlike LocalSink, GitSink integrates with the Git repository lifecycle:
    - write():  writes the file to disk via LocalSink
    - commit_all():  stages all changes, commits, and pushes

    commit_all() should be called ONCE after all resources are synced,
    not after each individual write.
    """

    name: ClassVar[str] = "git"

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root
        self._local = LocalSink()

    @classmethod
    def configure(cls, resource: Resource) -> StreamSink:
        return cls()

    async def write(
        self, stream: Stream, resource: Resource, ctx: PipelineContext
    ) -> WriteResult:
        """Write the stream to the local file. Does NOT commit."""
        return await self._local.write(stream, resource, ctx)

    def commit(self) -> bool:
        """Commit the pending write via LocalSink."""
        return self._local.commit()

    def discard(self) -> bool:
        """Discard the pending write via LocalSink."""
        return self._local.discard()

    def commit_all(
        self,
        repo_root: Path | None = None,
        resource_count: int = 0,
    ) -> bool:
        """Stage, commit, and push all changes. Returns True on success.

        Call this ONCE after all resources have been synced.
        Skips if the working tree is clean (no changes).
        """
        root = repo_root or self._resolve_repo_root()
        if not root:
            _LOGGER.warning("No Git repository root found — skipping commit")
            return False

        if not self._is_dirty(root):
            _LOGGER.info("No changes to commit — working tree is clean")
            return True

        self._run(root, "add", "-A")

        if resource_count == 1:
            message = "chore(sync): auto-update 1 resource"
        else:
            message = f"chore(sync): auto-update {resource_count} resources"

        if not self._run(root, "commit", "-m", message):
            _LOGGER.error("Git commit failed")
            return False

        branch = self._run(root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch:
            self._run(root, "push", "origin", branch)
            _LOGGER.info("Pushed '%s' to origin/%s", message, branch)

        return True

    def _resolve_repo_root(self) -> Path | None:
        """Resolve the Git repository root directory."""
        if self.repo_root is not None:
            return self.repo_root
        # Fallback: use cwd
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / ".git").exists():
                return parent
        return None

    def _run(self, repo_root: Path, *args: str) -> str:
        """Run a git command and return stdout. Returns empty string on failure."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            _LOGGER.error("Git is not installed or not found in PATH")
            return ""
        except OSError as e:
            _LOGGER.error("Git execution failed: %s", e)
            return ""

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "Author identity unknown" in stderr or "empty ident name" in stderr:
                _LOGGER.error(
                    "Git commit failed: author identity not configured.\n"
                    "  Run: git config user.name 'Your Name'\n"
                    "       git config user.email 'you@example.com'"
                )
            else:
                _LOGGER.error(
                    "Git command 'git %s' failed: %s",
                    " ".join(args),
                    stderr,
                )
            return ""

        return result.stdout.strip()

    def _is_dirty(self, repo_root: Path) -> bool:
        """Check whether the working tree has uncommitted changes."""
        output = self._run(repo_root, "status", "--porcelain")
        return bool(output)