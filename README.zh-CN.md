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
│   └── sync.yml                  # GitHub Actions 工作流
├── resource_sync/                # 主包
│   ├── __init__.py               # 包初始化与版本号
│   ├── __main__.py               # `python -m` 入口
│   ├── cli/                      # CLI 层
│   │   ├── app.py                # CLI 启动、编排、报告生成
│   │   └── parser.py             # 参数解析器
│   ├── domain/                   # 纯领域层
│   │   ├── models.py             # Pydantic 模型（Resource, SyncReport 等）
│   │   ├── events.py             # 领域事件（SyncStarted, ResourceWritten 等）
│   │   ├── pipeline.py           # 管道声明（source→validators→transforms→sink）
│   │   └── stream.py             # 流类型、协议、工具函数
│   ├── engine/                   # 引擎层
│   │   ├── config.py             # YAML 配置加载与环境变量替换
│   │   ├── builder.py            # 管道构建器 — 从插件组装管道
│   │   ├── executor.py           # 管道执行器 — 运行单个资源管道
│   │   └── orchestrator.py       # 同步编排器 — 管理完整同步生命周期
│   ├── eventbus/                 # 事件总线
│   │   └── memory.py             # 内存事件总线实现
│   ├── fetcher/                  # 数据源插件
│   │   └── http.py               # HTTP/HTTPS 流式下载器
│   ├── plugin/                   # 插件系统
│   │   ├── errors.py             # 插件异常层次结构
│   │   ├── registry.py           # 插件注册表 + 装饰器注册
│   │   └── types.py              # 插件协议定义
│   ├── sink/                     # 输出端插件
│   │   ├── drain.py              # 无操作 drain sink（dry-run 模式）
│   │   ├── git.py                # Git 感知 sink（写入 + 提交）
│   │   └── local.py              # 本地文件 sink（两阶段提交）
│   ├── transform/                # 流转换插件
│   │   ├── identity.py           # 恒等转换（透传，参考实现）
│   │   └── ...                   # 在此添加自定义转换器
│   └── validator/                # 内容验证插件
│       ├── empty.py              # 空文件检测
│       ├── html_error.py         # HTML 错误页面检测
│       └── size.py               # 最大文件大小限制
├── tests/                        # 测试套件（见"开发"章节）
├── config.yaml                   # 默认配置文件
├── pyproject.toml                # 项目元数据与依赖
├── requirements.txt              # 依赖锁定文件（pip install）
├── README.md                     # 英文文档
└── README.zh-CN.md               # 中文文档（本文件）
```

## 架构

### 模块依赖关系图

```
__main__.py → cli/app.py → engine/config.py → domain/models.py（叶子节点）
                          → engine/orchestrator.py → engine/builder.py → plugin/registry.py
                                                    → engine/executor.py → domain/stream.py
                                                                         → sink/*.py
                                                                         → domain/events.py
                                                                         → eventbus/memory.py
                          → plugin/registry.py（装饰器注册）
                          → fetcher/*.py → plugin/registry.py
                          → validator/*.py → plugin/registry.py
                          → sink/*.py → plugin/registry.py
```

### 架构概述

- **domain/** — 纯领域模型（Pydantic）、事件、管道声明、流类型协议。无 I/O、无副作用。
- **engine/** — 配置加载、管道构建、执行、编排。引擎从注册的插件组装管道并运行。
- **plugin/** — 基于装饰器的插件注册表。五种插件类型：fetcher、validator、transform、sink、observer。
- **fetcher/** — 数据源插件。每个 fetcher 处理一个或多个 URL 协议（如 `http`、`https`）。
- **validator/** — 内容安全检查，应用于每个下载的资源。
- **transform/** — 流转换（解压缩、解密、过滤等）。
- **sink/** — 输出目标。本地文件系统、Git 感知写入器、drain（dry-run）。
- **eventbus/** — 内存事件总线，支持 subscribe/emit 模式。
- **cli/** — 参数解析与应用启动。

### 插件注册

插件通过装饰器在导入时注册：

```python
@register_fetcher(schemes=frozenset({"http", "https"}))
class HttpFetcher: ...
```

`app.py` 中的 `_discover_plugins()` 函数导入所有插件模块，触发其装饰器。

### 流式管道

每个资源通过流式管道处理：

```
Fetch（数据源）→ Validators（验证器）→ Transforms（转换器）→ Hash（哈希，tee）→ Sink（写入）
```

流是 `AsyncIterator[bytes]`，无论文件大小如何，都能保证 O(chunk_size) 的内存使用。哈希通过 `tee_stream()` 在流经过时实时计算，避免额外遍历。

## 许可证

MIT License。详见 [LICENSE](LICENSE) 文件。