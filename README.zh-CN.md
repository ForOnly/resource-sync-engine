# Resource Sync Engine — 资源同步引擎

<p align="center">
  <a href="README.md">🇬🇧 English</a> | <a href="README.zh-CN.md">🇨🇳 中文</a>
</p>

一个**基于配置驱动**的资源同步工具。在 YAML 文件中定义远程资源，引擎会自动下载、通过哈希比对，并将变更自动提交到你的 Git 仓库。

## 特性

- 🌐 **HTTP/HTTPS 下载** — 支持可配置的超时、请求头和重试
- 🔍 **哈希比对** — 支持 `sha256`（默认）、`sha1`、`md5`
- 📝 **自动更新** — 仅在内容发生变化时更新文件
- ⏭️ **智能跳过** — 哈希一致时跳过下载
- 🛡️ **内容安全校验** — 空文件检测、大小限制、HTML 错误页面检测
- 🔄 **环境变量替换** — 在 URL、路径、请求头中使用 `${VAR}`
- 🏃 **Dry-Run 模式** — 预览变更而不写入任何文件
- 📊 **同步报告** — 生成结构化的 `sync-report.json`
- 🤖 **GitHub Actions** — 定时运行，自动提交和推送
- 📦 **无变化不提交** — 无资源变更时跳过 Git 提交

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 编写配置

创建 `config.yaml` 文件：

```yaml
resources:
  - name: "my-data"
    url: "https://example.com/data.json"
    path: "data/data.json"
    algorithm: "sha256"
```

### 3. 运行

```bash
# Dry-Run 预览（仅预览，不写入文件）
python -m resource_sync -c config.yaml --dry-run

# 正式同步
python -m resource_sync -c config.yaml
```

## 安装

### 前提条件

- **Python >= 3.11**
- **Git**（用于自动提交功能）

### 克隆并安装

```bash
git clone https://github.com/your-org/resource-sync.git
cd resource-sync
pip install -r requirements.txt
```

### 验证安装

```bash
python -m resource_sync --help
```

应能看到所有可用选项的帮助信息。

## 配置说明

系统由单个 `config.yaml` 文件驱动。以下是完整的配置参考：

### 完整 Schema

```yaml
resources:
  - name: "<string>"              # 必填：资源唯一标识
    url: "<string>"                # 必填：HTTP/HTTPS URL
    path: "<string>"               # 必填：本地文件路径（相对或绝对路径）
    algorithm: "<string>"          # 可选：sha256（默认）、sha1、md5
    timeout: <number>              # 可选：请求超时秒数（默认：30）
    retry: <number>                # 可选：重试次数（默认：3）
    max_size: <number>             # 可选：最大文件大小（字节，默认：524288000）
    headers:                       # 可选：HTTP 请求头
      <key>: "<value>"
```

### 环境变量替换

配置中的 `${VARIABLE}` 引用会在运行时替换为对应的环境变量：

```yaml
resources:
  - name: "api-data"
    url: "https://${API_HOST}/v1/data"
    path: "${DATA_DIR}/data.json"
    algorithm: "sha256"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
```

设置环境变量后运行：

```bash
API_HOST=api.example.com DATA_DIR=./output API_TOKEN=secret123 \
  python -m resource_sync -c config.yaml
```

> **注意**：如果引用的环境变量未设置，引擎会报错退出。

## 使用方式

### 命令行选项

| 选项 | 说明 |
|---|---|
| `-c, --config PATH` | 配置文件路径（默认：`config.yaml`） |
| `--dry-run` | 预览模式 — 下载并比对，但不写入任何文件 |
| `--no-commit` | 写入文件，但跳过 Git 提交/推送 |
| `--repo-root PATH` | Git 仓库根目录（默认：配置文件所在目录） |
| `-v, --verbose` | 启用调试级别日志 |
| `--help` | 显示帮助信息 |

### 使用示例

```bash
# 基本同步
python -m resource_sync

# 指定配置文件
python -m resource_sync -c my-config.yaml

# Dry-Run 预览
python -m resource_sync --dry-run

# 同步但不提交
python -m resource_sync --no-commit

# 详细日志
python -m resource_sync -v

# 指定仓库根目录
python -m resource_sync --repo-root /path/to/repo
```

### 使用 `python -m`

```bash
# 在项目根目录运行：
python -m resource_sync

# 指定配置文件：
python -m resource_sync -c /path/to/config.yaml
```

## 同步报告

每次运行后，会在仓库根目录生成 `sync-report.json` 文件：

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

## Dry-Run 模式

`--dry-run` 参数让你预览将要发生的变化，而不实际执行：

```bash
python -m resource_sync --dry-run -v
```

在 dry-run 模式下：
- ✅ 下载资源并计算哈希
- ✅ 计算本地哈希并进行比对
- ✅ 报告结果（CREATED / UPDATED / SKIPPED / ERROR）
- ❌ **不会写入任何文件到磁盘**
- ❌ **不会执行 Git 提交或推送**

## 哈希算法

