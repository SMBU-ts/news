#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并新摘要并直接修补HTML中的"暂无法生成概括"文本。"""

import json
import re
import html as html_mod
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "summaries" / "2026-07-21.json"

# === Step 1: Load existing summaries ===
summaries = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
before = len(summaries)
print(f"现有摘要: {before} 篇")

# === Step 2: Define URL normalization for fuzzy matching ===
def normalize_url(url):
    p = urlparse(url)
    base = p.netloc + p.path.rstrip("/").lower()
    base = base.replace("-2.49", "-249").replace("-1.94", "-194").replace("-1.53", "-153")
    return base

# Build normalized index
norm_index = {}
for key in summaries:
    norm_index[normalize_url(key)] = key

def find_summary(url):
    """Try exact match, then normalized match, then prefix match."""
    if url in summaries:
        return summaries[url]
    norm = normalize_url(url)
    if norm in norm_index:
        return summaries[norm_index[norm]]
    # Prefix match (first 30 chars of path)
    p = urlparse(url)
    prefix = p.netloc + p.path[:30].lower()
    for key in summaries:
        kp = urlparse(key)
        if kp.netloc + kp.path[:30].lower() == prefix:
            return summaries[key]
    return None

# === Step 3: Patch HTML files ===
total_patched = 0
total_articles = 0
total_with_summary = 0

for cat in ["tech", "finance", "world"]:
    html_path = ROOT / "2026-07-21" / cat / f"{cat}-2026-07-21.html"
    html_content = html_path.read_text(encoding="utf-8")

    # Find all summary divs
    # Pattern: id="sum-N" hidden>CONTENT</div>
    patched = 0
    cat_total = 0
    cat_has = 0

    # Process each summary div
    for match in re.finditer(r'id="sum-(\d+)"[^>]*>([^<]*)</div>', html_content):
        div_id = match.group(1)
        content = match.group(2).strip()
        cat_total += 1

        if "暂无法生成概括" not in content and content:
            cat_has += 1
            continue  # Already has a real summary

        # Find the corresponding article URL (search backwards for card-title)
        pos = match.start()
        card_match = None
        for cm in re.finditer(r'class="card-title">\s*<a href="([^"]+)"', html_content[:pos]):
            card_match = cm
        if not card_match:
            continue

        raw_url = card_match.group(1)
        url = html_mod.unescape(raw_url)

        summary = find_summary(url)
        if summary:
            escaped_summary = html_mod.escape(summary)
            old_text = match.group(2)
            html_content = html_content[:match.start(2)] + escaped_summary + html_content[match.end(2):]
            patched += 1
            cat_has += 1

    html_path.write_text(html_content, encoding="utf-8")
    total_patched += patched
    total_articles += cat_total
    total_with_summary += cat_has
    pct = (cat_has / cat_total * 100) if cat_total else 0
    print(f"{cat}: 补丁 {patched} 篇, 覆盖率 {cat_has}/{cat_total} ({pct:.0f}%)")

pct_total = (total_with_summary / total_articles * 100) if total_articles else 0
print(f"\n总计: 补丁 {total_patched} 篇, 覆盖率 {total_with_summary}/{total_articles} ({pct_total:.0f}%)")
