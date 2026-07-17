"""
Command-line interface for the Resource Sync Engine.

Parses command-line arguments, loads configuration, runs the sync,
optionally writes a report file, and optionally commits/pushes to Git.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from resource_sync.config import load_config
from resource_sync.exceptions import ConfigError, GitError, ResourceSyncError
from resource_sync.git_ops import auto_commit_and_push
from resource_sync.syncer import sync_resources

_LOGGER = logging.getLogger(__name__)

_REPORT_FILENAME = "sync-report.json"


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="resource-sync",
        description="A config-driven resource synchronization tool.",
        epilog=(
            "Example:\n"
            "  resource-sync -c config.yaml\n"
            "  resource-sync -c config.yaml --dry-run\n"
            "  resource-sync -c config.yaml --no-commit"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and compare but do NOT write any files or commit",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Download and write files but do NOT commit or push to Git",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Git repository root (default: working directory of the config file)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser


def configure_logging(verbose: bool = False) -> None:
    """Set up logging with console output.

    Args:
        verbose: If ``True``, set log level to ``DEBUG``; otherwise
                 ``INFO``.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("resource_sync")
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def write_report(report_json: str, repo_root: Path) -> None:
    """Write the sync report to a JSON file in the repo root."""
    report_path = repo_root / _REPORT_FILENAME
    try:
        report_path.write_text(report_json, encoding="utf-8")
        _LOGGER.debug("Sync report written to '%s'", report_path)
    except OSError as e:
        _LOGGER.warning("Failed to write sync report: %s", e)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` on success (all resources synced), ``1`` on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(verbose=args.verbose)

    try:
        # 1. Load configuration
        config_path: Path = args.config
        _LOGGER.info("Loading config from '%s' ...", config_path)

        repo_root: Path | None = args.repo_root
        config = load_config(config_path, repo_root=repo_root)

        if repo_root is None:
            repo_root = config_path.parent.resolve()

        # 2. Run sync
        _LOGGER.info(
            "Starting sync (%s) ...",
            "DRY RUN" if args.dry_run else "live",
        )
        report = sync_resources(config, dry_run=args.dry_run)

        # 3. Write sync report
        write_report(report.to_json(), repo_root)

        # 4. Print summary to stderr
        summary = report.summary
        _LOGGER.info(
            "Summary — created: %d, updated: %d, skipped: %d, errors: %d",
            summary.get("created", 0),
            summary.get("updated", 0),
            summary.get("skipped", 0),
            summary.get("error", 0),
        )

        # 5. Commit and push if not dry-run and not --no-commit
        if not args.dry_run and not args.no_commit:
            _LOGGER.info("Checking Git status for auto-commit ...")
            try:
                auto_commit_and_push(repo_root, resource_count=report.changed)
            except GitError as e:
                _LOGGER.error("Git operation failed: %s", e)
                return 1

        # 6. Determine exit code
        if "error" in summary and summary["error"] > 0:
            _LOGGER.error(
                "%d resource(s) failed to sync — see log for details",
                summary["error"],
            )
            return 1

        return 0

    except ConfigError as e:
        _LOGGER.error("Configuration error: %s", e)
        return 1
    except ResourceSyncError as e:
        _LOGGER.error("Sync error: %s", e)
        return 1
    except KeyboardInterrupt:
        _LOGGER.info("Interrupted by user")
        return 1