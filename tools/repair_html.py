#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 2026-07-21 三个板块 HTML 中被 patch 脚本污染的卡片结构。

问题根源：早期 patch_final.py 把摘要文本错误注入到按钮 class、阅读原文 href、
num span 以及标签之间的杂散文本中。但每张卡片的以下字段在源 HTML 中仍然是干净的：
  - card-title 里的 <a>（标题 + 链接）
  - chip（来源）
  - card-sum（预览）
  - card-meta（日期）
  - id="sum-N" 摘要 div

本脚本：从每个 <article> 提取上述干净字段，用 render_html 的原始模板逐张重建卡片，
保留当前文章集合不变，只修正结构污染。不改动 head/hero/footer/scripts。
"""
import re
import html
import json
from pathlib import Path
from urllib.parse import urlparse

# 域名 -> 源名称映射（从 feeds.yaml 提取，用于修复被污染的 chip）
DOMAIN_SOURCE = {
    "hnrss.org": "Hacker News",
    "sspai.com": "少数派",
    "www.ifanr.com": "爱范儿",
    "36kr.com": "36氪",
    "www.qbitai.com": "量子位",
    "www.tmtpost.com": "钛媒体",
    "www.theverge.com": "The Verge",
    "seekingalpha.com": "Seeking Alpha",
    "www.cnbc.com": "CNBC",
    "www.france24.com": "France 24",
    "feeds.skynews.com": "Sky News World",
    "feeds.npr.org": "NPR",
    "moxie.foxnews.com": "Fox News World",
    "feeds.bbci.co.uk": "BBC World",
    "rss.nytimes.com": "NYT World",
    "www.aljazeera.com": "Al Jazeera",
    "www.dw.com": "DW",
}

# 英文源域名：标题和 card-sum 必须是英文，否则视作污染
EN_DOMAINS = {
    "hnrss.org", "www.theverge.com", "www.cnbc.com", "www.france24.com",
    "feeds.skynews.com", "news.sky.com", "feeds.npr.org", "moxie.foxnews.com",
    "feeds.bbci.co.uk", "rss.nytimes.com", "www.aljazeera.com",
    "www.dw.com", "seekingalpha.com",
}

# 中文字符 + 常见中文/全角标点
_CN_RE = re.compile(r'[一-鿿　-〿＀-｠]')
_WS_RE = re.compile(r'\s+')

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES = json.loads((ROOT / "summaries" / "2026-07-21.json").read_text(encoding="utf-8"))
# 摘要文本 -> 规范 url（用于回退定位）
SUMMARY_TO_URL = {}
for _k, _v in SUMMARIES.items():
    SUMMARY_TO_URL.setdefault(_v.strip(), _k)

CAT_COLORS = {"tech": "#3b82f6", "finance": "#10b981", "world": "#f59e0b"}

CARD_TMPL = '''        <article class="card" style="--c:{color}">
          <div class="card-top">
            <span class="num" style="background:{color}">{i}</span>
            <span class="chip" style="--c:{color}">{src}</span>
          </div>
          <h3 class="card-title">
            <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
          </h3>
          <p class="card-sum">{card_sum}</p>
          <div class="card-meta">🕒 {date}</div>
          <div class="card-actions">
            <a class="read" href="{url}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
            <button type="button" class="read summary-btn" data-target="sum-{i}" aria-expanded="false">原文概括</button>
          </div>
          <div class="summary" id="sum-{i}" hidden>{summary}</div>
        </article>'''


def _find_json_url(url):
    """在摘要库中定位与给定 url 对应的规范键。

    处理三类情况：
      1. 完全匹配（含 &amp; 变体）
      2. URL 被注入中文污染：取 ASCII 前缀做最长前缀匹配
      3. 不同写法（去尾斜杠、query 差异等）：归一化后匹配
    返回规范 url 字符串，找不到返回 None。
    """
    if not url or url == "#":
        return None
    if url in SUMMARIES:
        return url
    u1 = url.replace("&amp;", "&")
    if u1 in SUMMARIES:
        return u1
    # 归一化：去 query、去尾斜杠、转小写（处理 ?utm_source= 等差异）
    norm = lambda s: s.replace("&amp;", "&").split("?")[0].rstrip("/").lower()
    for cand in (url, u1):
        n = norm(cand)
        for k in SUMMARIES:
            if norm(k) == n:
                return k
    # 截断/超集容差：归一化后互为前缀（覆盖 RSS 截断的 slug）
    np_ = norm(url)
    if len(np_) > 25:
        cands = [k for k in SUMMARIES if norm(k).startswith(np_) or np_.startswith(norm(k))]
        if cands:
            return max(cands, key=len)
    # 污染 URL：取 ASCII 前缀做最长前缀匹配
    prefix = ""
    for ch in url:
        if ord(ch) > 127:
            break
        prefix += ch
    if len(prefix) > 25:
        cands = [k for k in SUMMARIES if k.startswith(prefix)]
        if cands:
            return max(cands, key=len)
    return None


def extract(block):
    """从单个 article 块提取干净字段（已被污染的字段跳过/回退）。"""
    # 来源 chip
    m = re.search(r'<span class="chip"[^>]*>([^<]+)</span>', block)
    src = html.unescape(m.group(1)).strip() if m else "未知来源"

    # 标题 + 链接（card-title 里的 <a> 大部分干净，少数被污染）
    m = re.search(r'<h3 class="card-title">\s*<a href="([^"]*)"[^>]*>(.*?)</a>',
                  block, re.DOTALL)
    if m:
        url = html.unescape(m.group(1)).strip()
        title = html.unescape(m.group(2)).strip()
    else:
        url, title = "#", "无标题"

    # 修复来源：若 chip 被污染（"未知来源" 或文字 >30字），用域名反查
    if src == "未知来源" or len(src) > 30:
        try:
            clean_url = url.replace("&amp;", "&")
            domain = urlparse(clean_url).netloc.lower()
            src = DOMAIN_SOURCE.get(domain, src)
        except Exception:
            pass

    # 预览 card-sum
    m = re.search(r'<p class="card-sum">(.*?)</p>', block, re.DOTALL)
    card_sum = html.unescape(m.group(1)).strip() if m else "点击查看完整报道"
    if not card_sum:
        card_sum = "点击查看完整报道"

    # 日期
    m = re.search(r'🕒\s*([^\n<]+)', block)
    date = m.group(1).strip() if m else "时间未知"

    # 摘要（id="sum-N" div，末尾紧跟 </article>）
    m = re.search(r'id="sum-\d+"[^>]*>(.*?)</div>\s*</article>', block, re.DOTALL)
    summary = html.unescape(m.group(1)).strip() if m else "暂无法生成概括"

    # —— 修正被污染/缺失的 URL 与摘要 ——
    # 1) 若 URL 含中文（被注入），或 URL 不在摘要库，尝试定位规范 URL
    if any(ord(c) > 127 for c in url) or url not in SUMMARIES:
        canon = _find_json_url(url)
        if canon:
            url = canon
    # 2) 规范 URL 已在摘要库中 → 用库中摘要保证与构建逻辑一致
    if url in SUMMARIES:
        # 仅当当前摘要为空/占位符时才覆盖；否则保留已注入的正确摘要
        if not summary or summary == "暂无法生成概括":
            summary = SUMMARIES[url]
    else:
        # 3) URL 仍未命中：尝试用摘要文本反查规范 URL（兜底）
        canon = SUMMARY_TO_URL.get(summary.strip())
        if canon:
            url = canon
            if not summary or summary == "暂无法生成概括":
                summary = SUMMARIES[canon]
    # 4) 摘要仍为占位符：保留占位符（已尽力）
    if summary == "暂无法生成概括":
        pass

    # 5) 英文源去污染：标题和 card-sum 都不应含 CJK 字符
    try:
        domain = urlparse(url.replace("&amp;", "&")).netloc.lower()
    except Exception:
        domain = ""
    if domain in EN_DOMAINS:
        # 英文源：无论是否检测到中文都做清理（可能前一轮已清过但留有标点残渣）
        title = _CN_RE.sub(" ", title)
        title = _WS_RE.sub(" ", title)
        title = re.sub(r'[,\s]{2,}', ' ', title).strip(" ,;:'\"")
        card_sum = _CN_RE.sub(" ", card_sum)
        card_sum = _WS_RE.sub(" ", card_sum)
        card_sum = re.sub(r'[,\s]{2,}', ' ', card_sum).strip(" ,;:'\"")
        # 去污染后若过短或看起来仍是残渣（标点占比过高），回退英文占位符
        if len(card_sum) < 25 or len(re.findall(r'[,;:]', card_sum)) / max(len(card_sum), 1) > 0.05:
            card_sum = "Click to read the full story →"

    return {
        "src": src, "url": url, "title": title,
        "card_sum": card_sum, "date": date, "summary": summary,
    }


def repair(html_text, color):
    marker = '<div class="grid">'
    idx = html_text.index(marker)
    prefix = html_text[:idx] + marker
    rest = html_text[idx + len(marker):]
    end = rest.rindex('</article>') + len('</article>')
    cards_region = rest[:end]
    suffix = rest[end:]

    blocks = re.findall(r'<article class="card".*?</article>', cards_region, re.DOTALL)
    rebuilt = []
    for i, block in enumerate(blocks, 1):
        d = extract(block)
        rebuilt.append(CARD_TMPL.format(
            color=color, i=i,
            src=html.escape(d["src"]),
            url=html.escape(d["url"]),
            title=html.escape(d["title"]),
            card_sum=html.escape(d["card_sum"]),
            date=html.escape(d["date"]),
            summary=html.escape(d["summary"]),
        ))

    return prefix + "\n" + "\n".join(rebuilt) + suffix, len(rebuilt)


def main():
    for cat in ("tech", "finance", "world"):
        color = CAT_COLORS[cat]
        path = ROOT / "2026-07-21" / cat / f"{cat}-2026-07-21.html"
        original = path.read_text(encoding="utf-8")
        fixed, n = repair(original, color)
        path.write_text(fixed, encoding="utf-8")
        # 校验：不应再出现杂散摘要文本注入特征
        bad = fixed.count("暂无法生成概括")
        print(f"{cat}: 重建 {n} 张卡片 | 占位摘要剩余 {bad} 篇 | 文件大小 {len(fixed)} 字节")


if __name__ == "__main__":
    main()
