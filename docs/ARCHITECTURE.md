# 每日新闻站 · 系统架构

## 数据流总览

```
┌──────────────┐     ┌──────────────┐
│  feeds.yaml  │     │  AI HOT API  │
│ (RSS 源配置)  │     │ (aihot.virxact│
│              │     │   .com)      │
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌──────────────┐     ┌──────────────────┐
│ build_rss.py │     │build_dashboard.py│
│              │     │                  │
│ · 抓取 RSS    │     │ · 调用 AI HOT    │
│ · 解析 XML    │     │ · 按 5 版块展示  │
│ · 去重 Top20 │     │ · 生成摘要       │
│ · 生成摘要    │     │                  │
└──────┬───────┘     └──────┬───────────┘
       │                    │
       │    ┌───────────────┘
       │    │
       ▼    ▼
  YYYY-MM-DD/
  ├── index.html          ← 当日汇总
  ├── ai-daily/
  │   └── ai-daily-YYYY-MM-DD.html
  ├── tech/
  │   └── tech-YYYY-MM-DD.html
  ├── finance/
  │   └── finance-YYYY-MM-DD.html
  └── world/
      └── world-YYYY-MM-DD.html

              │
              ▼
      ┌───────────────┐
      │build_archive.py│
      │               │
      │ · index.html  │ ← 首页（日期导航）
      │ · archive.html│ ← 归档（跨日期分类汇总）
      │ · sitemap.xml │ ← SEO 站点地图
      │ · robots.txt  │ ← 爬虫规则
      │ · 各日汇总页   │ ← YYYY-MM-DD/index.html
      └───────┬───────┘
              │
              ▼
      ┌───────────────┐
      │  git push     │
      │     ↓         │
      │ GitHub Actions│
      │     ↓         │
      │ GitHub Pages  │
      │ smbu-ts.github│
      │   .io/news/   │
      └───────────────┘
```

## 热度排名系统（2026-07-21 新增）

`ranking.py` + `engagement.py` 实现多因子评分排名，在 `build_rss.py` 去重后、渲染前介入：

- **评分公式**：SCORE = w_e×S_e + w_r×S_r + w_a×S_a + w_i×S_i + w_c×S_c（各因子 [0,1]，加权和 ×100）
- **5 个因子**：互动数据（HN Firebase API 获取真实 score/comments）、时效性衰减（指数半衰期可配）、信源权威权重、标题信息量、跨源报道加成
- **排名方法**：`top_n`（保留前N条）/ `percentile`（前X%）/ `threshold`（最低分），分类级可配
- **配置**：集中在 `feeds.yaml` 的 `_ranking` 节，含 defaults + 分类级覆盖；源级新增 `weight` / `engagement` / `max_articles` 字段
- **向后兼容**：无 `_ranking` 配置时保持原有行为（按时间排序 + Top 20）
- `_ensure_diversity()` 保障来源多样性（每源至少保留1条）

## 构建管道详解

### 1. build_dashboard.py — AI 日报

**数据源**：AI HOT API（`https://aihot.virxact.com/api/daily`）

**处理流程**：
1. 请求当日 AI 日报 JSON
2. 按 5 个版块归类：模型发布/更新、产品发布/更新、行业动态、论文研究、技巧与观点
3. 对每篇文章调用 `summary_lib.summarize()` 生成中文摘要
4. 渲染内嵌 HTML/CSS 模板 → 输出到 `YYYY-MM-DD/ai-daily/`

### 2. build_rss.py — 科技/财经/国际 RSS

**数据源**：`feeds.yaml` 中定义的 RSS/Atom 订阅源

**处理流程**：
1. 读取 `feeds.yaml`，遍历每个分类的订阅源列表
2. 用 `urllib` + `xml.etree.ElementTree` 抓取并解析 RSS 2.0 / Atom
3. 按标题去重，然后经热度排名系统筛选（`ranking.py`）
4. 对每篇文章调用 `summary_lib.summarize()` 生成摘要
5. 渲染 HTML → 输出到 `YYYY-MM-DD/<cat>/`

**容错**：单个源抓取失败自动跳过并告警，不影响同分类其他源。

### 3. build_archive.py — 站点构建器

**职责**：聚合所有已有日期目录，生成导航和 SEO 文件。

**产出**：
- `index.html`：首页，按日期倒序列出所有归档日
- `archive.html`：全站归档，跨日期按分类汇总
- `YYYY-MM-DD/index.html`：每日汇总页
- `sitemap.xml`：列出所有页面 URL（绝对路径）
- `robots.txt`：Allow all + sitemap 指向

**分类元数据**集中在 `CATEGORY_LABELS` / `CAT_COLORS` / `CAT_ICONS`。新增分类时需同步更新这三张表。

**站点路径**：默认 `/news/`（GitHub 项目页），设 `CUSTOM_DOMAIN` 后改为 `/`。

### 4. build_all.py — 一键编排

依次调用 `build_dashboard.py` → `build_rss.py` → `build_archive.py`，支持日期参数。

## 正文提取管线（summaries/raw/）

生成中文摘要之前，需要从原文 URL 提取纯文本正文。这是一个**三轮递进**的离线流程，与主构建管道解耦：

