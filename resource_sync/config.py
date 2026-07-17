"""
YAML configuration loader with environment variable substitution.

Parses the ``config.yaml`` file, validates the schema, substitutes
``${ENV_VAR}`` placeholders, and returns a ``SyncConfig`` instance.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from resource_sync.exceptions import ConfigError
from resource_sync.models import HashAlgorithm, Resource, SyncConfig

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

_REQUIRED_RESOURCE_KEYS = {"name", "url", "path"}

_KNOWN_ALGORITHMS: set[str] = {a.value for a in HashAlgorithm}

_DEFAULT_TIMEOUT: float = 30.0
_DEFAULT_RETRY: int = 3
_DEFAULT_MAX_SIZE: int = 500 * 1024 * 1024


def load_config(
    path: str | Path,
    env: dict[str, str] | None = None,
    repo_root: Path | None = None,
) -> SyncConfig:
    """Load, validate, and return a ``SyncConfig`` from a YAML file.

    Args:
        path: Filesystem path to the YAML configuration file.
        env: Override environment variables (for testing). Defaults to
             ``os.environ``.
        repo_root: Root of the Git repository. If provided, relative
                   resource paths are resolved against it. Defaults to the
                   config file's parent directory.

    Returns:
        A validated ``SyncConfig`` instance.

    Raises:
        ConfigError: File not found, invalid YAML, missing required fields,
                     or unknown hash algorithm.
    """
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
        raise ConfigError(f"Invalid YAML in config file '{config_path}': {e}")

    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file '{config_path}' must contain a top-level mapping"
        )

    # Substitute environment variables in the raw parsed structure
    raw = _substitute_env(raw, env)

    raw_resources = raw.get("resources")
    if raw_resources is None:
        raise ConfigError("Config file must contain a 'resources' key")
    if not isinstance(raw_resources, list):
        raise ConfigError("'resources' must be a list")
    if not raw_resources:
        raise ConfigError("'resources' list must not be empty")

    resources: list[Resource] = []
    for i, entry in enumerate(raw_resources, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Resource #{i} must be a mapping")

        missing = _REQUIRED_RESOURCE_KEYS - entry.keys()
        if missing:
            raise ConfigError(
                f"Resource #{i} ('{entry.get('name', '<unnamed>')}') "
                f"is missing required keys: {', '.join(sorted(missing))}"
            )

        name = str(entry["name"])
        url = str(entry["url"])
        resource_path = _resolve_path(entry["path"], repo_root)
        algorithm = _parse_algorithm(entry.get("algorithm", "sha256"), name)
        headers = dict(entry.get("headers", {}))
        timeout = float(entry.get("timeout", _DEFAULT_TIMEOUT))
        retry = int(entry.get("retry", _DEFAULT_RETRY))
        max_size = int(entry.get("max_size", _DEFAULT_MAX_SIZE))

        resources.append(
            Resource(
                name=name,
                url=url,
                path=resource_path,
                algorithm=algorithm,
                headers=headers,
                timeout=timeout,
                retry=retry,
                max_size=max_size,
            )
        )

    return SyncConfig(resources=tuple(resources))


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    """Resolve a resource path relative to the repository root.

    If ``raw_path`` is absolute, return it as-is (after resolving symlinks).
    If relative, join it with ``repo_root``.
    """
    p = Path(raw_path)
    if p.is_absolute():
        return p.resolve()
    return (repo_root / p).resolve()


def _parse_algorithm(value: str, resource_name: str) -> HashAlgorithm:
    """Parse and validate a hash algorithm string.

    Raises:
        ConfigError: If the algorithm is not one of the known values.
    """
    normalized = value.strip().lower()
    if normalized not in _KNOWN_ALGORITHMS:
        raise ConfigError(
            f"Resource '{resource_name}': unknown hash algorithm '{value}'. "
            f"Must be one of: {', '.join(sorted(_KNOWN_ALGORITHMS))}"
        )
    return HashAlgorithm(normalized)


def _substitute_env(raw: Any, env: dict[str, str]) -> Any:
    """Recursively walk the parsed YAML tree and replace ``${VAR}`` tokens.

    Only processes string values. Non-strings are returned unchanged.

    Raises:
        ConfigError: If a referenced environment variable is not defined.
    """
    if isinstance(raw, str):
        return _substitute_in_string(raw, env)
    if isinstance(raw, dict):
        return {k: _substitute_env(v, env) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_substitute_env(item, env) for item in raw]
    return raw


def _substitute_in_string(value: str, env: dict[str, str]) -> str:
    """Replace all ``${VAR}`` occurrences in a string with env values.

    Raises:
        ConfigError: If a referenced variable is not in ``env``.
    """
    def _replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name not in env:
            raise ConfigError(
                f"Environment variable '${var_name}' is not set. "
                f"Please set it or remove the reference from the config."
            )
        return env[var_name]

    return _ENV_VAR_PATTERN.sub(_replacer, value)