#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成每日20条（时政要闻）精简版。

调用 tencent-news-cli hot 接口获取热门新闻榜，取 TOP 20，
生成简洁编号列表 HTML 页面。每条仅标题 + 一行摘要。

用法：
    python build_daily20.py                  # 今天
    python build_daily20.py 2026-07-22       # 指定日期
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI = ROOT / "tools" / "tnc.exe"
CAT = "daily20"
BRAND = "#8b5cf6"
TOOL_DIR = ROOT / "tools"

# 北京时区
TZ = timezone(timedelta(hours=8))


# ── CLI 调用 ──────────────────────────────────────────────────────

def _check_cli():
    """检查 CLI 是否存在且有 API Key。"""
    if not CLI.exists():
        print(f"[错误] 未找到 CLI：{CLI}", file=sys.stderr)
        print(f"  请从 https://mat1.gtimg.com/qqcdn/qqnews/cli/hub/windows-amd64/tencent-news-cli.exe 下载", file=sys.stderr)
        return False

    r = subprocess.run(
        [str(CLI), "apikey-get"],
        capture_output=True, text=True, timeout=15, cwd=ROOT
    )
    if r.returncode != 0 or "未设置" in (r.stdout + r.stderr):
        print("[错误] API Key 未配置", file=sys.stderr)
        print("  请访问 https://news.qq.com/exchange?scene=appkey 获取 Key", file=sys.stderr)
        print(f"  然后运行: {CLI} apikey-set <你的KEY>", file=sys.stderr)
        return False
    return True


def _fetch_hot(limit=20):
    """调用 CLI hot 命令，返回原始文本。"""
    r = subprocess.run(
        [str(CLI), "hot", "--limit", str(limit)],
        capture_output=True, text=True, timeout=30, cwd=ROOT
    )
    stdout = r.stdout.strip()
    stderr = r.stderr.strip()

    if r.returncode != 0:
        err = stderr or stdout or f"exit code {r.returncode}"
        raise RuntimeError(f"CLI hot 命令失败: {err}")

    return stdout


def _clean(s, max_len=120):
    """清理文本：去 HTML 标签、合并空白、截断。"""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_len and len(s) > max_len:
        s = s[:max_len-3] + "..."
    return s


# ── 解析 CLI 输出 ──────────────────────────────────────────────────

def _parse_hot_output(text):
    """解析 CLI 输出为结构化列表。

    实际格式（tencent-news-cli hot）：
        【腾讯新闻 - 热点榜】 2026-07-22 21:57

        1. 标题：<actual title>
           摘要: <summary text>
           来源: <source name>
           发布时间: <iso time>
           链接: <url>

    返回 list[dict]: {title, summary, source, url, time}
    """
    items = []
    # 跳过头行（【腾讯新闻 - 热点榜】 ...）
    # 按 "N. 标题：" 分割条目
    blocks = re.split(r"\n(?=\d+\.\s*标题[：:])", text)
    for block in blocks:
        if not block.strip():
            continue

        item = {"title": "", "summary": "", "source": "", "url": "", "time": ""}

        # 标题: N. 标题：<text>
        title_m = re.match(r"\d+\.\s*标题[：:]\s*(.+?)(?:\n|$)", block)
        if title_m:
            item["title"] = title_m.group(1).strip()

        # 摘要
        summary_m = re.search(r"\n\s*摘要[：:]\s*(.+?)(?:\n|$)", block)
        if summary_m:
            item["summary"] = _clean(summary_m.group(1).strip(), max_len=200)

        # 来源
        src_m = re.search(r"\n\s*来源[：:]\s*(.+?)(?:\n|$)", block)
        if src_m:
            item["source"] = src_m.group(1).strip()

        # 发布时间
        time_m = re.search(r"\n\s*发布时间[：:]\s*(.+?)(?:\n|$)", block)
        if time_m:
            item["time"] = time_m.group(1).strip()

        # 链接
        link_m = re.search(r"\n\s*链接[：:]\s*(.+?)(?:\n|$)", block)
        if link_m:
            item["url"] = link_m.group(1).strip()

        if item["title"]:
            items.append(item)

    return items


# ── HTML 渲染 ─────────────────────────────────────────────────────

