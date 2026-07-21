#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a single-file HTML AI daily dashboard from AI HOT's daily report API."""
import json
import urllib.request
import html
import datetime
from pathlib import Path

from summary_lib import summarize, SUMMARY_FAIL, load_precomputed

ROOT = Path(__file__).resolve().parent

BASE = "https://aihot.virxact.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Fixed five-section order mandated by the user.
FIXED_SECTIONS = [
    "模型发布/更新",
    "产品发布/更新",
    "行业动态",
    "论文研究",
    "技巧与观点",
]

# Accent color per section (used for number badge + chip).
SECTION_COLORS = {
    "模型发布/更新": "#3b82f6",   # blue
    "产品发布/更新": "#10b981",   # emerald
    "行业动态":     "#f59e0b",   # amber
    "论文研究":     "#8b5cf6",   # violet
    "技巧与观点":   "#ec4899",   # pink
}


def fetch(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_daily(today):
    """Try today's daily; fall back to latest available daily."""
    try:
        return fetch(f"/api/public/daily/{today}"), today, False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            latest = fetch("/api/public/daily")
            return latest, latest["date"], True
        raise


def beijing_human(iso):
    """Convert an ISO-8601 UTC timestamp to a Beijing human-readable string."""
    if not iso:
        return ""
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    bj = dt + datetime.timedelta(hours=8)
    return bj.strftime("%Y 年 %m 月 %d 日 %H:%M")


def weekday_cn(date_str):
    d = datetime.date.fromisoformat(date_str)
    return ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][d.weekday()]


def truncate(s, n=60):
    """Truncate to <=n characters (counting each char)."""
    if s is None:
        return ""
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def main():
    today = datetime.date.today().isoformat()
    data, used_date, fell_back = load_daily(today)

    # 载入预生成摘要（url -> 摘要，见 summaries/<date>.json）。
    # 即使未配置 DeepSeek API Key，本机重跑构建也能复用真实摘要。
    load_precomputed(ROOT / "summaries" / f"{used_date}.json")

    sections_in = {s["label"]: s.get("items", []) for s in data.get("sections", [])}

    # Build the fixed 5-section structure (missing => empty list).
    ordered = []
    for label in FIXED_SECTIONS:
        ordered.append((label, sections_in.get(label, [])))

    total = sum(len(items) for _, items in ordered)

    # Global continuous numbering across all sections.
    counter = 0
    cards_by_section = []
    for label, items in ordered:
        sec_cards = []
        for it in items:
            counter += 1
            sec_cards.append({
                "num": counter,
                "title": html.escape(it.get("title", "")),
                "summary": html.escape(truncate(it.get("summary", ""), 60)),
                "source": html.escape(it.get("sourceName", "AI HOT")),
                "url": html.escape(it.get("sourceUrl") or it.get("permalink") or BASE),
            })
        cards_by_section.append((label, sec_cards))

    # ----- HTML assembly -----
    date_human = f"{used_date[:4]} 年 {int(used_date[5:7])} 月 {int(used_date[8:10])} 日"
    weekday = weekday_cn(used_date)
    gen_human = beijing_human(data.get("generatedAt"))

    nav_html = ""
    for label, cards in cards_by_section:
        color = SECTION_COLORS.get(label, "#64748b")
        anchor = "sec-" + str(FIXED_SECTIONS.index(label))
        nav_html += (
            f'<a class="nav-link" href="#{anchor}" style="--c:{color}">'
            f'{html.escape(label)}<span class="nav-count">{len(cards)}</span></a>'
        )

    sections_html = ""
    n = 0
    for idx, (label, cards) in enumerate(cards_by_section):
        color = SECTION_COLORS.get(label, "#64748b")
        anchor = "sec-" + str(idx)
        count = len(cards)
        if count == 0:
            body = ('<div class="empty">本版块今日暂无条目</div>')
        else:
            grid = ""
            for c in cards:
                n += 1
                sum_text = summarize(c['url'], c['title'])
                grid += f'''
        <article class="card" style="--c:{color}">
          <div class="card-top">
            <span class="num" style="background:{color}">{c['num']}</span>
            <span class="chip" style="--c:{color}">{c['source']}</span>
          </div>
          <h3 class="card-title">
            <a href="{c['url']}" target="_blank" rel="noopener noreferrer">{c['title']}</a>
          </h3>
          <p class="card-sum">{c['summary']}</p>
          <div class="card-actions">
            <a class="read" href="{c['url']}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
            <button type="button" class="read summary-btn" data-target="sum-{n}" aria-expanded="false">原文概括</button>
          </div>
          <div class="summary" id="sum-{n}" hidden>{html.escape(sum_text)}</div>
        </article>'''
            body = f'<div class="grid">{grid}\n        </div>'

        sections_html += f'''
    <section id="{anchor}" class="section">
      <h2 class="section-title" style="--c:{color}">
        <span class="dot" style="background:{color}"></span>{html.escape(label)}
        <span class="section-count">{count}</span>
      </h2>
      {body}
    </section>'''

    fallback_banner = ""
    if fell_back:
        fallback_banner = (
            f'<div class="fallback">当日日报尚未生成，已回退展示最近一期（{used_date}）。</div>'
        )

    html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI HOT 日报 · {used_date}</title>
