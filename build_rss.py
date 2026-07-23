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
    "daily20": "#8b5cf6",
}
CAT_LABELS = {
    "tech": "科技", "finance": "财经", "world": "国际", "ai-daily": "AI 日报",
    "sports": "体育", "health": "健康", "culture": "文娱", "daily20": "每日20条",
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
            result = {}
            for k, v in data.items():
                if isinstance(v, list):
                    result[k] = v
                elif isinstance(v, dict) and k == "_ranking":
                    result[k] = v
            return result
    except ImportError:
        pass
    return _mini_parse(text)


def _mini_parse(text):
    """极简 feeds.yaml 解析器，支持列表分类和 _ranking 嵌套字典。"""
    cfg = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        # 顶层键（无缩进）
        if not raw[0].isspace() and ":" in line and not line.strip().startswith("-"):
            key = line.split(":", 1)[0].strip()
            if key == "_ranking":
                # 嵌套字典段落
                cfg[key], i = _mini_parse_dict(lines, i + 1)
            else:
                # 列表段落
                cfg[key], i = _mini_parse_list(lines, i + 1)
        else:
            i += 1
    return {k: v for k, v in cfg.items() if v or k == "_ranking"}


def _indent_of(raw):
    """返回行的前导空格数（tab 按 4 计）。"""
    n = 0
    for ch in raw:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def _mini_parse_list(lines, start):
    """解析列表段落（如 tech/finance/world），返回 (list, next_line_index)。"""
    result = []
    pending = None
    i = start
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        # 遇到顶层键（无缩进） -> 段落结束
        if not raw[0].isspace():
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            rest = stripped[2:].strip()
            pending = {}
            if ":" in rest:
                k, v = rest.split(":", 1)
                pending[k.strip()] = _smart_value(v)
            result.append(pending)
            i += 1
            continue
        if ":" in line and pending is not None:
            k, v = line.split(":", 1)
            pending[k.strip()] = _smart_value(v)
        i += 1
    return result, i


def _mini_parse_dict(lines, start, base_indent=None):
    """解析嵌套字典段落（如 _ranking），返回 (dict, next_line_index)。"""
    if base_indent is None:
        # 确定首行缩进
        for j in range(start, len(lines)):
            raw = lines[j]
            if raw.strip() and not raw.strip().startswith("#"):
                base_indent = _indent_of(raw)
                break
        if base_indent is None:
            return {}, len(lines)

    result = {}
    i = start
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        indent = _indent_of(raw)
        if indent < base_indent:
            break  # 回到更高层级 -> 段落结束

        stripped = line.strip()
        if ":" not in stripped:
            i += 1
            continue

        key, val = stripped.split(":", 1)
        key = key.strip()
        val = val.strip()

        if val:
            # 标量值
            result[key] = _smart_value(val)
            i += 1
        else:
            # 嵌套字典或空值
            # 检查下一行是否缩进更深
            if i + 1 < len(lines):
                next_indent = _indent_of(lines[i + 1])
                if next_indent > indent and lines[i + 1].strip() and not lines[i + 1].strip().startswith("#"):
                    sub_dict, i = _mini_parse_dict(lines, i + 1, next_indent)
                    result[key] = sub_dict
                    continue
            result[key] = None
            i += 1

    return result, i


def _smart_value(v):
    """智能值解析：支持字符串、数字、布尔值和 null/None。"""
    v = v.strip().strip('"').strip("'")
    if v.lower() in ("true",):
        return True
    if v.lower() in ("false",):
        return False
    if v.lower() in ("null", "none", ""):
        return None
    try:
        if "." in v or "e" in v.lower():
            return float(v)
        return int(v)
    except ValueError:
        pass
    return v


def _parse_paused(raw):
    """解析 paused_categories（兼容 PyYAML 列表与内置 mini 解析器）。

    支持两种写法：
      paused_categories:            # PyYAML -> 列表
        - tech
        - finance
      paused_categories:            # mini 解析器 -> 逐项是 {"tech": None}
        - tech:
        - finance:
    返回需要跳过的分类名集合。
    """
    paused = set()
    if not raw:
        return paused
    if isinstance(raw, str):
        paused.update(x.strip() for x in raw.split(",") if x.strip())
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                paused.add(item.strip())
            elif isinstance(item, dict):
                for k in item.keys():
                    if k:
                        paused.add(k.strip())
    return paused


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
  .summary-btn {{ font-family:inherit; line-height:inherit; background:transparent; cursor:pointer; margin:0; appearance:none; -webkit-appearance:none; }}
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


def _ensure_diversity(top, all_articles, scores, max_total):
    """确保来源多样性：每个有文章的源至少出现 1 条。

    策略:
      1. 统计 top 中各来源的文章数
      2. 找出未出现的来源
      3. 从全量文章中为每个缺失来源取分数最高的 1 条
      4. 替换 top 中分数最低的等量文章（保持总数不变）

    参数:
      top:           排名后的文章列表
      all_articles:  全量去重文章列表
      scores:        对应 all_articles 的评分
      max_total:     最大保留条数

    返回:
      调整后的文章列表
    """
    if not top or not all_articles:
        return top

    # 统计 top 中的来源
    top_sources = set()
    for art in top:
        top_sources.add(art.get("source", ""))

    # 找出全量中有但 top 中没有的来源
    all_sources = set()
    for art in all_articles:
        all_sources.add(art.get("source", ""))

    missing_sources = all_sources - top_sources
    if not missing_sources:
        return top  # 所有来源都已覆盖

    # 为每个缺失来源找分数最高的文章
    paired = list(zip(scores, all_articles))
    to_add = []
    for src in missing_sources:
        best = None
        best_score = -1
        for score, art in paired:
            if art.get("source", "") == src and art not in top and art not in to_add:
                if score > best_score:
                    best_score = score
                    best = art
        if best:
            to_add.append(best)

    if not to_add:
        return top

    # 替换 top 中分数最低的等量文章
    # 按 top 在原 scores 中的分数排序，移除最低的
    top_with_scores = []
    for art in top:
        for score, all_art in paired:
            if all_art is art:
                top_with_scores.append((score, art))
                break
    top_with_scores.sort(key=lambda x: x[0])

    # 移除最低的 len(to_add) 条，加入新来源的文章
    keep_count = len(top) - len(to_add)
    if keep_count < len(top) // 2:
        # 不移除超过一半
        keep_count = len(top) // 2
        to_add = to_add[:len(top) - keep_count]

    result = [art for _, art in top_with_scores[-keep_count:]] + to_add
    return result


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    # 载入预生成摘要（url -> 摘要，见 summaries/<date>.json）。
    # 这样即使未配置 DeepSeek API Key，本机重跑构建也能复用真实摘要、不丢失。
    load_precomputed(ROOT / "summaries" / f"{date}.json")
    cfg = load_config()
    if not cfg:
        return

    # 提取 _ranking 配置（不影响现有分类遍历）
    ranking_raw = cfg.pop("_ranking", None)

    # 提取暂停的分类（paused_categories）：构建时跳过，不抓取/不生成/不展示
    paused = _parse_paused(cfg.pop("paused_categories", None))
    if paused:
        print(f"暂停的分类（不生成）：{', '.join(sorted(paused))}")

    # 按需导入排名模块
    ranking_mod = None
    engagement_mod = None
    if ranking_raw:
        try:
            import ranking as ranking_mod
            import engagement as engagement_mod
        except ImportError as e:
            print(f"  [排名系统] 模块导入失败，回退到按时间排序: {e}")
            ranking_raw = None

    for cat, feeds in cfg.items():
        if cat in paused:
            print(f"  [暂停] 跳过分类 {cat}（paused_categories）")
            continue
        collected = []
        for f in feeds:
            name = f.get("name", "?")
            url = f.get("url")
            if not url:
                continue
            try:
                data = fetch(url)
                items = parse_feed(data, name)
                # 应用单源最大条目数限制
                max_art = f.get("max_articles")
                if max_art and isinstance(max_art, int) and len(items) > max_art:
                    items = items[:max_art]
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

        # ====== 热度排名管线 ======
        if ranking_mod and ranking_raw:
            ranking_config = ranking_mod.resolve_ranking_config(cat, ranking_raw)
        else:
            ranking_config = None

        if ranking_config:
            try:
                # 获取互动数据
                now = datetime.datetime.now(datetime.timezone.utc)
                engagement_map = {}
                if engagement_mod:
                    poll_timeout = ranking_config.get("engagement_poll_timeout", 15)
                    for f in feeds:
                        eng = f.get("engagement", "none")
                        if eng != "none" and eng in engagement_mod.ENGAGEMENT_FETCHERS:
                            try:
                                partial = engagement_mod.fetch_for_source(eng, timeout=poll_timeout)
                                engagement_map.update(partial)
                                if partial:
                                    print(f"  [互动] {cat}/{f.get('name', '?')}: 获取 {len(partial)} 条")
                            except Exception as e:
                                print(f"  [互动跳过] {cat}/{f.get('name', '?')}: {e}")

                # 构建来源权重映射
                source_weights = {f.get("name"): f.get("weight", 1.0) for f in feeds if f.get("name")}

                # 计算评分
                scores = ranking_mod.score_articles(uniq, engagement_map, ranking_config, source_weights, now)

                # 应用排名筛选
                top = ranking_mod.apply_ranking(uniq, scores, ranking_config)
                
                # 来源多样性保障：确保每个有文章的源至少出现 1-2 条
                top = _ensure_diversity(top, uniq, scores, ranking_config.get("top_n", 20))
                
                print(f"  {cat}: 排名后保留 {len(top)}/{len(uniq)} 条")

                # 如果排名结果太少，回退补充
                if len(top) < 5 and len(uniq) > len(top):
                    fallback = [it for it in uniq if it not in top][:5 - len(top)]
                    top.extend(fallback)
                    print(f"  {cat}: 补充 {len(fallback)} 条至最低5条")

            except Exception as e:
                print(f"  [排名异常] {cat}: {e}，回退到按时间排序")
                uniq.sort(key=_sortkey, reverse=True)
                top = uniq[:MAX_PER_CAT]
        else:
            # 无排名配置 -> 旧行为
            uniq.sort(key=_sortkey, reverse=True)
            top = uniq[:MAX_PER_CAT]

        out_dir = ROOT / date / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{cat}-{date}.html"
        out.write_text(render_html(cat, date, top), encoding="utf-8")
        print(f"WROTE {out}  ({len(top)}/{len(uniq)} unique, {cat})")


if __name__ == "__main__":
    main()
