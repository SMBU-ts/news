# summaries/raw — 正文提取缓存

## 用途

存放从新闻原文 URL 抓取的纯文本正文，供 `summary_lib.py` 生成中文摘要前做预处理。

## 工作流

```
新闻文章 URL
    │
    ▼
tools/extract_articles.py <date>  ─→  <date>/index.json + NNN.txt（第一轮：urllib 标准请求）
    │
    ├── 失败的 URL（403/超时/JS墙）
    │       │
    │       ├── tools/fetch_new_articles.py <date>  ─→  第二轮：宽松 UA + Referer 伪装
    │       └── tools/playwright_fetch.py <date>    ─→  第三轮：Playwright 反检测
    │
    ▼
summaries/<date>.json  ← 摘要引擎读取正文 → 调 LLM → 生成中文摘要
```

## 目录结构

```
raw/
├── README.md                 ← 本文件
└── <YYYY-MM-DD>/             ← 按日期分目录
    ├── index.json            ← 该日统一索引（标注 round/category/rawfile/ok）
    ├── playwright_remaining.json ← 仍需 Playwright 抓取的 URL
    ├── NNN.txt               ← 正文缓存（仅 ok=True 条目，不提交仓库）
    ├── _junk/                ← 无效提取的正文（cookie 墙/反爬页面），保留备查
    └── ...
```

> 旧版 index.json / mapping 文件在整理时已合并到 `<YYYY-MM-DD>/index.json`。

## index.json 字段

| 字段 | 说明 |
|------|------|
| `url` | 文章原始 URL |
| `title` | 文章标题 |
| `source` | 来源名称（如 钛媒体、Seeking Alpha） |
| `date` | 新闻日期（`2026-07-20`） |
| `category` | 分类（tech / finance / world / ai-daily） |
| `rawfile` | 对应正文文件名（如 `001.txt`），ok=False 时为空 |
| `ok` | 是否成功提取正文 |
| `round` | 提取轮次（1=标准 urllib, 2=宽松抓取, 3=Playwright, 0=仍失败） |

## 统计（2026-07-20 批次）

| 轮次 | 工具 | 成功 |
|------|------|------|
| Round 1 | extract_articles.py（urllib） | 32 |
| Round 2 | fetch_new_articles.py（宽松 UA） | 8 |
| Round 3 | playwright_fetch.py（反检测） | 15 |
| **合计** | | **55 / 68（81%）** |
| 仍失败 | — | 13 |

## 维护说明

- 正文缓存 txt 文件**不提交到仓库**，仅保留映射索引 `index.json`
- 每日期批次的 `_junk/` 存放失败的正文抓取结果，确认无用后可删除
- 每次新增日期批次：运行 `tools/extract_articles.py <date>` → 必要时运行二三轮脚本 → 正文自动写入 `<date>/` 子目录