<style>
  :root {{
    --bg:#f6f7fb; --card:#ffffff; --ink:#0f172a; --muted:#64748b;
    --line:#e7e9f0; --brand:#6366f1;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",
      system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    background:var(--bg); color:var(--ink); line-height:1.6;
  }}
  a {{ color:inherit; text-decoration:none; }}

  /* Hero */
  .hero {{
    background:linear-gradient(135deg,#6366f1 0%,#8b5cf6 45%,#ec4899 100%);
    color:#fff; padding:46px 24px 40px;
  }}
  .hero-inner {{ max-width:1080px; margin:0 auto; }}
  .kicker {{
    font-size:13px; letter-spacing:2px; opacity:.85; text-transform:uppercase;
    font-weight:600;
  }}
  .hero h1 {{
    margin:6px 0 4px; font-size:clamp(28px,5vw,42px); font-weight:800; line-height:1.2;
  }}
  .hero .sub {{ opacity:.92; font-size:15px; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:24px; }}
  .stat {{
    background:rgba(255,255,255,.15); backdrop-filter:blur(6px);
    border:1px solid rgba(255,255,255,.25); border-radius:14px;
    padding:14px 18px; min-width:120px;
  }}
  .stat .n {{ font-size:30px; font-weight:800; line-height:1; }}
  .stat .l {{ font-size:12.5px; opacity:.9; margin-top:6px; }}
  .pills {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:22px; }}
  .pill {{
    display:inline-flex; align-items:center; gap:8px;
    background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.28);
    border-radius:999px; padding:7px 14px; font-size:13.5px; font-weight:600;
  }}
  .pill i {{ width:9px; height:9px; border-radius:50%; display:inline-block; }}

  .fallback {{
    max-width:1080px; margin:14px auto 0; background:#fef3c7; color:#92400e;
    border:1px solid #fde68a; border-radius:10px; padding:10px 14px; font-size:13.5px;
  }}

  /* Nav */
  nav {{
    position:sticky; top:0; z-index:20; background:rgba(246,247,251,.92);
    backdrop-filter:blur(8px); border-bottom:1px solid var(--line);
    padding:10px 16px;
  }}
  nav .nav-inner {{ max-width:1080px; margin:0 auto; display:flex; flex-wrap:wrap; gap:8px; }}
  .nav-link {{
    display:inline-flex; align-items:center; gap:7px; font-size:13.5px; font-weight:600;
    color:var(--ink); background:var(--card); border:1px solid var(--line);
    border-radius:999px; padding:7px 13px; transition:.15s;
  }}
  .nav-link:hover {{ border-color:var(--c); color:var(--c); }}
  .nav-count {{
    background:var(--c); color:#fff; font-size:11.5px; font-weight:700;
    border-radius:999px; padding:1px 8px;
  }}

  /* Body */
  main {{ max-width:1080px; margin:0 auto; padding:28px 16px 60px; }}
  .section {{ margin-bottom:38px; scroll-margin-top:64px; }}
  .section-title {{
    display:flex; align-items:center; gap:10px; font-size:20px; font-weight:800;
    margin:0 0 16px; padding-bottom:10px; border-bottom:2px solid var(--line);
  }}
  .section-title .dot {{ width:12px; height:12px; border-radius:4px; }}
  .section-count {{
    margin-left:auto; font-size:14px; font-weight:700; color:var(--muted);
    background:#eef0f6; border-radius:999px; padding:2px 12px;
  }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }}
  .card {{
    background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:18px; display:flex; flex-direction:column; gap:10px;
    box-shadow:0 1px 2px rgba(15,23,42,.04); transition:.18s;
    border-top:3px solid var(--c);
  }}
  .card:hover {{ transform:translateY(-3px); box-shadow:0 10px 24px rgba(15,23,42,.10); }}
  .card-top {{ display:flex; align-items:center; gap:10px; }}
  .num {{
    color:#fff; font-weight:800; font-size:14px; min-width:26px; height:26px;
    border-radius:8px; display:inline-flex; align-items:center; justify-content:center; padding:0 6px;
  }}
  .chip {{
    font-size:12px; font-weight:600; color:var(--c); background:color-mix(in srgb,var(--c) 12%,#fff);
    border:1px solid color-mix(in srgb,var(--c) 30%,#fff);
    border-radius:999px; padding:3px 10px; overflow:hidden; text-overflow:ellipsis;
    white-space:nowrap; max-width:100%;
  }}
  .card-title {{ margin:0; font-size:16.5px; font-weight:700; line-height:1.4; }}
  .card-title a:hover {{ color:var(--c); text-decoration:underline; }}
  .card-sum {{ margin:0; color:var(--muted); font-size:14px; flex:1; }}
  .read {{
    align-self:flex-start; font-size:13.5px; font-weight:700; color:var(--c);
    border:1px solid color-mix(in srgb,var(--c) 35%,#fff); border-radius:10px;
    padding:6px 12px; transition:.15s;
  }}
  .read:hover {{ background:var(--c); color:#fff; }}
  .card-actions {{ display:flex; gap:8px; flex-wrap:wrap; align-self:flex-start; margin-top:2px; }}
  .summary-btn {{ font-family:inherit; line-height:1.2; background:transparent; cursor:pointer; margin:0; appearance:none; -webkit-appearance:none; }}
  .summary-btn:focus-visible {{ outline:2px solid var(--c); outline-offset:2px; }}
  .summary {{ margin-top:10px; padding:12px 14px; background:#f8fafc;
      border-left:3px solid var(--c); border-radius:0 10px 10px 0;
      font-size:13.5px; color:var(--ink); line-height:1.7; }}
  .empty {{
    background:var(--card); border:1px dashed var(--line); border-radius:16px;
    padding:28px; text-align:center; color:var(--muted); font-size:14px;
  }}

  /* Footer */
  footer {{
    max-width:1080px; margin:0 auto; padding:22px 16px 50px; color:var(--muted);
    font-size:13px; border-top:1px solid var(--line); text-align:center;
  }}
  footer a {{ color:var(--brand); font-weight:600; }}
  @media (max-width:560px) {{
    .stat {{ min-width:calc(50% - 7px); }}
    .grid {{ grid-template-columns:1fr; }}
  }}
</style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <div class="kicker">AI HOT 日报</div>
      <h1>{date_human} · {weekday}</h1>
      <div class="sub">共 {total} 条 · 生成于 北京时间 {gen_human} · 数据覆盖 {data.get('windowStart','')[:10]} ~ {data.get('windowEnd','')[:10]}</div>
      <div class="stats">
        <div class="stat"><div class="n">{total}</div><div class="l">今日总条数</div></div>
        <div class="stat"><div class="n">5</div><div class="l">固定版块</div></div>
        {''.join(f'<div class="stat"><div class="n">{len(c)}</div><div class="l">{html.escape(lbl)}</div></div>' for lbl,c in cards_by_section)}
      </div>
      <div class="pills">
        {''.join(f'<span class="pill" style="--c:{SECTION_COLORS.get(lbl,"#64748b")}"><i style="background:{SECTION_COLORS.get(lbl,"#64748b")}"></i>{html.escape(lbl)} · {len(c)}</span>' for lbl,c in cards_by_section)}
      </div>
    </div>
  </header>
  {fallback_banner}
  <nav>
    <div class="nav-inner">{nav_html}</div>
  </nav>
  <main>{sections_html}
  </main>
  <footer>
    本日报共 <strong>{total}</strong> 条 · 数据来源：<a href="https://aihot.virxact.com" target="_blank" rel="noopener noreferrer">aihot.virxact.com</a>
    {f' · 回退自 {used_date}' if fell_back else ''}
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
</body>
</html>'''

    # 输出到 <ROOT>/YYYY-MM-DD/ai-daily/，与 build_archive.py 的扫描目录一致，
    # 并使用相对 ROOT 的路径以保证可移植（CI / 其他机器均可运行）。
    out_dir = ROOT / used_date / "ai-daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ai-daily-{used_date}.html"
    out.write_text(html_doc, encoding="utf-8")
    print("WROTE", out)
    print("date:", used_date, "| total:", total, "| fell_back:", fell_back)
    for lbl, c in cards_by_section:
        print(f"  {lbl}: {len(c)}")


if __name__ == "__main__":
    main()
