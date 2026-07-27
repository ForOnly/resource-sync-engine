"""Configuration loading — YAML parser with env var substitution."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePath
from typing import Any

import yaml

from resource_sync.domain.models import HashAlgorithm, Resource

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")
_REQUIRED_RESOURCE_KEYS = frozenset({"name", "url", "path"})
_KNOWN_ALGORITHMS: set[str] = {a.value for a in HashAlgorithm}


class ConfigError(Exception):
    """Configuration file is missing, invalid, or violates the schema."""


class Config:
    """Loaded configuration — holds resources and engine settings."""

    def __init__(
        self,
        resources: tuple[Resource, ...],
        engine_config: dict[str, Any] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.resources = resources
        self.engine_config = engine_config or {}
        self.repo_root = repo_root

    @property
    def max_concurrency(self) -> int:
        return int(self.engine_config.get("max_concurrency", 1))

    @property
    def sink_name(self) -> str:
        return str(self.engine_config.get("sink", "local"))

    @property
    def observer_configs(self) -> list[dict[str, Any]]:
        return list(self.engine_config.get("observers", []))


def load_config(
    path: str | Path,
    env: dict[str, str] | None = None,
    repo_root: Path | None = None,
) -> Config:
    """Load, validate, and return a Config from a YAML file."""
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    if env is None:
        env = dict(os.environ)

    if repo_root is None:
        repo_root = config_path.parent

    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError("Config must contain a top-level mapping")

    raw = _substitute_env(raw, env)

    raw_resources = raw.get("resources")
    if raw_resources is None:
        raise ConfigError("Config must contain a 'resources' key")
    if not isinstance(raw_resources, list) or not raw_resources:
        raise ConfigError("'resources' must be a non-empty list")

    resources: list[Resource] = []
    for i, entry in enumerate(raw_resources, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Resource #{i} must be a mapping")
        missing = _REQUIRED_RESOURCE_KEYS - entry.keys()
        if missing:
            raise ConfigError(
                f"Resource #{i} '{entry.get('name', '<unnamed>')}' missing: {', '.join(sorted(missing))}"
            )
        resources.append(Resource(
            name=str(entry["name"]),
            url=str(entry["url"]),
            path=_resolve_path(str(entry["path"]), repo_root),
            algorithm=_parse_algorithm(entry.get("algorithm", "sha256"), str(entry["name"])),
            headers=dict(entry.get("headers", {})),
            timeout=float(entry.get("timeout", 30.0)),
            retry=int(entry.get("retry", 3)),
            max_size=int(entry.get("max_size", 500 * 1024 * 1024)),
            metadata=dict(entry.get("metadata", {})),
        ))

    return Config(
        resources=tuple(resources),
        engine_config=dict(raw.get("engine", {})),
        repo_root=repo_root,
    )


def _resolve_path(raw_path: str, repo_root: Path) -> PurePath:
    p = Path(raw_path)
    return PurePath(p.resolve() if p.is_absolute() else (repo_root / p).resolve())


def _parse_algorithm(value: str, name: str) -> HashAlgorithm:
    normalized = value.strip().lower()
    if normalized not in _KNOWN_ALGORITHMS:
        raise ConfigError(
            f"Resource '{name}': unknown hash algorithm '{value}'. "
            f"Must be one of: {', '.join(sorted(_KNOWN_ALGORITHMS))}"
        )
    return HashAlgorithm(normalized)


def _substitute_env(raw: Any, env: dict[str, str]) -> Any:
    if isinstance(raw, str):
        return _substitute_in_string(raw, env)
    if isinstance(raw, dict):
        return {k: _substitute_env(v, env) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_substitute_env(item, env) for item in raw]
    return raw


def _substitute_in_string(value: str, env: dict[str, str]) -> str:
    def _replacer(m: re.Match[str]) -> str:
        var = m.group(1)
        if var not in env:
            raise ConfigError(f"Environment variable '${var}' is not set")
        return env[var]
    return _ENV_VAR_PATTERN.sub(_replacer, value)