"""
Git operations — stage, commit, and push changes.

All operations shell out to ``git`` via ``subprocess``. No external
Git library is needed for the simple operations we perform.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from resource_sync.exceptions import GitError

_LOGGER = logging.getLogger(__name__)


def _run_git(repo_root: Path, *args: str) -> str:
    """Run a git command and return stdout.

    Args:
        repo_root: The repository root directory.
        *args: Git subcommand and arguments (e.g., ``"status", "--porcelain"``).

    Returns:
        The stdout of the git command.

    Raises:
        GitError: If the git command exits with a non-zero status.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise GitError("Git is not installed or not found in PATH")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Provide a clearer error for missing Git identity (common in CI)
        if "Author identity unknown" in stderr or "empty ident name" in stderr:
            raise GitError(
                "Git commit failed because no author identity is configured.\n"
                "  Run the following commands to fix:\n"
                "    git config user.name \"Your Name\"\n"
                "    git config user.email \"you@example.com\"\n"
                "  Or in GitHub Actions, add a step before the sync:\n"
                "    - name: Configure Git identity\n"
                "      run: |\n"
                "        git config user.name \"github-actions[bot]\"\n"
                "        git config user.email \"github-actions[bot]@users.noreply.github.com\""
            )
        raise GitError(
            f"Git command 'git {' '.join(args)}' failed:\n"
            f"  stderr: {stderr}"
        )

    return result.stdout.strip()


def is_dirty(repo_root: Path) -> bool:
    """Check whether the working tree has uncommitted changes.

    Uses ``git status --porcelain``. Returns ``True`` if there is any
    output (meaning there are changes).
    """
    output = _run_git(repo_root, "status", "--porcelain")
    return bool(output)


def stage_all(repo_root: Path) -> None:
    """Stage all changes in the repository root.

    Equivalent to ``git add -A``.
    """
    _LOGGER.debug("Staging all changes in '%s' ...", repo_root)
    _run_git(repo_root, "add", "-A")


def commit(repo_root: Path, message: str) -> None:
    """Create a commit with the given message.

    Raises:
        GitError: If the commit fails (e.g., nothing to commit).
    """
    _LOGGER.debug("Committing with message: '%s'", message)
    _run_git(repo_root, "commit", "-m", message)


def push(repo_root: Path, remote: str = "origin") -> None:
    """Push the current branch to the remote.

    Detects the current branch automatically.

    Raises:
        GitError: If the push fails (e.g., no remote configured,
                  rejected).
    """
    branch = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    _LOGGER.debug("Pushing '%s' to '%s/%s' ...", repo_root, remote, branch)
    _run_git(repo_root, "push", remote, branch)


def auto_commit_and_push(
    repo_root: Path,
    resource_count: int = 0,
) -> None:
    """Convenience: stage, commit only if dirty, then push.

    Args:
        repo_root: The repository root directory.
        resource_count: Number of resources that changed (for the commit
                        message).

    Raises:
        GitError: If any Git operation fails.
    """
    if not is_dirty(repo_root):
        _LOGGER.info("No changes to commit — working tree is clean")
        return

    stage_all(repo_root)

    if resource_count == 1:
        message = "chore(sync): auto-update 1 resource"
    else:
        message = f"chore(sync): auto-update {resource_count} resources"

    commit(repo_root, message)
    push(repo_root)
    _LOGGER.info("Committed and pushed: '%s'", message)