# CLAUDE.md — 每日新闻站

基于 GitHub Pages 的多分类静态新闻站点。Python 脚本从 RSS + AI HOT API 抓取新闻，生成 HTML 并自动部署到 `https://smbu-ts.github.io/news/`。

## 构建命令

```bash
python build_all.py              # 一键：dashboard + rss + archive（默认今天）
python build_all.py 2026-07-20   # 指定日期

# 分步：
python build_dashboard.py          # AI 日报（数据源：AI HOT API）
python build_rss.py                # 科技/财经/国际 RSS（读取 feeds.yaml）
python build_archive.py            # 重建首页/归档/sitemap/robots.txt
```

- 摘要功能需要 `DEEPSEEK_API_KEY` 或 `SUMMARY_API_KEY` 环境变量；未配置时所有摘要显示「暂无法生成概括」，站点其他功能不受影响。
- `build_all.py` / `build_rss.py` / `build_dashboard.py` 均支持日期参数，默认今天。

## 架构概要

```
feeds.yaml (RSS源配置)          AI HOT API
       │                            │
       ▼                            ▼
   build_rss.py              build_dashboard.py
       │                            │
       └──────────┬─────────────────┘
                  ▼
         YYYY-MM-DD/<分类>/  下的 HTML 页面
                  │
                  ▼
         build_archive.py  ← 重建 index.html / archive.html / sitemap / robots.txt
                  │
                  ▼
         git push → GitHub Actions → 部署到 smbu-ts.github.io/news/
```

- **数据源**：科技/财经/国际 → RSS/Atom（`feeds.yaml`）；AI 日报 → AI HOT API
- **输出**：`YYYY-MM-DD/<cat>/<cat>-YYYY-MM-DD.html` + 每日 `index.html`
- **站点前缀**：统一用 `/news/`（GitHub 项目页子路径），sitemap 用绝对 URL
- **摘要**：由 AI 助手逐篇阅读原文正文，生成 100–200 字中文摘要，写入 `summaries/<date>.json` 提交仓库。构建时 `summary_lib.py` 读取 JSON 复用，点击按钮仅展开/收起。

## 环境变量

| 变量 | 用途 | 必需 |
|------|------|------|
| `CUSTOM_DOMAIN` | 自定义域名（设置后站点路径改为 `/`，生成 CNAME） | 否 |

> 旧版 DeepSeek API 密钥（`DEEPSEEK_API_KEY` / `SUMMARY_API_KEY`）已废弃。`summary_lib.py` 仍保留 API 回退路径作为兜底，但日常摘要由 AI 助手生成后写入 `summaries/<date>.json`，构建时直接复用。

## 关键约定

### 生成每日新闻的完整流程（六步）

1. **拉数据**：`build_dashboard.py <date>`（AI HOT）+ `build_rss.py <date>`（RSS）→ 拿到文章 URL 列表
2. **抓正文**：三轮递进提取原文正文到 `summaries/raw/<date>/`（见下方「正文提取管线」）
3. **生成摘要**：AI 助手逐篇阅读 `raw/<date>/NNN.txt`，输出 100–200 字中文摘要 → 写入 `summaries/<date>.json`
4. **渲染 HTML**：重跑 `build_rss.py <date>` + `build_dashboard.py <date>`，`summary_lib` 读到预生成 JSON 直接复用
5. **重建站点**：`build_archive.py` → 首页/归档/sitemap
6. **推送部署**：git push → GitHub Actions → `https://smbu-ts.github.io/news/`

### 摘要优先级（`summary_lib.py` 内部）

1. `summaries/<date>.json`（AI 助手预生成，已提交仓库）→ 直接复用
2. 回退「暂无法生成概括」（缺失 URL 时）

逻辑集中在 `summary_lib.py`（标准库实现，零第三方依赖）。

### 预生成摘要的提交规则
把 `summaries/<date>.json` 提交进仓库后，任何人重跑构建都能复用真实摘要，无需 API Key。

### 反爬工具链（难度递增）
1. `build_rss.py` 内置 urllib → RSS/Atom 抓取
2. `tools/crawler.py` → 通用宽松爬虫（随机 UA、间隔抖动、自动重试）
3. `tools/playwright_fetch.py` → Playwright 反检测（破 Cloudflare 等 JS 墙）

### 正文提取 → 摘要生成管线（三轮递进）
摘要生成前需先从原文 URL 抓取纯文本正文，存入 `summaries/raw/`：

1. **Round 1**：`tools/extract_articles.py`（标准 urllib）→ 生成 `raw/<date>/index.json` + `NNN.txt`
2. **Round 2**：`tools/fetch_new_articles.py`（宽松 UA + Referer 伪装）→ 补第一轮失败的
3. **Round 3**：`tools/playwright_fetch.py`（Playwright 反检测）→ 破 JS 渲染/Cloudflare

`raw/<date>/index.json` 是统一索引，标注每条 URL 的轮次、正文文件名、成功与否。正文 txt 不提交仓库，索引 json 提交。
详见 [summaries/raw/README.md](summaries/raw/README.md)。

### 站点生成约定
- `build_archive.py` 负责所有聚合页面和 SEO 文件
- 分类元数据在 `build_archive.py` 的 `CATEGORY_LABELS` / `CAT_COLORS` / `CAT_ICONS`
- 新增分类需同时改 `feeds.yaml` + `build_archive.py` 的三张表

## 红线

- **不可删除 `.workbuddy/` 目录**——存储项目记忆和会话数据
- **不可跳过 git hooks**（`--no-verify`、`--no-gpg-sign`）
- **不可在 CLAUDE.md 中追加历史叙事 blockquote**（"X 时刻起 Y 上线"之类——这类内容归 git log）
- `.gitignore` 已排除 `.workbuddy/`、`__pycache__/`、`output/`、系统文件，部署产物干净

## 沙箱限制

- BBC / Al Jazeera / NYT / DW 等部分 RSS 源被沙箱网络策略屏蔽
- `gh` CLI 不在 PATH，需全路径 `"C:/Program Files/GitHub CLI/gh.exe"`
- 沙箱内 GitHub 可访问（git ls-remote 成功），但部分外网受限制
- 本机 / CI 环境无上述限制

## 深入文档

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 项目介绍、本地构建、发布指南、SEO 说明 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构、构建管道、反爬策略、摘要引擎、部署流程 |
| [feeds.yaml](feeds.yaml) | RSS 订阅源配置（分类 → 源清单） |
| [tools/](tools/) | 离线辅助脚本目录 |