```
文章 URL 列表
    │
    ├─ Round 1: tools/extract_articles.py
    │   · 标准 urllib + User-Agent
    │   · 成功 → raw/NNN.txt + index.json (round=1)
    │   · 失败（403/超时/JS墙）→ index.json (ok=False)
    │
    ├─ Round 2: tools/fetch_new_articles.py
    │   · 随机 UA + Referer:google 伪装
    │   · 目标：第一轮失败的 URL
    │   · 成功 → raw/NNN.txt + index.json (round=2)
    │
    └─ Round 3: tools/playwright_fetch.py
        · Playwright + Chromium + 反检测
        · 目标：前两轮仍失败的 URL（如 france24 Cloudflare）
        · 成功 → raw/NNN.txt + index.json (round=3)
        · 仍失败 → remaining.json
```

**索引文件**：`summaries/raw/<date>/index.json` 是统一索引，每条记录包含 `url`、`title`、`source`、`date`、`category`、`rawfile`（正文文件名）、`ok`（是否成功）、`round`（提取轮次）。

**正文缓存**：`.txt` 文件为纯文本正文（最大 5000 字符），不提交到仓库。仅 `index.json` 提交。

**统计数据（2026-07-20 批次）**：

| 轮次 | 成功 | 工具 |
|------|------|------|
| Round 1 | 32 | urllib 标准 |
| Round 2 | 8 | 宽松 UA |
| Round 3 | 15 | Playwright |
| 仍失败 | 13 | — |
| **合计** | **55/68 (81%)** | |

详见 [summaries/raw/README.md](../summaries/raw/README.md)。

## 反爬策略分层

按难度递增分为三层，对应不同场景：

| 层级 | 工具 | 策略 | 适用场景 |
|------|------|------|----------|
| L1 | `build_rss.py` 内置 urllib | 标准 HTTP 请求 + User-Agent | RSS/Atom 源（多数直接可读） |
| L2 | `tools/crawler.py` | 随机 UA、Referer 伪装、间隔抖动、自动重试 | 有轻度反爬的网页正文 |
| L3 | `tools/playwright_fetch.py` | Playwright + Chromium + 反检测（隐藏 webdriver、模拟插件、真实 viewport） | Cloudflare / JS 渲染页面 |

**已知顽固源**：
- `x.com`：TCP 层封杀（沙箱网络限制），需本机运行 Playwright
- `sky.com`：Akamai CDN IP 层拦截，非浏览器指纹问题
- 部分 RSS 源（BBC/AlJazeera/NYT/DW）在沙箱网络被屏蔽，本机/CI 正常

## 摘要引擎

### 原理

摘要由 **AI 助手离线生成**，构建时 `summary_lib.py` 直接读取预生成缓存，无需运行时调用外部 API。

```
AI 助手工作流：
  │
  ├─→ ① 读取 summaries/raw/<date>/NNN.txt（已提取的纯文本正文）
  │
  ├─→ ② 逐篇生成 100–200 字中文摘要
  │
  └─→ ③ 写入 summaries/<date>.json（{url: summary} 映射，提交仓库）

构建时 summary_lib.summarize(url, title)：
  │
  ├─→ ① 查 summaries/<date>.json（AI 助手预生成）
  │     命中 → 直接返回
  │
  └─→ ② 未命中 → 回退「暂无法生成概括」
```

`summary_lib.py` 是标准库实现，零第三方依赖。旧版 DeepSeek API 回退路径保留在代码中但日常不使用。

### 预生成缓存机制

`summaries/<date>.json` 是一个 `{url: summary}` 映射。提交进仓库后：

- 任何人重跑构建都能复用真实摘要，**无需配置 API Key**
- 缺失 URL 才回退到「暂无法生成概括」
- `build_rss.py` / `build_dashboard.py` 的 `main()` 已调用 `load_precomputed()`

## 部署流程

1. 本地构建：`python build_all.py`
2. `git add . && git commit && git push origin main`
3. GitHub Actions（`.github/workflows/deploy.yml`）自动触发
4. 约 1 分钟后部署到 `https://smbu-ts.github.io/news/`

**Pages 配置**：源为 main 分支、GitHub Actions。`.nojekyll` 空文件禁用 Jekyll 处理。

## 工具目录

| 工具 | 用途 |
|------|------|
| `crawler.py` | 通用宽松型爬虫（随机 UA、抖动、重试、JSON 输出） |
| `extract_articles.py` | 从 HTML 卡片提取文章链接，抓取正文存 `summaries/raw/` |
| `fetch_new_articles.py` | 批量抓取已知可破的文章 |
| `inject_summary_button.py` | 向已有 HTML 注入「原文概括」按钮+面板（幂等） |
| `playwright_fetch.py` | Playwright 反检测抓取（破 Cloudflare 等） |
| `api_push.py` / `api_push_all.py` | 通过 GitHub Git Data API 推送（沙箱内 HTTPS git push 被阻止时的备用方案） |
| `repair_html.py` | HTML 卡片修复：从污染页面提取干净字段后用原模板重建 |
| `patch_summaries.py` | 外科替换 HTML 中的回退摘要文本（推荐用 `repair_html.py` 代替） |

## 目录约定

```
summaries/
├── <date>.json       ← 预生成摘要缓存（提交到仓库）
└── raw/              ← 正文缓存（临时，不提交）
    ├── NNN.txt
    └── *_mapping.json

tools/                ← 离线辅助脚本（不直接参与主构建流程）
```

## 样式与前端

- `assets/css/style.css`：全站共享样式（渐变 Hero、玻璃拟态导航、卡片系统、响应式）
- `assets/js/main.js`：滚动揭示 IntersectionObserver 动效
- 文章页样式内嵌在 `build_rss.py` / `build_dashboard.py` 中
- 「原文概括」按钮使用内联 JS 事件委托，展开/收起无需额外请求
