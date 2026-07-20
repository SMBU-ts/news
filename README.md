# 每日新闻 · GitHub Pages 静态站点

一个基于 **GitHub Pages** 的多页静态新闻档案站点：按日期归档、页面间统一导航、支持自定义域名、每次提交自动部署，并具备 SEO 基础结构。

## 目录结构

```
.
├── .github/workflows/deploy.yml   # GitHub Actions：推送即自动部署
├── .nojekyll                      # 禁用 Jekyll，保留原始目录结构
├── CNAME                          # 自定义域名（替换为你的域名）
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
├── build_dashboard.py             # 生成单日新闻报文（数据源）
└── build_archive.py               # 生成首页/归档/汇总/sitemap（站点构建器）
```

## 本地构建

```bash
python build_archive.py     # 重新生成 index.html / archive.html / 各日 index.html / sitemap.xml / robots.txt
```

> 链接使用相对于站点根的路径（首页 `/`、当日 `/2026-07-20/`），因此站点既可作为用户站点
> （`<user>.github.io`）部署，也可配合自定义域名部署在根路径下。

## 新增一天的新闻

1. 运行 `build_dashboard.py` 生成当日报文（如 `ai-daily-2026-07-20.html`）。
2. 放入 `YYYY-MM-DD/<分类>/` 目录（分类即子文件夹名，如 `ai-daily`）。
3. 运行 `build_archive.py` 重建全部页面与站点地图。
4. 提交并推送。

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
5. 自定义域名：编辑根目录 `CNAME` 为你的域名（如 `news.example.com`），重新运行
   `build_archive.py` 让 `sitemap.xml` / `robots.txt` 使用新域名，然后提交推送。
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
