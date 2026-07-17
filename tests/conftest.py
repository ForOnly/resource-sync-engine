"""Shared pytest fixtures for Resource Sync Engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_config_content() -> str:
    """Return sample config YAML content."""
    return """\
resources:
  - name: "test-resource"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
"""


@pytest.fixture
def sample_config_with_env() -> str:
    """Return sample config with environment variable references."""
    return """\
resources:
  - name: "env-resource"
    url: "https://${HOST}/data.txt"
    path: "${OUTPUT_DIR}/data.txt"
    algorithm: "sha256"
    headers:
      Authorization: "Bearer ${TOKEN}"
"""


@pytest.fixture
def sample_config_with_headers() -> str:
    """Return sample config with custom headers."""
    return """\
resources:
  - name: "test-resource"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha256"
    headers:
      Authorization: "Bearer secret123"
      X-Custom: "value"
"""


@pytest.fixture
def sample_config_multiple() -> str:
    """Return sample config with multiple resources."""
    return """\
resources:
  - name: "resource-a"
    url: "https://example.com/a.txt"
    path: "data/a.txt"
    algorithm: "sha256"

  - name: "resource-b"
    url: "https://example.com/b.txt"
    path: "data/b.txt"
    algorithm: "sha1"

  - name: "resource-c"
    url: "https://example.com/c.txt"
    path: "data/c.txt"
    algorithm: "md5"
"""


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with a config.yaml file."""
    return tmp_path


@pytest.fixture
def config_with_invalid_algorithm() -> str:
    """Return config with an unknown hash algorithm."""
    return """\
resources:
  - name: "bad-algo"
    url: "https://example.com/data.txt"
    path: "output/data.txt"
    algorithm: "sha512"
"""


@pytest.fixture
def config_missing_required_keys() -> str:
    """Return config missing required keys."""
    return """\
resources:
  - name: "missing-url"
    path: "output/data.txt"
"""