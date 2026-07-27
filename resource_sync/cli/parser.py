"""CLI argument parser."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="resource-sync",
        description="A config-driven resource synchronization tool.",
    )
    parser.add_argument("-c", "--config", type=Path, default=Path("config.yaml"),
                        help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Download and compare but do NOT write files")
    parser.add_argument("--no-commit", action="store_true",
                        help="Write files but do NOT commit or push to Git")
    parser.add_argument("--repo-root", type=Path, default=None,
                        help="Git repository root (default: config parent dir)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug-level logging")
    return parser