def render_html(date_str, items):
    """生成自包含 HTML 页面。"""
    date_display = date_str
    now_ts = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    items_html = ""
    for i, item in enumerate(items, 1):
        title = _clean(item["title"], max_len=200)
        summary = item.get("summary", "")
        source = item.get("source", "")
        url = item.get("url", "")
        time_str = item.get("time", "")

        # 如果没有摘要，用来源兜底
        meta_parts = []
        if source:
            meta_parts.append(source)
        if time_str:
            meta_parts.append(time_str)
        meta = " · ".join(meta_parts) if meta_parts else ""

        # 链接处理
        title_html = (
            f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
            if url
            else title
        )

        items_html += f"""
        <div class="item">
            <span class="num">{i:02d}</span>
            <div class="item-body">
                <div class="item-title">{title_html}</div>
                {f'<div class="item-summary">{summary}</div>' if summary else ''}
                {f'<div class="item-meta">{meta}</div>' if meta else ''}
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日20条 · 时政精要 — {date_display}</title>
<style>
:root {{
    --bg: #f8f9fb;
    --card: #ffffff;
    --ink: #1e1e2e;
    --muted: #6b7280;
    --line: #e5e7eb;
    --brand: {BRAND};
    --brand-light: #ede9fe;
}}

* {{ margin:0; padding:0; box-sizing:border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
    background: var(--bg);
    color: var(--ink);
    line-height: 1.6;
    min-height: 100vh;
}}

/* ── Hero ── */
.hero {{
    background: linear-gradient(135deg, var(--brand) 0%, #7c3aed 50%, #6d28d9 100%);
    color: #fff;
    padding: 48px 20px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
}}
.hero::before {{
    content: "";
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at 20% 50%, rgba(255,255,255,.08) 0%, transparent 60%),
                radial-gradient(circle at 80% 30%, rgba(255,255,255,.05) 0%, transparent 50%);
}}
.hero-icon {{
    font-size: 48px;
    margin-bottom: 12px;
    position: relative;
}}
.hero h1 {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: .02em;
    position: relative;
}}
.hero .sub {{
    font-size: 14px;
    opacity: .8;
    margin-top: 6px;
    position: relative;
}}
.hero .date-tag {{
    display: inline-block;
    margin-top: 14px;
    padding: 4px 16px;
    background: rgba(255,255,255,.15);
    border-radius: 20px;
    font-size: 13px;
    letter-spacing: .03em;
    position: relative;
}}

/* ── Layout ── */
.container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 0 20px;
}}

/* ── Backline ── */
.backline {{
    text-align: center;
    padding: 16px 0 8px;
}}
.backline a {{
    color: var(--muted);
    font-size: 13px;
    text-decoration: none;
    transition: color .2s;
}}
.backline a:hover {{ color: var(--brand); }}

/* ── List ── */
.list {{
    background: var(--card);
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.03);
    margin: 8px 0 40px;
    overflow: hidden;
}}

.item {{
    display: flex;
    align-items: flex-start;
    gap: 16px;
    padding: 18px 24px;
    border-bottom: 1px solid var(--line);
    transition: background .15s;
}}
.item:last-child {{ border-bottom: none; }}
.item:hover {{ background: #fafbff; }}

.num {{
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    font-weight: 700;
    color: var(--brand);
    background: var(--brand-light);
    border-radius: 10px;
    margin-top: 2px;
}}

/* 前三名特殊样式 */
.item:nth-child(1) .num {{ background: var(--brand); color: #fff; }}
.item:nth-child(2) .num {{ background: #c4b5fd; color: #5b21b6; }}
.item:nth-child(3) .num {{ background: #ddd6fe; color: #6d28d9; }}

.item-body {{ flex: 1; min-width: 0; }}

.item-title {{
    font-size: 16px;
    font-weight: 600;
    line-height: 1.5;
    color: var(--ink);
    margin-bottom: 4px;
}}
.item-title a {{
    color: inherit;
    text-decoration: none;
    transition: color .15s;
}}
.item-title a:hover {{ color: var(--brand); }}

.item-summary {{
    font-size: 14px;
    color: var(--muted);
    line-height: 1.5;
    margin-bottom: 4px;
}}

.item-meta {{
    font-size: 12px;
    color: #9ca3af;
}}

/* ── Footer ── */
.footer {{
    text-align: center;
    padding: 24px 20px 40px;
    font-size: 12px;
    color: #9ca3af;
}}
.footer a {{ color: var(--muted); text-decoration: none; }}
.footer a:hover {{ color: var(--brand); }}

/* ── Empty State ── */
.empty {{
    text-align: center;
    padding: 80px 20px;
    color: var(--muted);
}}
.empty .icon {{ font-size: 48px; margin-bottom: 12px; }}

/* ── Responsive ── */
@media (max-width: 560px) {{
    .hero {{ padding: 36px 16px 30px; }}
    .hero h1 {{ font-size: 22px; }}
    .item {{ padding: 14px 16px; gap: 12px; }}
    .item-title {{ font-size: 15px; }}
    .num {{ width: 30px; height: 30px; font-size: 13px; border-radius: 8px; }}
}}
</style>
</head>
<body>

<header class="hero">
    <div class="hero-icon">📋</div>
    <h1>每日20条 · 时政精要</h1>
    <div class="sub">一天大事，二十条尽览</div>
    <div class="date-tag">{date_display}</div>
</header>

<div class="backline">
    <a href="../../archive.html">← 返回汇总</a>
</div>

<div class="container">
    {f'<div class="list">{items_html}\n    </div>' if items else '<div class="empty"><div class="icon">📭</div><p>暂无数据</p></div>'}
</div>

<footer class="footer">
    <p>数据来源：<a href="https://news.qq.com/" target="_blank" rel="noopener">腾讯新闻</a> · 生成时间 {now_ts}</p>
    <p style="margin-top:4px">Powered by <a href="https://github.com/SMBU-ts/news" target="_blank" rel="noopener">每日新闻站</a></p>
</footer>

</body>
</html>"""


