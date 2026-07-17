# Resource Sync Engine

<p align="center">
  <a href="README.md">🇬🇧 English</a> | <a href="README.zh-CN.md">🇨🇳 中文</a>
</p>

A **config-driven** resource synchronization tool. Define remote resources in a YAML file, and the engine will download them, compare by hash, and auto-commit any changes to your Git repository.

## Features

- 🌐 **HTTP/HTTPS download** with configurable timeouts, headers, and retries
- 🔍 **Hash comparison** — `sha256` (default), `sha1`, or `md5`
- 📝 **Auto-update** — files are updated only when content changes
- ⏭️ **Smart skip** — identical hashes skip the download entirely
- 🛡️ **Content validation** — empty file detection, size limits, HTML error page detection
- 🔄 **Environment variable substitution** — `${VAR}` in URLs, paths, and headers
- 🏃 **Dry-run mode** — preview changes without writing anything
- 📊 **Sync reports** — structured `sync-report.json` output
- 🤖 **GitHub Actions** — scheduled runs with auto-commit and push
- 📦 **No changes, no commit** — skips Git commit when nothing changed

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

Create a `config.yaml` file:

```yaml
resources:
  - name: "my-data"
    url: "https://example.com/data.json"
    path: "data/data.json"
    algorithm: "sha256"
```

### 3. Run

```bash
# Dry-run (preview only — no files written)
python -m resource_sync -c config.yaml --dry-run

# Live sync
python -m resource_sync -c config.yaml
```

## Installation

### Prerequisites

- **Python >= 3.11**
- **Git** (for auto-commit functionality)

### Clone & Install

```bash
git clone https://github.com/your-org/resource-sync.git
cd resource-sync
pip install -r requirements.txt
```

### Verify

```bash
python -m resource_sync --help
```

You should see the help output with all available options.

## Configuration

The system is driven by a single `config.yaml` file. Below is a complete reference:

### Full Schema

```yaml
resources:
  - name: "<string>"              # Required: Unique resource identifier
    url: "<string>"                # Required: HTTP/HTTPS URL
    path: "<string>"               # Required: Local file path (relative or absolute)
    algorithm: "<string>"          # Optional: sha256 (default), sha1, md5
    timeout: <number>              # Optional: Request timeout in seconds (default: 30)
    retry: <number>                # Optional: Number of retry attempts (default: 3)
    max_size: <number>             # Optional: Max file size in bytes (default: 524288000)
    headers:                       # Optional: HTTP headers
      <key>: "<value>"
```

### Environment Variable Substitution

Any `${VARIABLE}` reference in the config is replaced with the corresponding environment variable at runtime:

```yaml
resources:
  - name: "api-data"
    url: "https://${API_HOST}/v1/data"
    path: "${DATA_DIR}/data.json"
    algorithm: "sha256"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
```

Run with environment variables set:

```bash
API_HOST=api.example.com DATA_DIR=./output API_TOKEN=secret123 \
  python -m resource_sync -c config.yaml
```

> **Note**: If a referenced environment variable is not set, the engine will exit with an error.

## Usage

### Command-Line Options

