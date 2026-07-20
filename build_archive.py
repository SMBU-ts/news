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
ASSET_CSS = "/assets/css/style.css"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NEWS_RE = re.compile(r"^(?P<cat>.+?)-(?P<date>\d{4}-\d{2}-\d{2})\.html$")

# 已知分类的友好名称与配色（未知分类回退为标题化名称）。
CATEGORY_LABELS = {
    "ai-daily": "AI 日报",
    "tech": "科技",
    "finance": "财经",
    "world": "国际",
    "sports": "体育",
    "health": "健康",
    "culture": "文娱",
}
CAT_COLORS = {
    "ai-daily": "#6366f1",
    "tech": "#3b82f6",
    "finance": "#10b981",
    "world": "#f59e0b",
    "sports": "#ef4444",
    "health": "#14b8a6",
    "culture": "#ec4899",
}


def cat_label(key):
    return CATEGORY_LABELS.get(key, key.replace("-", " ").title())


def cat_color(key):
    return CAT_COLORS.get(key, "#64748b")


def site_url():
    """站点绝对基址，取自 CNAME（自定义域名），缺省用占位域名。"""
    cname = ROOT / "CNAME"
    if cname.exists():
        dom = cname.read_text(encoding="utf-8").strip().splitlines()
        dom = dom[0].strip() if dom else ""
        if dom:
            return dom if dom.startswith("http") else "https://" + dom
    return "https://your-domain.example"


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
<meta name="twitter:description" content="{d}">{ld}'''


NAV = [("首页", "/", "home"), ("归档", "/archive.html", "archive"), ("关于", "/about.html", "about")]


def site_header(active=""):
    links = "".join(
        f'<a href="{u}"{" class=\"active\"" if k == active else ""}>{t}</a>'
        for t, u, k in NAV
    )
    return (f'<header class="site-head"><div class="site-head-inner">'
            f'<a class="brand" href="/">每日新闻</a>'
            f'<nav class="site-nav">{links}</nav></div></header>')


def site_footer():
    return '''<footer class="site-foot"><div class="site-foot-inner">
<p>每日新闻 · 基于 GitHub Pages 的静态新闻档案</p>
<nav><a href="/">首页</a> · <a href="/archive.html">归档</a> · <a href="/about.html">关于</a></nav>
</div></footer>'''


def shell(title, description, canonical, body, active="", json_ld=None):
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{seo_head(title, description, canonical, json_ld)}
<link rel="stylesheet" href="{ASSET_CSS}">
</head>
<body>
{site_header(active)}
<main class="page">{body}</main>
{site_footer()}
</body></html>'''


