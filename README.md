# 每日新闻 · GitHub Pages 静态站点

一个基于 **GitHub Pages** 的多页静态新闻档案站点：按日期归档、页面间统一导航、支持自定义域名、每次提交自动部署，并具备 SEO 基础结构。

## 目录结构

```
.
├── .github/workflows/deploy.yml   # GitHub Actions：推送即自动部署
├── .nojekyll                      # 禁用 Jekyll，保留原始目录结构
├── CNAME                          # 仅自定义域名时由 build_archive.py 生成（见下文）
├── robots.txt                     # 由 build_archive.py 生成
├── sitemap.xml                    # 由 build_archive.py 生成（绝对 URL）
├── index.html                     # 首页：按日期倒序的导航入口（生成）
├── archive.html                   # 归档页：跨日期按分类汇总（生成）
├── about.html                     # 关于页（静态）
├── assets/css/style.css           # 全站共享样式
├── 2026-07-20/                    # 某一天
│   ├── index.html                 # 当日汇总页：可点击新闻链接（生成）
│   └── ai-daily/                  # 分类子文件夹
│       └── ai-daily-2026-07-20.html   # 新闻原文
├── build_dashboard.py             # 生成 AI 日报报文（数据源：AI HOT）
├── feeds.yaml                     # RSS 订阅源配置（分类 → 源清单）
├── build_rss.py                   # 读取 feeds.yaml，生成各分类 RSS 报文
├── build_all.py                   # 一键编排：dashboard + rss + archive
└── build_archive.py               # 生成首页/归档/汇总/sitemap（站点构建器）
```

## 本地构建

```bash
python build_archive.py     # 重新生成 index.html / archive.html / 各日 index.html / sitemap.xml / robots.txt
```

> 链接使用相对于站点根的路径（首页 `/`、当日 `/2026-07-20/`），由 `build_archive.py` 自动加发布前缀。
> 默认构建目标为 GitHub 项目页 `https://smbu-ts.github.io/news/`（链接前缀 `/news/`）；设 `CUSTOM_DOMAIN`
> 环境变量后改为自定义域名、站点部署在根路径 `/`。

## 新增一天的新闻

最简便：直接运行一键编排脚本，它会依次生成 AI 日报、所有 RSS 分类，并重建全站：

```bash
python build_all.py              # 默认今天
python build_all.py 2026-07-20   # 指定日期
```

若想手动分步：

1. 运行 `build_dashboard.py` 生成当日报文（如 `ai-daily-2026-07-20.html`）。
2. 运行 `build_rss.py` 按 `feeds.yaml` 生成各分类报文（如 `tech-2026-07-20.html` 等），自动写入 `YYYY-MM-DD/<分类>/`。
3. 运行 `build_archive.py` 重建全部页面与站点地图。
4. 提交并推送。

## 扩展更多新闻分类（RSS 订阅源）

除 AI 日报（`build_dashboard.py` 调用 AI HOT）外，其余分类由 RSS 订阅源聚合生成，数据源完全可配置、零 API Key。

- **`feeds.yaml`**：分类 → 订阅源清单（每个源含 `name` 与 `url`）。当前启用 `tech`（科技）/`finance`（财经）/`world`（国际）三个分类，每个分类下列出若干 RSS 2.0 / Atom 源。
- **`build_rss.py`**：读取 `feeds.yaml`，抓取并解析各源，去重后保留每分类最新的 20 条，写入 `YYYY-MM-DD/<分类>/<分类>-YYYY-MM-DD.html`。抓取失败的单个源会被自动跳过并告警，不影响其他源与分类。

新增一个分类只需两步：

1. 在 `feeds.yaml` 增加一级键（如 `sports:`）并列出其订阅源；
2. 在 `build_archive.py` 的 `CATEGORY_LABELS` / `CAT_COLORS` / `CAT_ICONS` 中补上对应中文名、配色与图标（`tech`/`finance`/`world`/`sports`/`health`/`culture` 已内置）。

之后 `build_archive.py` 会自动扫描新分类所在的子文件夹并渲染到首页、归档页与当日汇总页，无需改动归档逻辑。

## 原文概括（自动摘要）

科技 / 财经 / 国际 / AI 日报四类文章页中，每篇文章的「阅读原文」旁都有一个 **「原文概括」** 按钮。点击后会在按钮下方展开一段约 100–200 字的中文摘要；若摘要缺失，则显示友好提示 **「暂无法生成概括」**。

摘要采用 **AI 助手离线生成 + 构建时复用** 的模式：

1. AI 助手阅读已抓取的原文正文（`summaries/raw/<date>/`），逐篇生成中文摘要
2. 摘要写入 `summaries/<date>.json`（`{url: summary}` 映射）并提交仓库
3. 构建时 `summary_lib.py` 直接读取 JSON 复用，**无需任何 API Key**

> 摘要逻辑集中在 `summary_lib.py`（标准库实现，零第三方依赖），由 `build_rss.py` / `build_dashboard.py` 共用。部分原文为 JS 渲染 / 付费墙导致正文无法提取时，对应摘要显示「暂无法生成概括」。

## 发布到 GitHub Pages

1. 在 GitHub 新建仓库（建议命名为 `<user>.github.io`，即用户站点；任意名称亦可）。
2. 在本目录初始化并提交：
   ```bash
   git init -b main
   git add .
   git commit -m "Initial news site"
   ```
3. 关联远程并推送（替换 `<user>` 与 `<repo>`）：
   ```bash
   git remote add origin git@github.com:<user>/<repo>.git
   git push -u origin main
   ```
4. 仓库 **Settings → Pages → Build and deployment → Source** 选择
   **GitHub Actions**。推送后 Actions 会自动部署，约 1 分钟生效。
5. 自定义域名：设环境变量 `CUSTOM_DOMAIN` 后运行 `build_archive.py`，脚本会写入根目录 `CNAME`
   并让 `sitemap.xml` / `robots.txt` 使用新域名（例：`CUSTOM_DOMAIN=news.example.com python build_archive.py`）；
   不设则按 GitHub 项目页 `https://smbu-ts.github.io/news/`（链接前缀 `/news/`）构建，且不生成 CNAME。之后提交推送。
   并在域名 DNS 处：
   - 子域名（`news.example.com`）：添加 CNAME 记录指向 `<user>.github.io`
   - 顶级域名（`example.com`）：添加 A 记录指向 GitHub Pages IP
     `185.199.108.153 / 185.199.109.153 / 185.199.110.153 / 185.199.111.153`
   之后在 Settings → Pages 勾选 **Enforce HTTPS**（DNS 生效后可用）。

## SEO 说明

- 每页含 `<title>`、`<meta name="description">`、规范链接 `canonical`、
  Open Graph、Twitter Card 与 JSON-LD 结构化数据。
- `sitemap.xml` 列出所有页面与新闻原文的绝对地址（取自 `CNAME` 域名）。
- `robots.txt` 允许全部抓取并指向 `sitemap.xml`。

> 若日后页面增多、需要更强的模板能力，可平滑迁移到 Jekyll（ layouts/includes）
> 或静态站点生成器；当前纯静态方案零构建依赖，最易于长期维护。
