#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a date-based, multi-page news site for GitHub Pages.

Produces (all links are root-relative, served at the site root):
    index.html       首页：按日期倒序的导航入口
    archive.html     归档页：跨日期、按分类汇总全部新闻
    2026-MM-DD/index.html   当日汇总页：可点击新闻链接
    sitemap.xml / robots.txt  SEO 基础
    2026-MM-DD/<cat>/...html 新闻原文（分类子文件夹）

Run:  python build_archive.py
Re-run any time news files are added; it regenerates everything from the
folder layout. It never deletes news files.
"""
import os
import re
import json
import html
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- 发布模式配置 ----
# 设置环境变量 CUSTOM_DOMAIN（如 news.example.com）即走自定义域名（站点在根 /）；
# 留空则使用 GitHub 项目页地址 https://smbu-ts.github.io/news/（链接前缀 /news/）。
CUSTOM_DOMAIN = os.environ.get("CUSTOM_DOMAIN", "").strip()
if CUSTOM_DOMAIN:
    _dom = CUSTOM_DOMAIN.replace("https://", "").replace("http://", "").strip().rstrip("/")
    BASE_PATH = "/"            # 自定义域名下站点在根路径
    SITE_URL = "https://" + _dom
    CNAME_CONTENT = _dom
else:
    BASE_PATH = "/news/"      # GitHub 项目页子路径
    SITE_URL = "https://smbu-ts.github.io/news"
    CNAME_CONTENT = ""        # 不使用自定义域名（保留 github.io 默认地址）

def bp(url):
    """给站内根相对链接加发布前缀（/news/ 或 /）。"""
    if not url.startswith("/"):
        return url
    if BASE_PATH == "/":
        return url
    return BASE_PATH.rstrip("/") + url

ASSET_CSS = bp("/assets/css/style.css")
ASSET_JS = bp("/assets/js/main.js")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NEWS_RE = re.compile(r"^(?P<cat>.+?)-(?P<date>\d{4}-\d{2}-\d{2})\.html$")

# 已知分类的友好名称与配色（未知分类回退为标题化名称）。
CATEGORY_LABELS = {
    "ai-daily": "AI 日报",
    "hotsearch": "每日热搜",
    "tech": "科技",
    "finance": "财经",
    "world": "国际",
    "sports": "体育",
    "health": "健康",
    "culture": "文娱",
}
CAT_COLORS = {
    "ai-daily": "#6366f1",
    "hotsearch": "#f43f5e",
    "tech": "#3b82f6",
    "finance": "#10b981",
    "world": "#f59e0b",
    "sports": "#ef4444",
    "health": "#14b8a6",
    "culture": "#ec4899",
}
CAT_ICONS = {
    "ai-daily": "🤖",
    "hotsearch": "🔥",
    "tech": "💻",
    "finance": "📈",
    "world": "🌍",
    "sports": "⚽",
    "health": "🩺",
    "culture": "🎬",
}

# 分类展示优先级（越小越靠前）：AI 日报、每日热搜置顶，其余按名称
CAT_ORDER = {"ai-daily": 0, "hotsearch": 1}


def cat_sort_key(key):
    return (CAT_ORDER.get(key, 99), key)


def cat_label(key):
    return CATEGORY_LABELS.get(key, key.replace("-", " ").title())


def cat_color(key):
    return CAT_COLORS.get(key, "#64748b")


def cat_icon(key):
    return CAT_ICONS.get(key, "📰")


def site_url():
    """站点绝对基址，用于 canonical / sitemap / robots。"""
    return SITE_URL


def weekday_cn(date_str):
    d = datetime.date.fromisoformat(date_str)
    return ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][d.weekday()]


def extract_meta(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return path.name, ""
    m = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    title = html.unescape(m.group(1).strip()) if m else path.name
    d = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text, re.I | re.S)
    desc = html.unescape(d.group(1).strip()) if d else ""
    if not desc:
        p = re.search(r"<p[^>]*>(.*?)</p>", text, re.I | re.S)
        if p:
            desc = re.sub(r"<[^>]+>", "", p.group(1)).strip()
    return title, desc


def scan():
    """扫描日期文件夹，返回按日期倒序的 day 字典列表。"""
    days = []
    for name in sorted(os.listdir(ROOT)):
        dpath = ROOT / name
        if not dpath.is_dir() or not DATE_RE.match(name):
            continue
        news = []
        for dp, _, fns in os.walk(dpath):
            for fn in fns:
                if fn == "index.html" or not fn.endswith(".html"):
                    continue
                full = Path(dp) / fn
                rel = full.relative_to(ROOT).as_posix()
                parent = full.parent.name
                if parent == name:
                    fm = NEWS_RE.match(fn)
                    cat = fm.group("cat") if fm else "other"
                else:
                    cat = parent
                title, desc = extract_meta(full)
                news.append({
                    "full": full, "file": rel, "name": fn,
                    "cat": cat, "title": title, "desc": desc,
                })
        if not news:
            continue
        news.sort(key=lambda n: (n["cat"], n["title"]))
        days.append({"date": name, "weekday": weekday_cn(name), "news": news})
    days.sort(key=lambda x: x["date"], reverse=True)
    return days


# ---------------- SEO / 外壳 ----------------
def seo_head(title, description, canonical, json_ld=None):
    t = html.escape(title)
    d = html.escape(description)
    ld = (f'\n<script type="application/ld+json">{json.dumps(json_ld, ensure_ascii=False)}</script>'
          if json_ld else "")
    return f'''<meta name="description" content="{d}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="每日新闻">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">{ld}
<noscript><style>.reveal{{opacity:1!important;transform:none!important}}</style></noscript>'''


NAV = [("首页", bp("/"), "home"), ("归档", bp("/archive.html"), "archive"), ("关于", bp("/about.html"), "about")]


def site_header(active=""):
    links = "".join(
        f'<a href="{u}"{" class=\"active\"" if k == active else ""}>{t}</a>'
        for t, u, k in NAV
    )
    return (f'<header class="site-head"><div class="site-head-inner">'
            f'<a class="brand" href="{bp("/")}"><span class="logo">📰</span>'
            f'<span class="brand-text">每日新闻</span></a>'
            f'<nav class="site-nav">{links}</nav></div></header>')


def site_footer():
    year = datetime.date.today().year
    return f'''<footer class="site-foot"><div class="site-foot-inner">
<div class="foot-brand">📰 每日新闻</div>
<p>基于 GitHub Pages 的静态新闻档案 · 按日期归档 · 自动部署</p>
<nav><a href="{bp('/')}">首页</a>·<a href="{bp('/archive.html')}">归档</a>·<a href="{bp('/about.html')}">关于</a></nav>
<p style="margin-top:10px;opacity:.7">© {year} 每日新闻</p>
</div></footer>'''


def scripts():
    return f'<script src="{ASSET_JS}" defer></script>'


def shell(title, description, canonical, body, active="", json_ld=None):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{seo_head(title, description, canonical, json_ld)}
<link rel="stylesheet" href="{ASSET_CSS}">
{scripts()}
</head>
<body>
{site_header(active)}
<main class="page">{body}</main>
{site_footer()}
</body></html>'''


# ---------------- 页面渲染 ----------------
def _day_cats(d):
    cats = {}
    for n in d["news"]:
        cats[n["cat"]] = cats.get(n["cat"], 0) + 1
    return dict(sorted(cats.items(), key=lambda kv: cat_sort_key(kv[0])))


def render_home(days, base):
    total = sum(len(d["news"]) for d in days)
    all_cats = set(n["cat"] for d in days for n in d["news"])

    # 最新一期 Featured 横幅
    latest = days[0]
    lcats = _day_cats(latest)
    fpills = "".join(
        f'<span class="pill on-dark"><i></i>{cat_icon(c)} {html.escape(cat_label(c))} · {cnt}</span>'
        for c, cnt in lcats.items()
    )
    featured = f'''
    <a class="featured reveal" href="{bp('/' + latest['date'] + '/')}">
      <span class="tag">✦ 最新一期</span>
      <h3>{latest['date']} · {latest['weekday']}</h3>
      <p>共 {len(latest['news'])} 篇报道，覆盖 {len(lcats)} 个分类</p>
      <span class="go">进入当日汇总 →</span>
      <div class="fpills">{fpills}</div>
    </a>'''

    # 日期卡片
    cards = ""
    for d in days:
        date = d["date"]
        cats = _day_cats(d)
        chips = "".join(
            f'<span class="pill" style="--c:{cat_color(c)}">'
            f'<i></i>{cat_icon(c)} {html.escape(cat_label(c))} · {cnt}</span>'
            for c, cnt in cats.items()
        )
        cards += f'''
    <a class="day-card reveal" href="{bp('/' + date + '/')}">
      <div class="day-top">
        <div class="day-date">{date}</div>
        <span class="day-badge">{d['weekday']}</span>
      </div>
      <div class="day-count">📰 {len(d['news'])} 篇 · {len(cats)} 个分类</div>
      <div class="day-pills">{chips}</div>
      <div class="day-go">查看当日汇总 →</div>
    </a>'''

    # 注意：Hero 必须是 <body> 直接子元素（全宽），不能包进 <main class="page">，
    # 否则 Hero 渐变会被 1120px 容器截断、左右留白，出现布局偏移/样式错乱。
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">✦ 每日新闻档案</div>
      <h1>每日新闻，一处尽览</h1>
      <div class="sub">按日期归档，最新在前。点击任意日期，即可查看当天全部新闻的分类汇总。</div>
      <div class="stats">
        <div class="stat"><div class="ico">🗓️</div><div><div class="n">{len(days)}</div><div class="l">归档天数</div></div></div>
        <div class="stat"><div class="ico">📰</div><div><div class="n">{total}</div><div class="l">新闻总数</div></div></div>
        <div class="stat"><div class="ico">🏷️</div><div><div class="n">{len(all_cats)}</div><div class="l">新闻分类</div></div></div>
      </div>
    </div></section>
    <main class="page">
    {featured}
    <div class="sec-head"><h2>按日期浏览</h2><span class="sec-sub">时间倒序 · 最新在最前</span></div>
    <div class="grid">{cards}
    </div>
    </main>'''
    ld = {"@context": "https://schema.org", "@type": "WebSite",
          "name": "每日新闻", "url": base + "/"}
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日新闻档案</title>
{seo_head("每日新闻档案", "按日期归档的每日新闻汇总，最新日期在最前，点击日期查看当日全部新闻。", base + "/", json_ld=ld)}
<link rel="stylesheet" href="{ASSET_CSS}">
{scripts()}
</head>
<body>
{site_header(active="home")}
{body}
{site_footer()}
</body></html>'''


def render_day(day, base):
    date = day["date"]
    groups = {}
    for n in day["news"]:
        groups.setdefault(n["cat"], []).append(n)
    sections = ""
    for cat in sorted(groups, key=cat_sort_key):
        color = cat_color(cat)
        items = ""
        for n in groups[cat]:
            rel_day = n["full"].relative_to(ROOT / date).as_posix()
            desc = html.escape(n["desc"]) if n["desc"] else "点击查看完整报道"
            items += f'''
        <article class="news-card reveal" style="--c:{color}">
          <div class="news-cat" style="--c:{color}">{cat_icon(cat)} {html.escape(cat_label(cat))}</div>
          <h3 class="news-title"><a href="{rel_day}" target="_blank" rel="noopener noreferrer">{html.escape(n['title'])}</a></h3>
          <p class="news-desc">{desc}</p>
          <a class="news-link" href="{rel_day}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
        </article>'''
        sections += f'''
    <section class="cat-section">
      <h2 class="cat-title" style="--c:{color}">
        <span class="cat-ico" style="--c:{color}">{cat_icon(cat)}</span>{html.escape(cat_label(cat))}
        <span class="cat-count">{len(groups[cat])} 篇</span>
      </h2>
      <div class="grid">{items}
      </div>
    </section>'''
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">✦ 当日汇总</div>
      <h1>{date} · {day['weekday']}</h1>
      <div class="sub">共 {len(day['news'])} 篇报道 · {len(groups)} 个分类</div>
      <div class="back"><a href="{bp('/')}">← 返回新闻主页</a></div>
    </div></section>
    <div class="page">{sections}
    </div>'''
    # 当日页外壳（hero 已在 body 内，用轻量外壳避免重复页头）
    page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日新闻 · {date}</title>
{seo_head("每日新闻 · " + date, f"{date} 当日新闻汇总，共 {len(day['news'])} 篇报道、{len(groups)} 个分类。", base + "/" + date + "/", json_ld=day_ld(day, base))}
<link rel="stylesheet" href="{ASSET_CSS}">
{scripts()}
</head>
<body>
{site_header(active="")}
{body}
{site_footer()}
</body></html>'''
    return page


def day_ld(day, base):
    items = [{
        "@type": "NewsArticle",
        "headline": n["title"],
        "url": base + "/" + n["file"],
        "datePublished": day["date"],
    } for n in day["news"]]
    return {
        "@context": "https://schema.org", "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": it}
            for i, it in enumerate(items)
        ],
    }


def render_archive(days, base):
    # 按分类聚合全部新闻（跨日期）
    by_cat = {}
    for d in days:
        for n in d["news"]:
            by_cat.setdefault(n["cat"], []).append((d["date"], n))
    sections = ""
    all_items = []
    for cat in sorted(by_cat, key=cat_sort_key):
        color = cat_color(cat)
        items = ""
        entries = sorted(by_cat[cat], key=lambda x: x[0], reverse=True)
        for date, n in entries:
            link = bp("/" + n["file"])
            desc = html.escape(n["desc"]) if n["desc"] else "点击查看完整报道"
            items += f'''
        <article class="news-card reveal" style="--c:{color}">
          <div class="news-cat" style="--c:{color}">{cat_icon(cat)} {html.escape(cat_label(cat))}</div>
          <h3 class="news-title"><a href="{link}" target="_blank" rel="noopener noreferrer">{html.escape(n['title'])}</a></h3>
          <p class="news-desc">{desc}</p>
          <div class="news-meta">🗓️ {date}<span class="sep">·</span>{html.escape(n['name'])}</div>
        </article>'''
            all_items.append({"@type": "NewsArticle", "headline": n["title"], "url": base + "/" + n["file"]})
        sections += f'''
    <section class="cat-section">
      <h2 class="cat-title" style="--c:{color}">
        <span class="cat-ico" style="--c:{color}">{cat_icon(cat)}</span>{html.escape(cat_label(cat))}
        <span class="cat-count">{len(entries)} 篇</span>
      </h2>
      <div class="grid">{items}
      </div>
    </section>'''
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">✦ 全站归档</div>
      <h1>新闻归档</h1>
      <div class="sub">跨日期、按分类汇总全部 {sum(len(v) for v in by_cat.values())} 篇报道</div>
    </div></section>
    <div class="page">{sections}
    </div>'''
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "每日新闻归档", "url": base + "/archive.html"}
    page = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>归档 · 每日新闻</title>
{seo_head("新闻归档 · 每日新闻", "跨日期、按分类汇总每日新闻的全部报道。", base + "/archive.html", json_ld=ld)}
<link rel="stylesheet" href="{ASSET_CSS}">
{scripts()}
</head>
<body>
{site_header(active="archive")}
{body}
{site_footer()}
</body></html>'''
    return page


def render_about(base):
    body = f'''<section class="hero"><div class="hero-inner">
      <div class="kicker">✦ 关于本站</div>
      <h1>为长期维护而生的新闻档案</h1>
      <div class="sub">纯静态、零构建依赖、按日期归档，配合 GitHub Pages 实现自动部署与自定义域名。</div>
    </div></section>
    <main class="page">
      <section class="prose">
        <h2>技术特性</h2>
        <div class="feature-grid">
          <div class="feature-item reveal"><div class="fi-ico">🧭</div><h3>多页导航</h3><p>首页、归档页、关于页与每日汇总页通过统一顶部导航互联。</p></div>
          <div class="feature-item reveal"><div class="fi-ico">🚀</div><h3>自动部署</h3><p>每次向 <code>main</code> 分支提交，GitHub Actions 自动构建并发布。</p></div>
          <div class="feature-item reveal"><div class="fi-ico">🌐</div><h3>自定义域名</h3><p>根目录 <code>CNAME</code> 文件 + DNS 配置即可绑定自有域名并启用 HTTPS。</p></div>
          <div class="feature-item reveal"><div class="fi-ico">🔍</div><h3>SEO 基础</h3><p>每页含 canonical、Open Graph、Twitter Card 与 JSON-LD，并附 sitemap 与 robots。</p></div>
        </div>
        <h2>如何新增一天的新闻</h2>
        <ol>
          <li>用 <code>build_dashboard.py</code> 生成当日报文，例如 <code>ai-daily-2026-07-20.html</code>。</li>
          <li>将其放入 <code>YYYY-MM-DD/&lt;分类&gt;/</code> 目录，例如 <code>2026-07-20/ai-daily/</code>。</li>
          <li>运行 <code>build_archive.py</code> 重建首页、归档页、当日汇总页与站点地图。</li>
          <li>提交并推送，站点会自动更新。</li>
        </ol>
        <h2>目录结构</h2>
        <ul>
          <li><code>index.html</code> — 首页，按日期倒序导航</li>
          <li><code>archive.html</code> — 归档页，跨日期按分类汇总</li>
          <li><code>YYYY-MM-DD/index.html</code> — 当日汇总页</li>
          <li><code>YYYY-MM-DD/&lt;分类&gt;/*.html</code> — 新闻原文</li>
          <li><code>assets/</code> — 共享样式与脚本</li>
        </ul>
      </section>
    </main>'''
    ld = {"@context": "https://schema.org", "@type": "AboutPage",
          "name": "关于每日新闻", "url": base + "/about.html"}
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关于 · 每日新闻</title>
{seo_head("关于 · 每日新闻", "基于 GitHub Pages 的静态新闻档案，按日期归档，支持自定义域名与自动部署。", base + "/about.html", json_ld=ld)}
<link rel="stylesheet" href="{ASSET_CSS}">
{scripts()}
</head>
<body>
{site_header(active="about")}
{body}
{site_footer()}
</body></html>'''


def render_sitemap(days, base):
    urls = [("/")] + [("/archive.html"), ("/about.html")]
    for d in days:
        urls.append("/" + d["date"] + "/")
        for n in d["news"]:
            urls.append("/" + n["file"])
    today = datetime.date.today().isoformat()
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    prio = {"/": "1.0", "/archive.html": "0.6", "/about.html": "0.5"}
    for u in urls:
        p = prio.get(u, "0.8" if u.rstrip("/").count("/") == 1 else "0.6")
        body.append(f"  <url><loc>{base}{u}</loc><lastmod>{today}</lastmod>"
                    f"<changefreq>daily</changefreq><priority>{p}</priority></url>")
    body.append("</urlset>")
    return "\n".join(body)


def render_robots(base):
    return f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"


def main():
    days = scan()
    if not days:
        print("未找到日期新闻文件夹（期望如 2026-07-20/）。")
        return
    base = site_url()

    # 当日汇总页
    for day in days:
        out = ROOT / day["date"] / "index.html"
        out.write_text(render_day(day, base), encoding="utf-8")
        print(f"WROTE {out}  ({len(day['news'])} news, {day['date']})")

    # 首页 / 归档页 / 关于页
    (ROOT / "index.html").write_text(render_home(days, base), encoding="utf-8")
    print("WROTE index.html")
    (ROOT / "archive.html").write_text(render_archive(days, base), encoding="utf-8")
    print("WROTE archive.html")
    (ROOT / "about.html").write_text(render_about(base), encoding="utf-8")
    print("WROTE about.html")

    # SEO 文件
    (ROOT / "sitemap.xml").write_text(render_sitemap(days, base), encoding="utf-8")
    print("WROTE sitemap.xml")
    (ROOT / "robots.txt").write_text(render_robots(base), encoding="utf-8")
    print("WROTE robots.txt")

    # CNAME：自定义域名时写入，否则删除占位文件
    cname_path = ROOT / "CNAME"
    if CNAME_CONTENT:
        cname_path.write_text(CNAME_CONTENT + "\n", encoding="utf-8")
        print("WROTE CNAME ->", CNAME_CONTENT)
    elif cname_path.exists():
        cname_path.unlink()
        print("REMOVED CNAME (using github.io default)")

    print("SITE_URL =", base, "| BASE_PATH =", BASE_PATH)
    print("DONE")


if __name__ == "__main__":
    main()
