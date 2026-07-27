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
│   └── sync.yml                  # GitHub Actions workflow
├── resource_sync/                # Main package
│   ├── __init__.py               # Package init & version
│   ├── __main__.py               # `python -m` entry point
│   ├── cli/                      # CLI layer
│   │   ├── app.py                # CLI bootstrap, orchestration, report
│   │   └── parser.py             # Argument parser
│   ├── domain/                   # Pure domain layer
│   │   ├── models.py             # Pydantic models (Resource, SyncReport, etc.)
│   │   ├── events.py             # Domain events (SyncStarted, ResourceWritten, etc.)
│   │   ├── pipeline.py           # Pipeline declaration (source→validators→transforms→sink)
│   │   └── stream.py             # Stream types, protocols, utilities
│   ├── engine/                   # Engine layer
│   │   ├── config.py             # YAML config loader with env var substitution
│   │   ├── builder.py            # Pipeline builder — assembles pipelines from plugins
│   │   ├── executor.py           # Pipeline executor — runs a single resource pipeline
│   │   └── orchestrator.py       # Sync orchestrator — manages full sync lifecycle
│   ├── eventbus/                 # Event bus
│   │   └── memory.py             # In-memory event bus implementation
│   ├── fetcher/                  # Data source plugins
│   │   └── http.py               # HTTP/HTTPS streaming fetcher
│   ├── plugin/                   # Plugin system
│   │   ├── errors.py             # Plugin exception hierarchy
│   │   ├── registry.py           # Plugin registry + decorator registration
│   │   └── types.py              # Plugin protocol definitions
│   ├── sink/                     # Output destination plugins
│   │   ├── drain.py              # No-op drain sink (dry-run mode)
│   │   ├── git.py                # Git-aware sink (write + commit)
│   │   └── local.py              # Local file sink with two-phase commit
│   ├── transform/                # Stream transform plugins
│   │   ├── identity.py           # Identity transform (pass-through, reference impl)
│   │   └── ...                   # Add custom transforms here
│   └── validator/                # Content validation plugins
│       ├── empty.py              # Empty file detection
│       ├── html_error.py         # HTML error page detection
│       └── size.py               # Max file size enforcement
├── tests/                        # Test suite (see Development section)
├── config.yaml                   # Default configuration
├── pyproject.toml                # Project metadata & dependencies
├── requirements.txt              # Pinned dependencies (pip install)
├── README.md                     # English documentation
└── README.zh-CN.md               # Chinese documentation
```

## Architecture

### Module Dependency Graph

```
__main__.py → cli/app.py → engine/config.py → domain/models.py (leaf)
                          → engine/orchestrator.py → engine/builder.py → plugin/registry.py
                                                    → engine/executor.py → domain/stream.py
                                                                         → sink/*.py
                                                                         → domain/events.py
                                                                         → eventbus/memory.py
                          → plugin/registry.py (decorator registration)
                          → fetcher/*.py → plugin/registry.py
                          → validator/*.py → plugin/registry.py
                          → sink/*.py → plugin/registry.py
```

### Architecture Overview

- **domain/** — Pure domain models (Pydantic), events, pipeline declarations, and stream type protocols. No I/O, no side effects.
- **engine/** — Configuration loading, pipeline building, execution, and orchestration. The engine assembles pipelines from registered plugins and runs them.
- **plugin/** — Decorator-based plugin registry. Five plugin types: fetcher, validator, transform, sink, observer.
- **fetcher/** — Data source plugins. Each fetcher handles one or more URL schemes (e.g., `http`, `https`).
- **validator/** — Content safety checks applied to every downloaded resource.
- **transform/** — Stream transformations (decompress, decrypt, filter, etc.).
- **sink/** — Output destinations. Local file system, Git-aware writer, drain (dry-run).
- **eventbus/** — In-memory event bus with subscribe/emit pattern.
- **cli/** — Argument parsing and application bootstrap.

### Plugin Registration

Plugins are registered via decorators at import time:

```python
@register_fetcher(schemes=frozenset({"http", "https"}))
class HttpFetcher: ...
```

The `_discover_plugins()` function in `app.py` imports all plugin modules, triggering their decorators.

### Streaming Pipeline

Each resource is processed through a streaming pipeline:

```
Fetch (source) → Validators → Transforms → Hash (tee) → Sink (write)
```

The stream is an `AsyncIterator[bytes]`, allowing O(chunk_size) memory usage regardless of file size. The hash is computed as the stream passes through via `tee_stream()`, avoiding a separate pass.

## License

MIT License. See [LICENSE](LICENSE) for details.