| Option | Description |
|---|---|
| `-c, --config PATH` | Path to config YAML (default: `config.yaml`) |
| `--dry-run` | Preview changes — download and compare but write nothing |
| `--no-commit` | Write files to disk but skip Git commit/push |
| `--repo-root PATH` | Git repository root (default: config file's parent directory) |
| `-v, --verbose` | Enable debug-level logging |
| `--help` | Show help message and exit |

### Examples

```bash
# Basic sync
python -m resource_sync

# Custom config file
python -m resource_sync -c my-config.yaml

# Dry-run preview
python -m resource_sync --dry-run

# Sync without committing
python -m resource_sync --no-commit

# Verbose logging
python -m resource_sync -v

# Custom repo root
python -m resource_sync --repo-root /path/to/repo
```

### Using `python -m`

```bash
# From the project root:
python -m resource_sync

# With explicit config:
python -m resource_sync -c /path/to/config.yaml
```

## Sync Report

After each run, a `sync-report.json` file is generated in the repository root:

```json
{
  "run_id": "a1b2c3d4e5f6",
  "timestamp": "2026-07-17T14:30:00+00:00",
  "dry_run": false,
  "summary": {
    "created": 1,
    "updated": 2,
    "skipped": 5,
    "error": 0
  },
  "results": [
    {
      "resource_name": "example-json",
      "status": "created",
      "local_hash": null,
      "remote_hash": "sha256:abc123...",
      "error_message": null,
      "dry_run": false
    }
  ]
}
```

## Dry-Run Mode

The `--dry-run` flag lets you preview what would happen without making any changes:

```bash
python -m resource_sync --dry-run -v
```

In dry-run mode:
- ✅ Resources are downloaded and hashed
- ✅ Local hashes are computed and compared
- ✅ Results are reported (CREATED / UPDATED / SKIPPED / ERROR)
- ❌ **No files are written to disk**
- ❌ **No Git commit or push is made**

## Hash Algorithms

| Algorithm | Config Value | Use Case |
|---|---|---|
| **SHA-256** | `sha256` | General purpose (default) |
| **SHA-1** | `sha1` | Faster, legacy compatibility |
| **MD5** | `md5` | Fastest, non-security use cases |

## Content Validation

The engine performs three safety checks on every downloaded resource:

1. **Empty file detection** — files with 0 bytes are rejected
2. **Maximum file size** — configurable via `max_size` (default: 500 MB)
3. **HTML error page detection** — detects when a server returns an HTML error page with a 2xx status code (checks for `<html>`, `<head>`, or `<body>` tags combined with a 4xx/5xx title within the first 2048 bytes)

## GitHub Actions

### Adding to Your Repository

1. Create `.github/workflows/sync.yml` (included in this project):

```yaml
name: Resource Sync

on:
  schedule:
    - cron: "0 */6 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: "pip"
      - run: pip install -r requirements.txt
      - name: Configure Git identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      - run: python -m resource_sync -c config.yaml
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}
```

2. Add any required secrets in your repository:
   - Go to **Settings → Secrets and variables → Actions**
   - Add secrets like `API_TOKEN`, `HOST`, etc.

> **Important**: The workflow must configure a Git identity before committing, otherwise the commit will fail. The workflow above includes the required `git config` step.

### Workflow Behavior

| Trigger | Description |
|---|---|
| **Schedule** | Runs every 6 hours (`0 */6 * * *`) |
| **workflow_dispatch** | Manual trigger from the Actions tab |
| **Auto-commit** | Commits and pushes changes automatically |
| **No-op** | Skips commit if no resources changed |

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `GITHUB_ACTIONS` | Set automatically by GitHub Actions | No |
| `${VAR}` in config | Custom variables for URLs, paths, headers | Depends on config |

In GitHub Actions, pass environment variables via the `env` key:

```yaml
- run: python -m resource_sync -c config.yaml
  env:
    API_TOKEN: ${{ secrets.API_TOKEN }}
    HOST: ${{ secrets.HOST }}
```

## Project Structure

```
resource-sync/
├── .github/workflows/
│   └── sync.yml              # GitHub Actions workflow
├── src/
│   └── resource_sync/
│       ├── __init__.py        # Package init & version
│       ├── __main__.py        # `python -m` entry point
│       ├── cli.py             # CLI argument parsing & orchestration
│       ├── config.py          # YAML loader with env var substitution
│       ├── content_validator.py  # Content safety checks
│       ├── downloader.py      # HTTP download with retries
│       ├── exceptions.py      # Exception hierarchy
│       ├── git_ops.py         # Git stage, commit, push
│       ├── hasher.py          # SHA-256/SHA-1/MD5 hashing
│       ├── models.py          # Dataclasses & enums
│       └── syncer.py          # Core sync engine
├── tests/
│   ├── conftest.py            # Shared test fixtures
│   ├── test_cli.py            # CLI tests
│   ├── test_config.py         # Config parser tests
│   ├── test_content_validator.py  # Content validation tests
│   ├── test_downloader.py     # HTTP download tests
│   ├── test_git_ops.py        # Git operation tests
│   ├── test_hasher.py         # Hash computation tests
│   └── test_syncer.py         # Sync engine tests
├── config.yaml                # Default configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-httpx

# Run all tests
python -m pytest tests/ -v

# Run with coverage
pip install pytest-cov
python -m pytest tests/ -v --cov=src/resource_sync
```

### Writing Tests

The test suite uses:
- `pytest` for test discovery and execution
- `pytest-httpx` for mocking HTTP responses
- `tmp_path` fixture for temporary files
- `unittest.mock` for module-level mocking

## Architecture

### Module Dependency Graph

```
__main__.py → cli.py → config.py ← models.py → exceptions.py (leaf)
                      → syncer.py → hasher.py
                                  → downloader.py
                                  → content_validator.py
                      → git_ops.py
```

- **models.py** — Foundation dataclasses (Resource, SyncConfig, SyncResult, SyncReport)
- **exceptions.py** — Exception hierarchy (ResourceSyncError → ConfigError, DownloadError, etc.)
- **config.py** — YAML parsing, validation, `${ENV_VAR}` substitution
- **hasher.py** — Streaming file hashing (64 KiB chunks) and in-memory byte hashing
- **downloader.py** — HTTP/HTTPS download with timeout and retry logic
- **content_validator.py** — Empty file, size limit, and HTML error page detection
- **syncer.py** — Core decision tree: download → hash → compare → create/update/skip
- **git_ops.py** — Git stage, commit, and push operations
- **cli.py** — CLI orchestration, report generation, exit code handling

## License

MIT License. See [LICENSE](LICENSE) for details.