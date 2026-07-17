"""Tests for ``resource_sync.config``."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from resource_sync.config import load_config
from resource_sync.exceptions import ConfigError
from resource_sync.models import HashAlgorithm, Resource, SyncConfig


class TestLoadConfig:
    """Tests for ``load_config``."""

    def test_basic_config(self, tmp_path: Path, sample_config_content: str) -> None:
        """A valid config is parsed into a SyncConfig."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(sample_config_content)

        config = load_config(config_path, env={})
        assert isinstance(config, SyncConfig)
        assert len(config.resources) == 1

        resource = config.resources[0]
        assert resource.name == "test-resource"
        assert resource.url == "https://example.com/data.txt"
        assert str(resource.path).endswith("output/data.txt")
        assert resource.algorithm is HashAlgorithm.SHA256
        assert resource.headers == {}
        assert resource.timeout == 30.0

    def test_with_headers(self, tmp_path: Path, sample_config_with_headers: str) -> None:
        """Custom headers are parsed correctly."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(sample_config_with_headers)

        config = load_config(config_path, env={})
        resource = config.resources[0]
        assert resource.headers == {
            "Authorization": "Bearer secret123",
            "X-Custom": "value",
        }

    def test_multiple_resources(
        self, tmp_path: Path, sample_config_multiple: str
    ) -> None:
        """Multiple resources are all parsed in order."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(sample_config_multiple)

        config = load_config(config_path, env={})
        assert len(config.resources) == 3
        assert config.resources[0].name == "resource-a"
        assert config.resources[0].algorithm is HashAlgorithm.SHA256
        assert config.resources[1].algorithm is HashAlgorithm.SHA1
        assert config.resources[2].algorithm is HashAlgorithm.MD5

    def test_file_not_found(self) -> None:
        """Raises ConfigError when the config file does not exist."""
        with pytest.raises(ConfigError, match="not found"):
            load_config(Path("/nonexistent/config.yaml"))

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Raises ConfigError on invalid YAML."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{{{invalid_yaml}}}")

        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(config_path, env={})

    def test_missing_resources_key(self, tmp_path: Path) -> None:
        """Raises ConfigError when 'resources' key is missing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("other_key: value")

        with pytest.raises(ConfigError, match="'resources' key"):
            load_config(config_path, env={})

    def test_resources_not_list(self, tmp_path: Path) -> None:
        """Raises ConfigError when 'resources' is not a list."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: not_a_list")

        with pytest.raises(ConfigError, match="'resources' must be a list"):
            load_config(config_path, env={})

    def test_empty_resources(self, tmp_path: Path) -> None:
        """Raises ConfigError when 'resources' list is empty."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources: []")

        with pytest.raises(ConfigError, match="not be empty"):
            load_config(config_path, env={})

    def test_missing_required_keys(
        self, tmp_path: Path, config_missing_required_keys: str
    ) -> None:
        """Raises ConfigError when required keys are missing."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_missing_required_keys)

        with pytest.raises(ConfigError, match="missing required keys"):
            load_config(config_path, env={})

    def test_invalid_algorithm(
        self, tmp_path: Path, config_with_invalid_algorithm: str
    ) -> None:
        """Raises ConfigError for unknown hash algorithm."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_with_invalid_algorithm)

        with pytest.raises(ConfigError, match="unknown hash algorithm"):
            load_config(config_path, env={})

    def test_resource_not_mapping(self, tmp_path: Path) -> None:
        """Raises ConfigError when a resource entry is not a dict."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("resources:\n  - not_a_dict")

        with pytest.raises(ConfigError, match="must be a mapping"):
            load_config(config_path, env={})

    def test_top_level_not_mapping(self, tmp_path: Path) -> None:
        """Raises ConfigError when the top-level value is not a mapping."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("just a string")

        with pytest.raises(ConfigError, match="top-level mapping"):
            load_config(config_path, env={})

    def test_timeout_and_retry(self, tmp_path: Path) -> None:
        """Custom timeout and retry are parsed correctly."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
    timeout: 120
    retry: 5
    max_size: 1048576
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={})
        resource = config.resources[0]
        assert resource.timeout == 120.0
        assert resource.retry == 5
        assert resource.max_size == 1048576


class TestEnvVarSubstitution:
    """Tests for environment variable substitution in config."""

    def test_url_substitution(self, tmp_path: Path) -> None:
        """${HOST} in URL is replaced with the env value."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://${HOST}/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"HOST": "my-server.com"})
        assert config.resources[0].url == "https://my-server.com/data.txt"

    def test_path_substitution(self, tmp_path: Path) -> None:
        """${OUTPUT_DIR} in path is replaced with the env value."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://example.com/data.txt"
    path: "${OUTPUT_DIR}/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"OUTPUT_DIR": "custom/path"})
        assert "custom/path/data.txt" in str(config.resources[0].path)

    def test_header_substitution(self, tmp_path: Path) -> None:
        """${TOKEN} in headers is replaced with the env value."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
    headers:
      Authorization: "Bearer ${TOKEN}"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"TOKEN": "abc123"})
        assert config.resources[0].headers["Authorization"] == "Bearer abc123"

    def test_undefined_variable_raises_error(self, tmp_path: Path) -> None:
        """Undefined env var raises ConfigError."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://${UNDEFINED}/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        with pytest.raises(ConfigError, match="not set"):
            load_config(config_path, env={})  # Empty env

    def test_custom_env_overrides_os_environ(self, tmp_path: Path) -> None:
        """The env parameter takes precedence over os.environ."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://${HOST}/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(
            config_path, env={"HOST": "custom-host.com"}
        )
        assert config.resources[0].url == "https://custom-host.com/data.txt"

    def test_multiple_variables(self, tmp_path: Path) -> None:
        """Multiple env vars in the same string are all replaced."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://${HOST}:${PORT}/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"HOST": "api.example.com", "PORT": "8080"})
        assert config.resources[0].url == "https://api.example.com:8080/data.txt"

    def test_nested_variable_not_expanded(self, tmp_path: Path) -> None:
        """Only ${VAR} at the top level of a string is replaced."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://example.com/${ENV}.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"ENV": "production"})
        assert config.resources[0].url == "https://example.com/production.txt"

    def test_no_substitution_needed(self, tmp_path: Path) -> None:
        """Config without env vars is parsed as-is."""
        config_yaml = """\
resources:
  - name: "test"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(config_yaml)

        config = load_config(config_path, env={"SOME_VAR": "value"})
        assert config.resources[0].url == "https://example.com/data.txt"