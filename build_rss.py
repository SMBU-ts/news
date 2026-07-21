#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate category news pages from RSS/Atom feeds defined in feeds.yaml.

For every category listed in ``feeds.yaml`` this script:
  1. fetches each feed (RSS 2.0 or Atom) with a browser User-Agent,
  2. parses out title / link / summary / published date,
  3. de-duplicates and keeps the latest ``MAX_PER_CAT`` items,
  4. writes ``YYYY-MM-DD/<cat>/<cat>-YYYY-MM-DD.html`` using the same
     visual language as the AI daily report.

``build_archive.py`` then scans these folders automatically, so no change
to the archive builder is required for new categories to appear on the
site.  Zero third-party dependencies (stdlib only); if PyYAML happens to
be installed it is used, otherwise a small built-in parser reads the simple
``feeds.yaml`` format.
"""
import os
import re
import sys
import html
import gzip
import email.utils
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

from summary_lib import summarize, SUMMARY_FAIL, load_precomputed

ROOT = Path(__file__).resolve().parent

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Accent colours must match build_archive.py CAT_COLORS so a category looks
# the same on the daily-report page, the day-summary page and the archive.
CAT_COLORS = {
    "tech": "#3b82f6",
    "finance": "#10b981",
    "world": "#f59e0b",
    "ai-daily": "#6366f1",
    "sports": "#ef4444",
    "health": "#14b8a6",
    "culture": "#ec4899",
}
CAT_LABELS = {
    "tech": "科技", "finance": "财经", "world": "国际", "ai-daily": "AI 日报",
    "sports": "体育", "health": "健康", "culture": "文娱",
}

MAX_PER_CAT = 20      # 每个分类保留的最新条目数
TIMEOUT = 25          # 单源抓取超时（秒）


# ---------------- 时间 ----------------
def beijing_human(dt):
    """Datetime -> 北京时间字符串（YYYY-MM-DD HH:MM）。"""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    bj = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    return bj.strftime("%Y-%m-%d %H:%M")


def _sortkey(it):
    d = it["dt"]
    if d is None:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return d


# ---------------- 配置解析 ----------------
def load_config():
    p = ROOT / "feeds.yaml"
    if not p.exists():
        print("未找到 feeds.yaml，请先参考 README 创建（或运行 build_rss.py 前确认配置存在）。")
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, list)}
    except ImportError:
        pass
    return _mini_parse(text)


def _mini_parse(text):
    """极简 feeds.yaml 解析器，仅支持本项目使用的简单结构。"""
    cfg, cur, pending = {}, None, None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if (not raw.startswith(" ")) and (not raw.startswith("\t")) and ":" in line and not line.strip().startswith("-"):
            cur = line.split(":", 1)[0].strip()
            cfg[cur] = []
            pending = None
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            rest = stripped[2:].strip()
            pending = {}
            if ":" in rest:
                k, v = rest.split(":", 1)
                pending[k.strip()] = _stripq(v)
            if cur is not None:
                cfg[cur].append(pending)
            continue
        if ":" in line and pending is not None:
            k, v = line.split(":", 1)
            pending[k.strip()] = _stripq(v)
    return {k: v for k, v in cfg.items() if v}


def _stripq(v):
    return v.strip().strip('"').strip("'")


# ---------------- 抓取 ----------------
def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA,
                 "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":           # 服务器强塞了 gzip
        data = gzip.decompress(data)
    return data


# ---------------- 解析 ----------------
def _ln(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text(el, name):
    for c in el:
        if _ln(c.tag) == name and c.text and c.text.strip():
            return c.text.strip()
    return ""


def _link(el):
    for c in el:
        if _ln(c.tag) == "link":
            href = c.get("href")
            if href and c.get("rel") in (None, "alternate"):
                return href
    for c in el:
        if _ln(c.tag) == "link":
            if c.get("href"):
                return c.get("href")
            if c.text and c.text.strip():
                return c.text.strip()
    return _text(el, "link")


def _date(el):
    for name in ("pubDate", "updated", "published", "date"):
        t = _text(el, name)
        if not t:
            continue
        try:                                    # RFC 822 (RSS)
            dt = email.utils.parsedate_to_datetime(t)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            pass
        s = t.strip().replace("Z", "+00:00")     # ISO 8601 (Atom)
        try:
            dt = datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception:
            pass
    return None


_TAG_RE = re.compile(r"<[^>]+>")


def _clean(s, n=100):
    s = _TAG_RE.sub(" ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[: n - 1] + "…"
    return s


def parse_feed(xml_bytes, source_name):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"    [解析失败] {source_name}: {e}")
        return items
    for el in root.iter():
        if _ln(el.tag) not in ("item", "entry"):
            continue
        title = _text(el, "title")
        if not title:
            continue
        items.append({
            "title": title.strip(),
            "link": _link(el),
            "summary": _clean(_text(el, "description") or _text(el, "summary") or _text(el, "content")),
            "source": source_name,
            "dt": _date(el),
        })
    return items


# ---------------- 渲染 ----------------
def render_html(cat, date, items):
    color = CAT_COLORS.get(cat, "#64748b")
    label = CAT_LABELS.get(cat, cat)
    total = len(items)

    if total == 0:
        body = ('<div class="empty">本分类今日暂无更新——所有订阅源均未返回条目或暂时不可达。'
                '请检查 feeds.yaml 中的源地址。</div>')
    else:
        cards = ""
        for i, it in enumerate(items, 1):
            title = html.escape(it["title"])
            url = html.escape(it["link"] or "#")
            summary = html.escape(it["summary"]) or "点击查看完整报道"
            src = html.escape(it["source"])
            when = beijing_human(it["dt"])
            sum_text = summarize(it["link"], it["title"])
            cards += f'''
        <article class="card" style="--c:{color}">
          <div class="card-top">
            <span class="num" style="background:{color}">{i}</span>
            <span class="chip" style="--c:{color}">{src}</span>
          </div>
          <h3 class="card-title">
            <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
          </h3>
          <p class="card-sum">{summary}</p>
          <div class="card-meta">🕒 {when or "时间未知"}</div>
          <div class="card-actions">
            <a class="read" href="{url}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
            <button type="button" class="read summary-btn" data-target="sum-{i}" aria-expanded="false">原文概括</button>
          </div>
          <div class="summary" id="sum-{i}" hidden>{html.escape(sum_text)}</div>
        </article>'''
        body = f'<div class="grid">{cards}\n        </div>'

    date_human = f"{int(date[0:4])} 年 {int(date[5:7])} 月 {int(date[8:10])} 日"
    desc = f"{label}日报 {date} 共 {total} 条，由 RSS 订阅源聚合生成。"

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{label}日报 · {date}</title>
<meta name="description" content="{html.escape(desc)}">
<style>
  :root {{ --bg:#f6f7fb; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e7e9f0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",
      system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg);
      color:var(--ink); line-height:1.6; }}
  a {{ color:inherit; text-decoration:none; }}

  .hero {{ background:linear-gradient(135deg,{color} 0%,{color}cc 55%,#0f172a 140%);
      color:#fff; padding:46px 24px 40px; }}
  .hero-inner {{ max-width:1080px; margin:0 auto; }}
  .kicker {{ font-size:13px; letter-spacing:2px; opacity:.85; text-transform:uppercase; font-weight:600; }}
  .hero h1 {{ margin:6px 0 4px; font-size:clamp(26px,5vw,40px); font-weight:800; line-height:1.2; }}
  .hero .sub {{ opacity:.92; font-size:15px; }}
  .stat {{ display:inline-flex; gap:8px; align-items:baseline; margin-top:18px;
      background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.25);
      border-radius:12px; padding:10px 16px; }}
  .stat .n {{ font-size:26px; font-weight:800; }}
  .stat .l {{ font-size:12.5px; opacity:.9; }}

  main {{ max-width:1080px; margin:0 auto; padding:28px 16px 60px; }}
  .section-title {{ display:flex; align-items:center; gap:10px; font-size:20px;
      font-weight:800; margin:0 0 16px; padding-bottom:10px; border-bottom:2px solid var(--line); }}
  .section-title .dot {{ width:12px; height:12px; border-radius:4px; background:{color}; }}
  .section-count {{ margin-left:auto; font-size:14px; font-weight:700; color:var(--muted);
      background:#eef0f6; border-radius:999px; padding:2px 12px; }}

  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:16px;
      padding:18px; display:flex; flex-direction:column; gap:10px;
      box-shadow:0 1px 2px rgba(15,23,42,.04); border-top:3px solid var(--c);
      transition:.18s; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 10px 24px rgba(15,23,42,.10); }}
  .card-top {{ display:flex; align-items:center; gap:10px; }}
  .num {{ color:#fff; font-weight:800; font-size:14px; min-width:26px; height:26px;
      border-radius:8px; display:inline-flex; align-items:center; justify-content:center; padding:0 6px; }}
  .chip {{ font-size:12px; font-weight:600; color:var(--c);
      background:color-mix(in srgb,var(--c) 12%,#fff); border:1px solid color-mix(in srgb,var(--c) 30%,#fff);
      border-radius:999px; padding:3px 10px; overflow:hidden; text-overflow:ellipsis;
      white-space:nowrap; max-width:100%; }}
  .card-title {{ margin:0; font-size:16.5px; font-weight:700; line-height:1.4; }}
  .card-title a:hover {{ color:var(--c); text-decoration:underline; }}
  .card-sum {{ margin:0; color:var(--muted); font-size:14px; flex:1; }}
  .card-meta {{ font-size:12.5px; color:var(--muted); }}
  .read {{ align-self:flex-start; font-size:13.5px; font-weight:700; color:var(--c);
      border:1px solid color-mix(in srgb,var(--c) 35%,#fff); border-radius:10px;
      padding:6px 12px; transition:.15s; }}
  .read:hover {{ background:var(--c); color:#fff; }}
  .card-actions {{ display:flex; gap:8px; flex-wrap:wrap; align-self:flex-start; margin-top:2px; }}
  .summary-btn {{ font-family:inherit; line-height:1.2; background:transparent; cursor:pointer; margin:0; appearance:none; -webkit-appearance:none; }}
  .summary-btn:focus-visible {{ outline:2px solid var(--c); outline-offset:2px; }}
  .summary {{ margin-top:10px; padding:12px 14px; background:#f8fafc;
      border-left:3px solid var(--c); border-radius:0 10px 10px 0;
      font-size:13.5px; color:var(--ink); line-height:1.7; }}
  .empty {{ background:var(--card); border:1px dashed var(--line); border-radius:16px;
      padding:28px; text-align:center; color:var(--muted); font-size:14px; }}
  footer {{ max-width:1080px; margin:0 auto; padding:22px 16px 50px; color:var(--muted);
      font-size:13px; border-top:1px solid var(--line); text-align:center; }}
  footer a {{ color:{color}; font-weight:600; }}
  @media (max-width:560px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
  <header class="hero"><div class="hero-inner">
    <div class="kicker">{label}日报</div>
    <h1>{date_human}</h1>
    <div class="sub">共 {total} 条 · 数据来自 RSS 订阅源聚合</div>
    <div class="stat"><div class="n">{total}</div><div class="l">今日条数</div></div>
  </div></header>
  <main>
    <section class="section">
      <h2 class="section-title"><span class="dot"></span>{label} · 今日速览
        <span class="section-count">{total} 篇</span></h2>
      {body}
    </section>
  </main>
  <footer>
    本页由 RSS 订阅源自动聚合生成 · 数据来源以各卡片标注为准 · 点击「阅读原文」跳转原始报道
  </footer>
  <script>
  document.addEventListener('click', function(e){{
    var b = e.target.closest('.summary-btn'); if(!b) return;
    var el = document.getElementById(b.getAttribute('data-target')); if(!el) return;
    var open = el.hasAttribute('hidden');
    if(open){{ el.removeAttribute('hidden'); }} else {{ el.setAttribute('hidden',''); }}
    b.setAttribute('aria-expanded', String(open));
  }});
  </script>
</body></html>'''


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    # 载入预生成摘要（url -> 摘要，见 summaries/<date>.json）。
    # 这样即使未配置 DeepSeek API Key，本机重跑构建也能复用真实摘要、不丢失。
    load_precomputed(ROOT / "summaries" / f"{date}.json")
    cfg = load_config()
    if not cfg:
        return
    for cat, feeds in cfg.items():
        collected = []
        for f in feeds:
            name = f.get("name", "?")
            url = f.get("url")
            if not url:
                continue
            try:
                data = fetch(url)
                items = parse_feed(data, name)
                print(f"  {cat}/{name}: {len(items)} 条")
                collected.extend(items)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                print(f"  [跳过] {cat}/{name}: {e}")
        # 去重（优先按链接，无链接按标题）
        seen, uniq = set(), []
        for it in collected:
            key = (it["link"] or "").strip() or it["title"].strip()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        uniq.sort(key=_sortkey, reverse=True)
        top = uniq[:MAX_PER_CAT]

        out_dir = ROOT / date / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{cat}-{date}.html"
        out.write_text(render_html(cat, date, top), encoding="utf-8")
        print(f"WROTE {out}  ({len(top)}/{len(uniq)} unique, {cat})")


if __name__ == "__main__":
    main()