# ── JSON 存档 ──────────────────────────────────────────────────────

def save_json(date_str, items):
    """保存结构化数据到 summaries/daily20/<date>.json。"""
    out_dir = ROOT / "summaries" / CAT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.json"

    data = {
        "date": date_str,
        "generated_at": datetime.now(TZ).isoformat(),
        "total": len(items),
        "items": [
            {
                "rank": i + 1,
                "title": item["title"],
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "time": item.get("time", ""),
            }
            for i, item in enumerate(items)
        ],
    }
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  JSON → {out_path}")


# ── 主流程 ─────────────────────────────────────────────────────────

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).strftime("%Y-%m-%d")

    print(f"[每日20条] 日期: {date_str}")

    # 1. 检查 CLI 环境
    if not _check_cli():
        sys.exit(1)

    # 2. 抓取
    print("  正在抓取腾讯新闻热榜...")
    try:
        raw = _fetch_hot(limit=20)
    except Exception as e:
        print(f"[错误] 抓取失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not raw.strip():
        print("[错误] CLI 返回空内容", file=sys.stderr)
        sys.exit(1)

    # 3. 解析
    items = _parse_hot_output(raw)
    if not items:
        print("[错误] 未能解析任何条目", file=sys.stderr)
        # 打印原始输出前 500 字符供调试
        print(f"  原始输出前500字: {raw[:500]}", file=sys.stderr)
        sys.exit(1)

    print(f"  解析到 {len(items)} 条新闻")

    # 4. 去重（按标题规范化）
    seen = set()
    deduped = []
    for item in items:
        key = re.sub(r"\s+", "", item["title"])
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    if len(deduped) < len(items):
        print(f"  去重后 {len(deduped)} 条（移除 {len(items)-len(deduped)} 条重复）")
    items = deduped[:20]

    # 5. 生成 HTML
    out_dir = ROOT / date_str / CAT
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{CAT}-{date_str}.html"
    html = render_html(date_str, items)
    html_path.write_text(html, encoding="utf-8")
    print(f"  HTML → {html_path}")

    # 6. 保存 JSON
    save_json(date_str, items)

    # 7. 打印预览
    print(f"\n  {'='*50}")
    print(f"  共 {len(items)} 条时政要闻")
    print(f"  {'='*50}")
    for i, item in enumerate(items, 1):
        title = _clean(item["title"], max_len=60)
        src = item.get("source", "")
        print(f"  {i:2d}. {title}{'  [' + src + ']' if src else ''}")


if __name__ == "__main__":
    main()
