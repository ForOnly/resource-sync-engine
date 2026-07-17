"""
Core sync engine — orchestrates the resource sync lifecycle.

For each resource in the configuration:
  1. Download remote content.
  2. Validate content safety.
  3. Hash the remote content in memory.
  4. If local file exists: hash it and compare.
  5. If same → SKIPPED.
  6. If different → UPDATED (or CREATED if missing).
  7. In dry-run mode: never write files, only report intent.

All results are collected into a ``SyncReport`` that can be serialized
to JSON.
"""

from __future__ import annotations

import logging
from pathlib import Path

from resource_sync.content_validator import validate_content
from resource_sync.downloader import download_resource
from resource_sync.exceptions import ContentError, DownloadError, HashError
from resource_sync.hasher import hash_bytes, hash_file
from resource_sync.models import (
    HashAlgorithm,
    Resource,
    SyncConfig,
    SyncReport,
    SyncResult,
    SyncStatus,
)

_LOGGER = logging.getLogger(__name__)


def sync_resources(config: SyncConfig, dry_run: bool = False) -> SyncReport:
    """Execute the full sync for every resource in the configuration.

    A single resource failure never aborts the batch; the error is
    captured in its ``SyncResult`` and processing continues.

    Args:
        config: Parsed, validated configuration.
        dry_run: If ``True``, download and compare but never write files.

    Returns:
        A ``SyncReport`` with results for every resource.
    """
    report = SyncReport(dry_run=dry_run)

    for resource in config.resources:
        _LOGGER.info("Processing resource '%s' from %s ...", resource.name, resource.url)
        try:
            result = _sync_single_resource(resource, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Unexpected error syncing '%s':", resource.name)
            result = SyncResult(
                resource_name=resource.name,
                status=SyncStatus.ERROR,
                error_message=f"Unexpected error: {exc}",
                dry_run=dry_run,
            )

        _log_result(result)
        report.results.append(result)

    _LOGGER.info(
        "Sync complete — %d created, %d updated, %d skipped, %d errors",
        report.summary.get("created", 0),
        report.summary.get("updated", 0),
        report.summary.get("skipped", 0),
        report.summary.get("error", 0),
    )

    return report


def _sync_single_resource(resource: Resource, dry_run: bool = False) -> SyncResult:
    """Sync a single resource — the core decision tree.

    Steps:
      1. Download remote content.
      2. Validate content safety (empty, max size, HTML error page).
      3. Hash the remote content.
      4. Check if local file exists.
         a. Missing → CREATED (write in non-dry-run).
         b. Exists → hash local, compare with remote hash.
            i.  Same → SKIPPED.
            ii. Different → UPDATED (write in non-dry-run).
    """
    # Step 1: Download
    _LOGGER.debug("Downloading '%s' ...", resource.name)
    try:
        remote_data = download_resource(
            url=resource.url,
            headers=dict(resource.headers) if resource.headers else None,
            timeout=resource.timeout,
            retry=resource.retry,
            max_size=resource.max_size,
        )
    except DownloadError as e:
        return SyncResult(
            resource_name=resource.name,
            status=SyncStatus.ERROR,
            error_message=str(e),
            dry_run=dry_run,
        )

    # Step 2: Validate content
    try:
        validate_content(
            data=remote_data,
            max_size=resource.max_size,
            name=resource.name,
        )
    except ContentError as e:
        return SyncResult(
            resource_name=resource.name,
            status=SyncStatus.ERROR,
            error_message=str(e),
            dry_run=dry_run,
        )

    # Step 3: Hash remote content
    remote_hash = hash_bytes(remote_data, resource.algorithm)

    # Step 4: Check local file
    if resource.path.exists():
        return _handle_existing_file(resource, remote_data, remote_hash, dry_run)

    return _handle_missing_file(resource, remote_data, remote_hash, dry_run)


def _handle_existing_file(
    resource: Resource,
    remote_data: bytes,
    remote_hash: HashResult,
    dry_run: bool,
) -> SyncResult:
    """Handle a resource whose local file already exists."""
    # Hash local file
    try:
        local_hash = hash_file(resource.path, resource.algorithm)
    except HashError as e:
        return SyncResult(
            resource_name=resource.name,
            status=SyncStatus.ERROR,
            error_message=str(e),
            dry_run=dry_run,
        )

    # Compare hashes
    if local_hash.matches(remote_hash):
        _LOGGER.debug(
            "Hash match for '%s' (%s) — skipping",
            resource.name,
            remote_hash,
        )
        return SyncResult(
            resource_name=resource.name,
            status=SyncStatus.SKIPPED,
            local_hash=local_hash,
            remote_hash=remote_hash,
            dry_run=dry_run,
        )

    # Hash differs — update
    _LOGGER.debug(
        "Hash mismatch for '%s' (local: %s, remote: %s) — updating",
        resource.name,
        local_hash,
        remote_hash,
    )
    if not dry_run:
        _write_resource(resource, remote_data)

    return SyncResult(
        resource_name=resource.name,
        status=SyncStatus.UPDATED,
        local_hash=local_hash,
        remote_hash=remote_hash,
        dry_run=dry_run,
    )


def _handle_missing_file(
    resource: Resource,
    remote_data: bytes,
    remote_hash: HashResult,
    dry_run: bool,
) -> SyncResult:
    """Handle a resource with no local file — create it."""
    _LOGGER.debug("Local file '%s' does not exist — creating", resource.path)
    if not dry_run:
        _write_resource(resource, remote_data)

    return SyncResult(
        resource_name=resource.name,
        status=SyncStatus.CREATED,
        remote_hash=remote_hash,
        dry_run=dry_run,
    )


def _write_resource(resource: Resource, data: bytes) -> None:
    """Write downloaded content to disk, creating parent directories."""
    try:
        resource.path.parent.mkdir(parents=True, exist_ok=True)
        resource.path.write_bytes(data)
        _LOGGER.info(
            "Wrote %d bytes to '%s'", len(data), resource.path
        )
    except OSError as e:
        raise HashError(
            f"Failed to write resource '{resource.name}' to "
            f"'{resource.path}': {e}"
        )


def _log_result(result: SyncResult) -> None:
    """Log a single sync result at the appropriate level."""
    if result.status == SyncStatus.ERROR:
        _LOGGER.error(
            "  [%s] '%s' — %s",
            result.status.value.upper(),
            result.resource_name,
            result.error_message,
        )
    elif result.status == SyncStatus.SKIPPED:
        _LOGGER.info("  [%s] '%s'", result.status.value.upper(), result.resource_name)
    else:
        _LOGGER.info(
            "  [%s] '%s' (dry_run=%s)",
            result.status.value.upper(),
            result.resource_name,
            result.dry_run,
        )