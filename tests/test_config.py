"""Tests for Config loader (YAML loading, env var substitution)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from resource_sync.engine.config import Config, ConfigError, load_config


class TestConfigLoading:
    """Config loading from YAML."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        config_data = {
            "resources": [
                {
                    "name": "test",
                    "url": "https://example.com/data.json",
                    "path": str(tmp_path / "data.json"),
                    "algorithm": "sha256",
                }
            ],
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(config_path)
        assert len(config.resources) == 1
        assert config.resources[0].name == "test"

    def test_missing_file(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(Path("/nonexistent/config.yaml"))

    def test_empty_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "empty.yaml"
        config_path.write_text("")
        with pytest.raises(ConfigError, match="top-level mapping"):
            load_config(config_path)

    def test_no_resources(self, tmp_path: Path) -> None:
        config_path = tmp_path / "no_resources.yaml"
        with open(config_path, "w") as f:
            yaml.dump({}, f)
        with pytest.raises(ConfigError, match="resources"):
            load_config(config_path)

    def test_env_var_substitution(self, tmp_path: Path) -> None:
        os.environ["_TEST_TOKEN"] = "secret-token-123"
        config_data = {
            "resources": [
                {
                    "name": "test",
                    "url": "https://example.com/data.json",
                    "path": str(tmp_path / "data.json"),
                    "algorithm": "sha256",
                    "headers": {"Authorization": "Bearer ${_TEST_TOKEN}"},
                }
            ],
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(config_path)
        assert config.resources[0].headers["Authorization"] == "Bearer secret-token-123"
        del os.environ["_TEST_TOKEN"]


class TestConfigProperties:
    """Config property accessors."""

    def test_default_sink(self, tmp_path: Path) -> None:
        config = Config(
            resources=[],
            engine_config={},
            repo_root=tmp_path,
        )
        assert config.sink_name == "local"
        assert config.max_concurrency == 1
        assert config.observer_configs == []

    def test_custom_sink(self, tmp_path: Path) -> None:
        config = Config(
            resources=[],
            engine_config={"sink": "git", "max_concurrency": "4"},
            repo_root=tmp_path,
        )
        assert config.sink_name == "git"
        assert config.max_concurrency == 4

    def test_invalid_concurrency(self, tmp_path: Path) -> None:
        """Invalid concurrency values should default to 1."""
        config = Config(
            resources=[],
            engine_config={"max_concurrency": "invalid"},
            repo_root=tmp_path,
        )
        assert config.max_concurrency == 1

    def test_empty_observers(self, tmp_path: Path) -> None:
        config = Config(
            resources=[],
            engine_config={},
            repo_root=tmp_path,
        )
        assert config.observer_configs == []

    def test_non_list_observers(self, tmp_path: Path) -> None:
        """Non-list observer configs should be safely handled."""
        config = Config(
            resources=[],
            engine_config={"observers": "not-a-list"},
            repo_root=tmp_path,
        )
        assert config.observer_configs == []