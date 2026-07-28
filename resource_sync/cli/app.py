"""CLI application — bootstraps the engine and runs the sync."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from resource_sync.cli.parser import build_parser
from resource_sync.domain.events import SyncCompleted
from resource_sync.domain.models import SyncReport
from resource_sync.engine.builder import PipelineBuilder
from resource_sync.engine.config import Config, ConfigError, load_config
from resource_sync.engine.executor import PipelineExecutor
from resource_sync.engine.orchestrator import SyncOrchestrator
from resource_sync.eventbus.memory import EventBus
from resource_sync.fetcher.cache import EtagCache
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
    import resource_sync.observer  # noqa: F401
    import resource_sync.sink  # noqa: F401
    import resource_sync.validator  # noqa: F401


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


async def _run_and_finalize(
        orchestrator: SyncOrchestrator,
        event_bus: EventBus,
        config: Config,
        config_path: Path,
        repo_root: Path,
        dry_run: bool,
        no_commit: bool,
) -> tuple[SyncReport, bool, bool]:
    """Run resources and emit completion only after all finalization succeeds."""
    try:
        report = await orchestrator.run(config, dry_run=dry_run)
        report_written = await asyncio.to_thread(
            _write_report,
            report.to_json(),
            repo_root,
        )

        git_succeeded = True
        if not dry_run and not no_commit and report.changed > 0:
            _LOGGER.info("Auto-committing %d changed resource(s)...", report.changed)
            git_root = str(config.repo_root or config_path.parent.resolve())
            git_succeeded = await asyncio.to_thread(
                orchestrator.commit_changes,
                repo_root=git_root,
                changed=report.changed,
            )

        if not report.has_errors and report_written and git_succeeded:
            await event_bus.emit(SyncCompleted(summary=str(report.summary)))

        return report, report_written, git_succeeded
    finally:
        await orchestrator.shutdown()


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

        # 3a. Register observers from config
        for obs_config in config.observer_configs:
            obs_type = obs_config.get("type", "log")
            if obs_type == "log":
                continue  # Already registered above
            try:
                obs_cls = registry.get_observer(obs_type)
                observer = obs_cls.configure(obs_config)
                event_bus.register_observer(observer)
                _LOGGER.debug("Registered observer '%s' from config", obs_type)
            except Exception as e:
                _LOGGER.warning("Failed to configure observer '%s': %s", obs_type, e)

        executor = PipelineExecutor(event_bus)

        # 3b. Initialize ETag cache
        etag_cache = EtagCache(repo_root)
        builder = PipelineBuilder(registry, etag_cache=etag_cache)
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
        report, report_written, git_succeeded = asyncio.run(
            _run_and_finalize(
                orchestrator=orchestrator,
                event_bus=event_bus,
                config=config,
                config_path=config_path,
                repo_root=repo_root,
                dry_run=args.dry_run,
                no_commit=args.no_commit,
            )
        )

        # 5. Print summary
        s = report.summary
        _LOGGER.info(
            "Summary — created: %d, updated: %d, skipped: %d, errors: %d",
            s.get("created", 0),
            s.get("updated", 0),
            s.get("skipped", 0),
            s.get("error", 0),
        )

        # 6. Exit code
        if not git_succeeded:
            return 1
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