| 算法 | 配置值 | 适用场景 |
|---|---|---|
| **SHA-256** | `sha256` | 通用场景（默认） |
| **SHA-1** | `sha1` | 较快，兼容旧系统 |
| **MD5** | `md5` | 最快，非安全场景 |

## 内容安全校验

引擎对每个下载的资源执行三项安全检查：

1. **空文件检测** — 0 字节的文件会被拒绝
2. **最大文件大小** — 通过 `max_size` 配置（默认：500 MB）
3. **HTML 错误页面检测** — 检测服务器返回了 2xx 状态码但内容是 HTML 错误页面的情况（检查前 2048 字节中 `<html>`、`<head>`、`<body>` 标签与 4xx/5xx 标题的组合）

## GitHub Actions

### 添加到你的仓库

1. 创建 `.github/workflows/sync.yml`（本项目中已包含）：

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
      - name: 配置 Git 身份
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      - run: python -m resource_sync -c config.yaml
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}
```

2. 在仓库中添加所需的 Secrets：
   - 进入 **Settings → Secrets and variables → Actions**
   - 添加 `API_TOKEN`、`HOST` 等 Secrets

> **重要**：工作流中必须配置 Git 身份信息，否则提交会失败。项目中已包含 `git config` 步骤。

### 工作流行为

| 触发方式 | 说明 |
|---|---|
| **定时调度** | 每 6 小时运行一次（`0 */6 * * *`） |
| **workflow_dispatch** | 从 Actions 标签页手动触发 |
| **自动提交** | 自动提交并推送变更 |
| **无操作** | 无资源变更时跳过提交 |

## 环境变量

| 变量 | 用途 | 是否必须 |
|---|---|---|
| `GITHUB_ACTIONS` | GitHub Actions 自动设置 | 否 |
| 配置中的 `${VAR}` | URL、路径、请求头中的自定义变量 | 取决于配置 |

在 GitHub Actions 中，通过 `env` 键传递环境变量：

```yaml
- run: python -m resource_sync -c config.yaml
  env:
    API_TOKEN: ${{ secrets.API_TOKEN }}
    HOST: ${{ secrets.HOST }}
```

## 项目结构

```
resource-sync/
├── .github/workflows/
│   └── sync.yml              # GitHub Actions 工作流
├── src/
│   └── resource_sync/
│       ├── __init__.py        # 包初始化与版本号
│       ├── __main__.py        # `python -m` 入口
│       ├── cli.py             # CLI 参数解析与编排
│       ├── config.py          # YAML 加载与环境变量替换
│       ├── content_validator.py  # 内容安全校验
│       ├── downloader.py      # HTTP 下载（含重试）
│       ├── exceptions.py      # 异常层次结构
│       ├── git_ops.py         # Git 暂存、提交、推送
│       ├── hasher.py          # SHA-256/SHA-1/MD5 哈希计算
│       ├── models.py          # Dataclass 与枚举定义
│       └── syncer.py          # 核心同步引擎
├── tests/
│   ├── conftest.py            # 共享测试夹具
│   ├── test_cli.py            # CLI 测试
│   ├── test_config.py         # 配置解析测试
│   ├── test_content_validator.py  # 内容校验测试
│   ├── test_downloader.py     # HTTP 下载测试
│   ├── test_git_ops.py        # Git 操作测试
│   ├── test_hasher.py         # 哈希计算测试
│   └── test_syncer.py         # 同步引擎测试
├── config.yaml                # 默认配置文件
├── requirements.txt           # Python 依赖
├── README.md                  # 英文文档
└── README.zh-CN.md            # 中文文档（本文件）
```

## 开发

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-httpx

# 运行所有测试
python -m pytest tests/ -v

# 运行测试并生成覆盖率报告
pip install pytest-cov
python -m pytest tests/ -v --cov=src/resource_sync
```

### 编写测试

测试套件使用：
- `pytest` — 测试发现与执行
- `pytest-httpx` — 模拟 HTTP 响应
- `tmp_path` fixture — 临时文件
- `unittest.mock` — 模块级模拟

## 架构

### 模块依赖关系图

```
__main__.py → cli.py → config.py ← models.py → exceptions.py（叶子节点）
                      → syncer.py → hasher.py
                                  → downloader.py
                                  → content_validator.py
                      → git_ops.py
```

- **models.py** — 基础 dataclass（Resource、SyncConfig、SyncResult、SyncReport）
- **exceptions.py** — 异常层次结构（ResourceSyncError → ConfigError、DownloadError 等）
- **config.py** — YAML 解析、校验、`${ENV_VAR}` 替换
- **hasher.py** — 流式文件哈希（64 KiB 分块）和内存字节哈希
- **downloader.py** — HTTP/HTTPS 下载，含超时和重试逻辑
- **content_validator.py** — 空文件、大小限制、HTML 错误页面检测
- **syncer.py** — 核心决策树：下载 → 哈希 → 比对 → 创建/更新/跳过
- **git_ops.py** — Git 暂存、提交、推送操作
- **cli.py** — CLI 编排、报告生成、退出码处理

## 许可证

MIT License。详见 [LICENSE](LICENSE) 文件。