"""CLI application — bootstraps the engine and runs the sync."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from resource_sync.cli.parser import build_parser
from resource_sync.engine.builder import PipelineBuilder
from resource_sync.engine.config import ConfigError, load_config
from resource_sync.engine.executor import PipelineExecutor
from resource_sync.engine.orchestrator import SyncOrchestrator
from resource_sync.eventbus.memory import EventBus
from resource_sync.observer.log import LogObserver
from resource_sync.plugin.registry import get_registry

_LOGGER = logging.getLogger(__name__)
_REPORT_FILENAME = "sync-report.json"


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging to stderr with the given verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger("resource_sync")
    root.setLevel(level)
    root.addHandler(handler)


def _discover_plugins() -> None:
    """Import all plugin modules to trigger their registration decorators."""
    import resource_sync.fetcher  # noqa: F401
    import resource_sync.validator  # noqa: F401
    import resource_sync.sink  # noqa: F401
    import resource_sync.observer  # noqa: F401


def _write_report(report_json: str, repo_root: Path) -> bool:
    """Write the sync report to a JSON file. Returns True on success."""
    report_path = repo_root / _REPORT_FILENAME
    try:
        report_path.write_text(report_json, encoding="utf-8")
        _LOGGER.debug("Sync report written to '%s'", report_path)
        return True
    except OSError as e:
        _LOGGER.error("Failed to write sync report: %s", e)
        return False


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns 0 on success, 1 on failure."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(verbose=args.verbose)

    try:
        # 1. Load config
        config_path: Path = args.config
        repo_root: Path | None = args.repo_root
        config = load_config(config_path, repo_root=repo_root)
        if repo_root is None:
            repo_root = config_path.parent.resolve()

        # 2. Bootstrap plugins (import modules → decorators fire)
        _discover_plugins()
        registry = get_registry()

        # 3. Build engine
        event_bus = EventBus()
        event_bus.register_observer(LogObserver())
        executor = PipelineExecutor(event_bus)
        builder = PipelineBuilder(registry)
        orchestrator = SyncOrchestrator(
            builder=builder,
            executor=executor,
            event_bus=event_bus,
            max_concurrency=config.max_concurrency,
        )

        # 4. Run sync
        _LOGGER.info(
            "Starting sync (dry_run=%s, concurrency=%d)...",
            args.dry_run,
            config.max_concurrency,
        )
        report = asyncio.run(orchestrator.run(config, dry_run=args.dry_run))

        # 5. Write report
        report_written = _write_report(report.to_json(), repo_root)

        # 6. Print summary
        s = report.summary
        _LOGGER.info(
            "Summary — created: %d, updated: %d, skipped: %d, errors: %d",
            s.get("created", 0),
            s.get("updated", 0),
            s.get("skipped", 0),
            s.get("error", 0),
        )

        # 7. Git commit (once, after all resources are synced)
        if not args.dry_run and not args.no_commit and report.changed > 0:
            _LOGGER.info("Auto-committing %d changed resource(s)...", report.changed)
            try:
                from resource_sync.sink.git import GitSink

                git_root = config.repo_root or config_path.parent.resolve()
                git = GitSink(repo_root=git_root)
                if not git.commit_all(repo_root=git_root, resource_count=report.changed):
                    return 1
            except Exception as e:
                _LOGGER.error("Git operation failed: %s", e)
                return 1

        # 8. Exit code
        if s.get("error", 0) > 0:
            return 1
        if not report_written:
            return 1
        return 0

    except ConfigError as e:
        _LOGGER.error("Configuration error: %s", e)
        return 1
    except KeyboardInterrupt:
        _LOGGER.info("Interrupted by user")
        return 1