#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日热搜汇总：抓取国内平台实时热榜 → 每平台取 24 小时内综合排名前 10 →
按平台分栏渲染自包含卡片页面（融入现有站点的 hotsearch 分类）。

零第三方依赖（仅标准库），风格对齐 build_rss.py。

平台与端点：
  微博       https://weibo.com/ajax/side/hotSearch   （需 Referer 头）
  百度       https://top.baidu.com/board?tab=realtime （HTML 内嵌 s-data JSON）
  今日头条   https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc
  知乎       https://60s.viki.moe/v2/zhihu           （聚合兜底，直连需鉴权）
  哔哩哔哩   https://api.bilibili.com/x/web-interface/popular

配置要点（改这几项即生效，下次运行采用新值）：
  · 抓取各平台【完整热榜，不限条数】；展示时每平台仅取自身综合排名前 PER_PLATFORM_TOP=10 条；
  · 微博 / 今日头条接口无描述字段 → 方案1：对其缺摘要条目用标题调 Bing 搜索
    抓首条结果摘要，得到真实中文摘要（失败则保留兜底文案）；
  · 哔哩哔哩摘要字段刻意留空（不取视频简介 desc）。

用法：
  python build_hotsearch.py             # 今天
  python build_hotsearch.py 2026-07-21  # 指定日期
"""
import re
import sys
import json
import html
import gzip
import datetime
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 20
PER_PLATFORM_TOP = 10   # 每平台展示的条数（取该平台综合排名前 N）
SUMMARY_MAX = 50      # 摘要最大字数
ENRICH_TIMEOUT = 10   # 方案1：微博/头条二次抓取（Bing 摘要）超时秒数

CAT = "hotsearch"
BRAND = "#f43f5e"     # 版块主色（与 build_archive.py 的 CAT_COLORS["hotsearch"] 一致）

# 平台展示名 → 主题色（卡片 chip / 顶部条 / 分栏标题）
PLATFORM_COLORS = {
    "微博": "#ff8200",
    "百度": "#2932e1",
    "今日头条": "#f04142",
    "知乎": "#0084ff",
    "哔哩哔哩": "#fb7299",
}
# 分栏展示时的平台先后顺序（与配置覆盖顺序一致：百度/知乎/微博/今日头条/哔哩哔哩）
PLATFORM_ORDER = ["百度", "知乎", "微博", "今日头条", "哔哩哔哩"]


# ==================== 抓取工具 ====================
def _get(url, headers=None, timeout=TIMEOUT):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA,
                 "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                 **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def _get_json(url, headers=None):
    return json.loads(_get(url, headers).decode("utf-8", "ignore"))


_TAG_RE = re.compile(r"<[^>]+>")


def _fmt_hot(n):
    """把热度原始值格式化为友好中文（万/亿）。"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if n <= 0:
        return "—"
    if n >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return str(int(n))


def _parse_hot_text(s):
    """从「397 万热度」这类文本解析出数值。"""
    m = re.search(r"([\d.]+)\s*(亿|万)?", s or "")
    if not m:
        return 0.0
    v = float(m.group(1))
    unit = m.group(2)
    if unit == "亿":
        v *= 1e8
    elif unit == "万":
        v *= 1e4
    return v


