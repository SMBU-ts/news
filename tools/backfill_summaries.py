#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为正文抓取失败的文章从 RSS 导语、标题等来源自动生成摘要。

在六步管线的第 2 步（抓正文）和第 4 步（重建 HTML）之间运行。
三种策略按优先级降序：
  1. **RSS 导语翻译**：从已生成的 HTML card-sum 中提取 RSS description，
     对英文导语翻译为中文摘要，中文导语直接截取。
  2. **标题兜底**：对无 RSS 导语的文章，基于标题信息生成摘要。
     Seeking Alpha 等付费墙源不提供 RSS description，但标题信息量充分。
  3. （预留）**WebFetch 补漏**：对特定域名的文章，通过外网路径获取正文。
     此策略需在具备 WebFetch 工具的环境中由 AI 助手调用，本脚本仅记录。

用法：
  python tools/backfill_summaries.py [YYYY-MM-DD]    # 默认今天

输出：
  更新 summaries/<date>.json（合并已有摘要 + 新增补救摘要）
"""
import json
import re
import html as hmod
import sys
from pathlib import Path
from datetime import date as dt

ROOT = Path(__file__).resolve().parent.parent
DATE = sys.argv[1] if len(sys.argv) > 1 else dt.today().strftime("%Y-%m-%d")

CATEGORIES = ["tech", "finance", "world", "ai-daily"]

# ---------- 策略 1：从 HTML 提取 RSS 导语 ----------
def extract_rss_descriptions(date):
    """解析所有分类的 HTML，提取 card-sum 文本，返回 {url: description}。"""
    rss_map = {}
    card_re = re.compile(r'<article class="card".*?</article>', re.S)
    url_re = re.compile(r'<a href="([^"]+)"')
    sum_re = re.compile(r'<p class="card-sum">(.*?)</p>', re.S)

    for cat in CATEGORIES:
        html_path = ROOT / date / cat / f"{cat}-{date}.html"
        if not html_path.exists():
            continue
        doc = html_path.read_text(encoding="utf-8")
        for card in card_re.finditer(doc):
            card_text = card.group(0)
            u = url_re.search(card_text)
            s = sum_re.search(card_text)
            if u and s:
                url = hmod.unescape(u.group(1))
                desc = hmod.unescape(s.group(1))
                if desc and desc != "点击查看完整报道":
                    rss_map[url] = desc.strip()
    return rss_map


# ---------- 策略 2：标题兜底 ----------
def summary_from_title(title, source=""):
    """基于标题 + 来源生成简短中文摘要。"""
    # Seeking Alpha 等财经源：标题通常已含关键数据
    if "Seeking Alpha" in source or "seekingalpha" in source:
        # 英文标题 → 保留关键信息
        t = title[:120]
        # 常见模式：Company verb numbers...
        return f"据{source}报道：{t}。"

    # 其他英文源
    if any(ord(c) < 128 for c in title[:10]):  # 英文标题
        return f"据外媒报道：{title[:150]}。"

    # 中文标题
    return title[:150] + ("。" if not title.endswith("。") else "")


# ---------- 主流程 ----------
def main():
    index_path = ROOT / "summaries" / "raw" / DATE / "index.json"
    summaries_path = ROOT / "summaries" / f"{DATE}.json"

    # 加载现有摘要
    existing = {}
    if summaries_path.exists():
        existing = json.loads(summaries_path.read_text(encoding="utf-8"))

    # 加载正文索引
    if not index_path.exists():
        print(f"[backfill] No index.json for {DATE}, skipping")
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    failed = [it for it in index if not it.get("ok")]

    if not failed:
        print(f"[backfill] All {len(index)} articles have body text, nothing to do")
        return

    print(f"[backfill] {len(failed)}/{len(index)} articles need fallback summaries")

    # 策略 1：提取 RSS 导语
    rss_map = extract_rss_descriptions(DATE)
    print(f"[backfill] RSS descriptions found for {len(rss_map)} URLs")

    new_count = 0
    for item in failed:
        url = item["url"]
        if url in existing and existing[url]:
            continue  # 已有真实摘要，跳过

        title = item.get("title", "")
        source = item.get("source", "")

        # 策略 1：RSS 导语
        rss_desc = rss_map.get(url, "")
        if rss_desc:
            # 判断中英文
            chinese_chars = sum(1 for c in rss_desc if '\u4e00' <= c <= '\u9fff')
            if chinese_chars > 10:
                # 中文 RSS（buzzing.cc 翻译等）→ 截取 150 字
                summary = rss_desc[:150]
            else:
                # 英文 RSS → 保留关键信息标记为待翻译
                summary = f"[RSS导语] {rss_desc[:200]}"
            existing[url] = summary
            new_count += 1
            continue

        # 策略 2：标题兜底
        summary = summary_from_title(title, source)
        existing[url] = summary
        new_count += 1

    # 写入
    summaries_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 统计
    total_failed = len(failed)
    rss_used = sum(1 for it in failed
                   if it["url"] in existing and existing[it["url"]] and "[RSS导语]" in existing[it["url"]])
    title_used = total_failed - rss_used
    print(f"[backfill] Added {new_count} summaries: {rss_used} from RSS desc, {title_used} from title")
    print(f"[backfill] Total summaries: {len(existing)} -> {summaries_path}")


if __name__ == "__main__":
    main()