# ---------------- 页面渲染 ----------------
def render_home(days, base):
    total = sum(len(d["news"]) for d in days)
    cards = ""
    for d in days:
        date = d["date"]
        cats = {}
        for n in d["news"]:
            cats[n["cat"]] = cats.get(n["cat"], 0) + 1
        chips = "".join(
            f'<span class="pill" style="--c:{cat_color(c)}">'
            f'<i style="background:{cat_color(c)}"></i>{html.escape(cat_label(c))} · {cnt}</span>'
            for c, cnt in sorted(cats.items(), key=lambda kv: (kv[0] != "ai-daily", kv[0]))
        )
        cards += f'''
    <a class="day-card" href="/{date}/" style="--c:{cat_color('ai-daily')}">
      <div class="day-date">{date}</div>
      <div class="day-week">{d['weekday']}</div>
      <div class="day-count">{len(d['news'])} 篇 · {len(cats)} 类</div>
      <div class="day-pills">{chips}</div>
      <div class="day-go">查看当日汇总 →</div>
    </a>'''
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">每日新闻档案</div>
      <h1>每日新闻汇总</h1>
      <div class="sub">按日期归档 · 最新日期在最前 · 点击任意日期查看当日全部新闻</div>
      <div class="stats">
        <div class="stat"><div class="n">{len(days)}</div><div class="l">归档天数</div></div>
        <div class="stat"><div class="n">{total}</div><div class="l">新闻总数</div></div>
      </div>
    </div></section>
    <h2 class="sec-head">日期导航（倒序）</h2>
    <div class="grid">{cards}
    </div>'''
    ld = {"@context": "https://schema.org", "@type": "WebSite",
          "name": "每日新闻", "url": base + "/"}
    return shell("每日新闻档案", "按日期归档的每日新闻汇总，最新日期在最前，点击日期查看当日全部新闻。",
                 base + "/", body, active="home", json_ld=ld)


def render_day(day, base):
    date = day["date"]
    groups = {}
    for n in day["news"]:
        groups.setdefault(n["cat"], []).append(n)
    sections = ""
    for cat in sorted(groups, key=lambda c: (c != "ai-daily", c)):
        color = cat_color(cat)
        items = ""
        for n in groups[cat]:
            rel_day = n["full"].relative_to(ROOT / date).as_posix()
            desc = html.escape(n["desc"]) if n["desc"] else "点击查看完整报道"
            items += f'''
        <article class="news-card" style="--c:{color}">
          <div class="news-cat" style="--c:{color}">{html.escape(cat_label(cat))}</div>
          <h3 class="news-title"><a href="{rel_day}" target="_blank" rel="noopener noreferrer">{html.escape(n['title'])}</a></h3>
          <p class="news-desc">{desc}</p>
          <a class="news-link" href="{rel_day}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
        </article>'''
        sections += f'''
    <section class="cat-section">
      <h2 class="cat-title" style="--c:{color}">
        <span class="dot" style="background:{color}"></span>{html.escape(cat_label(cat))}
        <span class="cat-count">{len(groups[cat])}</span>
      </h2>
      <div class="grid">{items}
      </div>
    </section>'''
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">每日新闻 · 当日汇总</div>
      <h1>{date} · {day['weekday']}</h1>
      <div class="sub">共 {len(day['news'])} 篇报道 · {len(groups)} 个分类</div>
      <div class="back"><a href="/">← 返回新闻主页</a></div>
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
    for cat in sorted(by_cat, key=lambda c: (c != "ai-daily", c)):
        color = cat_color(cat)
        items = ""
        entries = sorted(by_cat[cat], key=lambda x: x[0], reverse=True)
        for date, n in entries:
            link = "/" + n["file"]
            desc = html.escape(n["desc"]) if n["desc"] else "点击查看完整报道"
            items += f'''
        <article class="news-card" style="--c:{color}">
          <div class="news-cat" style="--c:{color}">{html.escape(cat_label(cat))}</div>
          <h3 class="news-title"><a href="{link}" target="_blank" rel="noopener noreferrer">{html.escape(n['title'])}</a></h3>
          <p class="news-desc">{desc}</p>
          <div class="day-week">{date} · {html.escape(n['name'])}</div>
        </article>'''
            all_items.append({"@type": "NewsArticle", "headline": n["title"], "url": base + "/" + n["file"]})
        sections += f'''
    <section class="cat-section">
      <h2 class="cat-title" style="--c:{color}">
        <span class="dot" style="background:{color}"></span>{html.escape(cat_label(cat))}
        <span class="cat-count">{len(entries)}</span>
      </h2>
      <div class="grid">{items}
      </div>
    </section>'''
    body = f'''
    <section class="hero"><div class="hero-inner">
      <div class="kicker">每日新闻 · 全站归档</div>
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
</head>
<body>
{site_header(active="archive")}
{body}
{site_footer()}
</body></html>'''
    return page


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

    # 首页 / 归档页
    (ROOT / "index.html").write_text(render_home(days, base), encoding="utf-8")
    print("WROTE index.html")
    (ROOT / "archive.html").write_text(render_archive(days, base), encoding="utf-8")
    print("WROTE archive.html")

    # SEO 文件
    (ROOT / "sitemap.xml").write_text(render_sitemap(days, base), encoding="utf-8")
    print("WROTE sitemap.xml")
    (ROOT / "robots.txt").write_text(render_robots(base), encoding="utf-8")
    print("WROTE robots.txt")

    print("SITE_URL =", base)
    print("DONE")


if __name__ == "__main__":
    main()