def _clean(s, n=SUMMARY_MAX):
    s = _TAG_RE.sub("", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[: n - 1] + "…"
    return s


# ==================== 各平台抓取器 ====================
def fetch_weibo():
    d = _get_json("https://weibo.com/ajax/side/hotSearch",
                  {"Referer": "https://weibo.com/", "Accept": "application/json"})
    out = []
    for it in (d.get("data", {}) or {}).get("realtime", []):
        if it.get("is_ad") or it.get("adid"):
            continue
        word = it.get("word") or it.get("note")
        if not word:
            continue
        num = it.get("num") or it.get("raw_hot") or 0
        q = urllib.parse.quote(f"#{word}#")
        out.append({
            "title": word,
            "summary": "",
            "url": f"https://s.weibo.com/weibo?q={q}",
            "hot": float(num or 0),
            "hot_display": _fmt_hot(num),
            "source": "微博",
            "label": it.get("label_name", "") or "",
        })
    return out


def fetch_baidu():
    txt = _get("https://top.baidu.com/board?tab=realtime").decode("utf-8", "ignore")
    m = re.search(r"<!--s-data:(.*?)-->", txt, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    out = []
    for card in data.get("data", {}).get("cards", []):
        for it in card.get("content", []):
            word = it.get("word") or it.get("query")
            if not word:
                continue
            score = it.get("hotScore") or 0
            out.append({
                "title": word,
                "summary": it.get("desc") or "",
                "url": it.get("rawUrl") or it.get("url") or "",
                "hot": float(score or 0),
                "hot_display": _fmt_hot(score),
                "source": "百度",
                "label": it.get("hotTag", "") or "",
            })
    return out


def fetch_toutiao():
    d = _get_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    out = []
    for it in d.get("data", []):
        title = it.get("Title")
        if not title:
            continue
        try:
            hv = float(it.get("HotValue") or 0)
        except (TypeError, ValueError):
            hv = 0.0
        out.append({
            "title": title,
            "summary": "",
            "url": it.get("Url") or "",
            "hot": hv,
            "hot_display": _fmt_hot(hv),
            "source": "今日头条",
            "label": it.get("Label", "") or "",
        })
    return out


def fetch_zhihu():
    d = _get_json("https://60s.viki.moe/v2/zhihu")
    out = []
    for it in d.get("data", []):
        title = it.get("title")
        if not title:
            continue
        hvd = it.get("hot_value_desc") or ""
        hot = _parse_hot_text(hvd)
        out.append({
            "title": title,
            "summary": it.get("detail") or "",
            "url": it.get("link") or "",
            "hot": hot,
            "hot_display": hvd.replace("热度", "").strip() or _fmt_hot(hot),
            "source": "知乎",
            "label": "",
        })
    return out


def fetch_bilibili():
    d = _get_json("https://api.bilibili.com/x/web-interface/popular?ps=30&pn=1")
    out = []
    for it in (d.get("data", {}) or {}).get("list", []):
        title = it.get("title")
        if not title:
            continue
        view = (it.get("stat") or {}).get("view") or 0
        bvid = it.get("bvid")
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else (it.get("short_link_v2") or "")
        out.append({
            "title": title,
            "summary": "",   # 按配置：不包含视频简介（desc）字段
            "url": url,
            "hot": float(view or 0),
            "hot_display": _fmt_hot(view) + "播放",
            "source": "哔哩哔哩",
            "label": (it.get("owner") or {}).get("name", "") or "",
        })
    return out


FETCHERS = [
    ("微博", fetch_weibo),
    ("百度", fetch_baidu),
    ("今日头条", fetch_toutiao),
    ("知乎", fetch_zhihu),
    ("哔哩哔哩", fetch_bilibili),
]


# ==================== 每平台取自身综合排名前 N ====================
# 按平台分栏展示：抓取各平台【完整热榜，不限条数】后，直接取每个平台返回顺序
# （即其自身综合排名）的前 PER_PLATFORM_TOP 条，不做跨平台合并。
# 微博 / 今日头条经方案1 补真实摘要；哔哩哔哩摘要留空。

# 平台的单字/状态标签，不适合当摘要
_STATUS_LABELS = {"新", "热", "沸", "爆", "荐", "商", "hot", "new", "boom", "recommend"}


def finalize_section(items, source):
    """截断/兜底摘要，赋该平台内排名序号（1..N）。"""
    out = []
    for i, it in enumerate(items[:PER_PLATFORM_TOP], 1):
        summary = _clean(it.get("summary") or "")
        if not summary:
            label = (it.get("label") or "").strip()
            if label and label.lower() not in _STATUS_LABELS and len(label) >= 2:
                summary = _clean(f"「{label}」相关话题，正在{source}热榜引发热议，点击查看详情")
            else:
                summary = _clean(f"该话题正在{source}热榜引发广泛关注，点击查看完整内容")
        out.append({
            "rank": i,
            "title": it["title"],
            "summary": summary,
            "url": it.get("url") or "",
            "hot": it.get("hot", 0),
            "hot_display": it.get("hot_display") or "—",
            "source": source,
        })
    return out


# ==================== 方案1：微博/头条二次抓取真实摘要 ====================
# 微博、今日头条的热榜接口只返回标题 + 热度，没有描述字段。
# 方案1：对这两家、且仍缺摘要的条目，用标题调一次 Bing 搜索，
# 抓取首条结果摘要作为真实中文摘要（替代兜底文案）。抓取失败则保留兜底文案。
def _bing_snippet(query, n=SUMMARY_MAX):
    """用标题调 Bing 搜索，返回首条结果摘要（已截断/去噪）。失败返回空串。"""
    q = urllib.parse.quote(query)
    url = f"https://www.bing.com/search?q={q}&setlang=zh-CN"
    try:
        txt = _get(url, {"Accept-Language": "zh-CN,zh;q=0.9"},
                   timeout=ENRICH_TIMEOUT).decode("utf-8", "ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return ""
    m = (re.search(r'class="[^"]*b_lineclamp[0-9]*[^"]*"[^>]*>(.*?)</p>', txt, re.S)
         or re.search(r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', txt, re.S))
    if not m:
        return ""
    s = _TAG_RE.sub("", m.group(1))
    s = html.unescape(s)
    # 去掉摘要开头常见的时间/署名噪前缀（如「6 小时之前 · 作者 | 肖瑶」「1 天前 · 央视网消息」）
    s = re.sub(r'^\s*\d+\s*(秒|分钟|小时|天|周|个月)之?前\s*[·•]?\s*', "", s)
    s = re.sub(r'^\s*\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*[·•]?\s*', "", s)
    s = re.sub(r'^\s*(作者|记者)\s*[|｜:：]\s*', "", s)
    s = re.sub(r'^\s*[·•]\s*', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 相关性粗筛：数字开头等易误匹配（如「9」→「9是自然数」）。
    # 摘要须至少含标题中的 2 个非数字字符，否则视为无关结果，回退兜底。
    key_chars = set(re.sub(r"[\d\s\W_]", "", query))
    if key_chars and len(key_chars & set(s)) < 2:
        return ""
    if len(s) > n:
        s = s[: n - 1] + "…"
    return s


def enrich_scheme1(items):
    """方案1：为『微博/今日头条』来源且仍无摘要的条目补真实摘要（Bing 片段）。"""
    for it in items:
        if it["source"] in ("微博", "今日头条") and not (it.get("summary") or "").strip():
            s = _bing_snippet(it["title"])
            if s:
                it["summary"] = s
    return items


# ==================== 渲染 ====================
def _bj_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def render_html(date, sections):
    total = sum(len(s["items"]) for s in sections)
    now = _bj_now()
    win_start = now - datetime.timedelta(hours=24)
    gen_human = now.strftime("%Y-%m-%d %H:%M")
    range_human = f"{win_start.strftime('%m-%d %H:%M')} ~ {now.strftime('%m-%d %H:%M')}"
    date_human = f"{int(date[0:4])} 年 {int(date[5:7])} 月 {int(date[8:10])} 日"

    # 平台统计 chips
    plat_stats = ""
    for s in sections:
        p = s["source"]
        col = PLATFORM_COLORS.get(p, "#64748b")
        plat_stats += (f'<span class="pstat" style="--pc:{col}">'
                       f'<i></i>{html.escape(p)} · {len(s["items"])}</span>')

    if total == 0:
        body = ('<div class="empty">暂未抓取到热搜数据——可能是各平台源暂时不可达。'
                '请稍后重试或检查网络。</div>')
    else:
        gid = 0
        sections_html = ""
        for s in sections:
            p = s["source"]
            pcolor = PLATFORM_COLORS.get(p, "#64748b")
            cards = ""
            for it in s["items"]:
                gid += 1
                title = html.escape(it["title"])
                url = html.escape(it["url"] or "#")
                summary = html.escape(it["summary"])
                rank = it["rank"]
                hot_disp = html.escape(it["hot_display"])
                cards += f'''
          <article class="card" data-hot="{it['hot']}" data-rank="{rank}" data-platform="{html.escape(p)}" style="--c:{pcolor}">
            <div class="card-top">
              <span class="num">{rank}</span>
              <span class="chip">{html.escape(p)}</span>
              <span class="hot" title="热度指数">🔥 {hot_disp}</span>
            </div>
            <h3 class="card-title">
              <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
            </h3>
            <div class="card-actions">
              <a class="read" href="{url}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
              <button type="button" class="read sum-btn" data-target="hs-{gid}" aria-expanded="false">展开摘要</button>
            </div>
            <div class="summary" id="hs-{gid}" hidden>{summary}</div>
          </article>'''
            sections_html += f'''
        <section class="psec" data-platform="{html.escape(p)}" style="--c:{pcolor}">
          <div class="psec-h">
            <span class="dot"></span>{html.escape(p)} 热榜
            <span class="psec-count">TOP {len(s['items'])}</span>
          </div>
          <div class="grid">{cards}
          </div>
        </section>'''
        body = f'<div id="wrap">{sections_html}\n        </div>'

    nplat = len(sections)
    desc = (f"{date} 每日热搜汇总：分 {nplat} 个平台各取 24 小时内综合排名前 {PER_PLATFORM_TOP}，"
            f"共 {total} 条热点，含热度指数、来源与原文链接。")

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日热搜 · {date}</title>
<meta name="description" content="{html.escape(desc)}">
<style>
  :root {{ --bg:#f6f7fb; --card:#ffffff; --ink:#0f172a; --muted:#64748b;
    --line:#e7e9f0; --brand:{BRAND}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",
      system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg);
      color:var(--ink); line-height:1.6; }}
  a {{ color:inherit; text-decoration:none; }}

  .hero {{ position:relative; overflow:hidden; color:#fff; padding:48px 24px 42px;
      background:linear-gradient(125deg,#f43f5e 0%,#fb7185 45%,#f59e0b 120%); }}
  .hero::after {{ content:"🔥"; position:absolute; right:20px; top:-6px; font-size:150px;
      opacity:.14; transform:rotate(8deg); }}
  .hero-inner {{ position:relative; z-index:1; max-width:1080px; margin:0 auto; }}
  .kicker {{ display:inline-flex; align-items:center; gap:8px; font-size:12.5px;
      letter-spacing:2px; font-weight:700; text-transform:uppercase;
      background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.32);
      padding:6px 14px; border-radius:999px; }}
  .hero h1 {{ margin:14px 0 6px; font-size:clamp(26px,5vw,42px); font-weight:850; line-height:1.15; }}
  .hero .sub {{ opacity:.95; font-size:14.5px; }}
  .hero .sub b {{ font-weight:700; }}
  .pstats {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:20px; }}
  .pstat {{ display:inline-flex; align-items:center; gap:7px; font-size:13px; font-weight:600;
      background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3);
      border-radius:999px; padding:6px 13px; }}
  .pstat i {{ width:8px; height:8px; border-radius:50%; background:var(--pc); display:inline-block;
      box-shadow:0 0 0 2px rgba(255,255,255,.5); }}

  main {{ max-width:1080px; margin:0 auto; padding:24px 16px 60px; }}
  .toolbar {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:20px; }}
  .sortgroup {{ display:inline-flex; background:var(--card); border:1px solid var(--line);
      border-radius:999px; padding:3px; }}
  .sort-btn {{ font:inherit; cursor:pointer; border:0; background:transparent; color:var(--muted);
      font-size:13.5px; font-weight:700; padding:7px 15px; border-radius:999px; transition:.15s; }}
  .sort-btn.active {{ background:var(--brand); color:#fff; }}
  .expand-all {{ margin-left:auto; font:inherit; cursor:pointer; font-size:13.5px; font-weight:700;
      color:var(--brand); background:var(--card); border:1px solid color-mix(in srgb,var(--brand) 35%,#fff);
      border-radius:11px; padding:8px 15px; transition:.15s; }}
  .expand-all:hover {{ background:var(--brand); color:#fff; }}

  .psec {{ margin-bottom:28px; }}
  .psec-h {{ display:flex; align-items:center; gap:10px; font-size:17px; font-weight:800;
      color:var(--ink); margin:0 0 14px; padding-left:12px; border-left:5px solid var(--c); }}
  .psec-h .dot {{ width:10px; height:10px; border-radius:50%; background:var(--c); display:inline-block; }}
  .psec-count {{ font-size:12.5px; font-weight:700; color:var(--muted);
      background:#eef0f6; border-radius:999px; padding:2px 10px; }}
  #wrap.flat .psec {{ margin-bottom:0; }}
  #wrap.flat .psec-h {{ display:none; }}

  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }}
  .card {{ position:relative; background:var(--card); border:1px solid var(--line);
      border-radius:16px; padding:18px; display:flex; flex-direction:column; gap:11px;
      box-shadow:0 1px 2px rgba(15,23,42,.04); border-top:3px solid var(--c); transition:.18s; }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 10px 24px rgba(15,23,42,.10); }}
  .card-top {{ display:flex; align-items:center; gap:9px; flex-wrap:wrap; }}
  .num {{ color:#fff; font-weight:850; font-size:14px; min-width:26px; height:26px; border-radius:8px;
      display:inline-flex; align-items:center; justify-content:center; padding:0 6px;
      background:linear-gradient(135deg,var(--brand),#fb7185); }}
  .card:nth-child(1) .num, .card:nth-child(2) .num, .card:nth-child(3) .num {{
      background:linear-gradient(135deg,#f59e0b,#f43f5e); box-shadow:0 3px 10px rgba(244,63,94,.4); }}
  .chip {{ font-size:12px; font-weight:700; color:var(--c);
      background:color-mix(in srgb,var(--c) 12%,#fff); border:1px solid color-mix(in srgb,var(--c) 30%,#fff);
      border-radius:999px; padding:3px 10px; }}
  .hot {{ margin-left:auto; font-size:12.5px; font-weight:800; color:#c2410c;
      background:#fff7ed; border:1px solid #fed7aa; border-radius:999px; padding:3px 10px; white-space:nowrap; }}
  .card-title {{ margin:0; font-size:16.5px; font-weight:750; line-height:1.42; }}
  .card-title a:hover {{ color:var(--c); text-decoration:underline; }}
  .card-actions {{ display:flex; gap:8px; flex-wrap:wrap; align-self:flex-start; margin-top:auto; }}
  .read {{ font-size:13.5px; font-weight:700; color:var(--c);
      border:1px solid color-mix(in srgb,var(--c) 35%,#fff); border-radius:10px; padding:6px 12px; transition:.15s; }}
  .read:hover {{ background:var(--c); color:#fff; }}
  .sum-btn {{ font-family:inherit; line-height:inherit; background:transparent; cursor:pointer;
      margin:0; appearance:none; -webkit-appearance:none; }}
  .sum-btn:focus-visible {{ outline:2px solid var(--c); outline-offset:2px; }}
  .summary {{ padding:12px 14px; background:#fff7f8; border-left:3px solid var(--brand);
      border-radius:0 10px 10px 0; font-size:13.5px; color:var(--ink); line-height:1.7; }}
  .empty {{ background:var(--card); border:1px dashed var(--line); border-radius:16px;
      padding:30px; text-align:center; color:var(--muted); font-size:14px; }}

  .backline {{ max-width:1080px; margin:16px auto 0; padding:0 16px; }}
  .backline a {{ font-size:13.5px; font-weight:600; color:var(--brand); }}
  footer {{ max-width:1080px; margin:0 auto; padding:22px 16px 50px; color:var(--muted);
      font-size:13px; border-top:1px solid var(--line); text-align:center; }}
  @media (max-width:560px) {{ .grid {{ grid-template-columns:1fr; }}
      .expand-all {{ margin-left:0; }} .hot {{ margin-left:0; }} }}
</style>
</head>
<body>
  <header class="hero"><div class="hero-inner">
    <div class="kicker">🔥 每日热搜汇总</div>
    <h1>{date_human} · 共 {total} 条热点</h1>
    <div class="sub">统计范围 <b>{range_human}</b> · 更新于北京时间 <b>{gen_human}</b> · 聚合 {nplat} 个平台，每平台各取综合排名前 {PER_PLATFORM_TOP}</div>
    <div class="pstats">{plat_stats}</div>
  </div></header>
  <div class="backline"><a href="../index.html">← 返回当日汇总</a></div>
  <main>
    <div class="toolbar">
      <div class="sortgroup">
        <button type="button" class="sort-btn active" data-view="section">分栏查看</button>
        <button type="button" class="sort-btn" data-view="flat">平铺全部</button>
      </div>
      <button type="button" class="expand-all" data-state="collapsed">展开全部摘要</button>
    </div>
    {body}
  </main>
  <footer>
    数据来源：微博 / 百度 / 今日头条 / 知乎 / 哔哩哔哩 公开热榜 · 每平台展示其 24 小时内综合排名前 {PER_PLATFORM_TOP} 条 ·
    点击「阅读原文」跳转对应平台
  </footer>
  <script>
  (function(){{
    // 单条摘要展开/收起
    document.addEventListener('click', function(e){{
      var b = e.target.closest('.sum-btn'); if(!b) return;
      var el = document.getElementById(b.getAttribute('data-target')); if(!el) return;
      var open = el.hasAttribute('hidden');
      if(open){{ el.removeAttribute('hidden'); b.textContent='收起摘要'; }}
      else {{ el.setAttribute('hidden',''); b.textContent='展开摘要'; }}
      b.setAttribute('aria-expanded', String(open));
    }});
    // 一键展开/收起全部
    var ea = document.querySelector('.expand-all');
    if(ea){{ ea.addEventListener('click', function(){{
      var collapsed = ea.getAttribute('data-state') === 'collapsed';
      document.querySelectorAll('.summary').forEach(function(s){{
        if(collapsed) s.removeAttribute('hidden'); else s.setAttribute('hidden','');
      }});
      document.querySelectorAll('.sum-btn').forEach(function(b){{
        b.textContent = collapsed ? '收起摘要' : '展开摘要';
        b.setAttribute('aria-expanded', String(collapsed));
      }});
      ea.setAttribute('data-state', collapsed ? 'expanded' : 'collapsed');
      ea.textContent = collapsed ? '收起全部摘要' : '展开全部摘要';
    }}); }}
    // 分栏 / 平铺 切换
    var wrap = document.getElementById('wrap');
    document.querySelectorAll('.sort-btn').forEach(function(btn){{
      btn.addEventListener('click', function(){{
        document.querySelectorAll('.sort-btn').forEach(function(x){{ x.classList.remove('active'); }});
        btn.classList.add('active');
        if(wrap) wrap.classList.toggle('flat', btn.getAttribute('data-view') === 'flat');
      }});
    }});
  }})();
  </script>
</body></html>'''


# ==================== 主流程 ====================
def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()

    platform_items = {}
    for name, fn in FETCHERS:
        try:
            items = fn()                       # 抓取各平台【完整热榜，不限条数】
            platform_items[name] = items
            print(f"  {name}: 抓到 {len(items)} 条")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, ValueError, KeyError) as e:
            platform_items[name] = []
            print(f"  [跳过] {name}: {e}")

    # 每平台取自身综合排名前 PER_PLATFORM_TOP，依次分栏
    sections = []
    for name in PLATFORM_ORDER:
        items = platform_items.get(name, [])
        if not items:
            continue
        # 平台内轻量去重（避免同平台重复条目）
        dedup = []
        keys = set()
        for it in items:
            k = re.sub(r"[\s\W_#]+", "", it.get("title") or "").lower()
            if k and k in keys:
                continue
            keys.add(k)
            dedup.append(it)
        top = dedup[:PER_PLATFORM_TOP]
        if not top:
            continue
        top = enrich_scheme1(top)             # 方案1：微博/头条补真实摘要
        items_out = finalize_section(top, name)
        sections.append({"source": name, "items": items_out})

    total = sum(len(s["items"]) for s in sections)
    per_platform = {s["source"]: len(s["items"]) for s in sections}

    # 写页面
    out_dir = ROOT / date / CAT
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{CAT}-{date}.html"
    out.write_text(render_html(date, sections), encoding="utf-8")
    print(f"WROTE {out}  ({total} 条热点 / {len(sections)} 平台)")

    # 存档 JSON（便于复查 / 重渲染）
    arch_dir = ROOT / "summaries" / "hotsearch"
    arch_dir.mkdir(parents=True, exist_ok=True)
    (arch_dir / f"{date}.json").write_text(
        json.dumps({"date": date, "generated_at": _bj_now().isoformat(),
                    "total": total, "sections": sections, "per_platform": per_platform},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"WROTE {arch_dir / (date + '.json')}")
    for s in sections:
        print(f"  {s['source']}: {len(s['items'])}")


if __name__ == "__main__":
    main()
