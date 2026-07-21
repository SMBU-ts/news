#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接替换HTML中的"暂无法生成概括"文本。

逐篇文章提取URL，用多级模糊匹配查找摘要，直接替换。"""

import json
import re
import html as html_mod
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent.parent
SUMMARIES_PATH = ROOT / "summaries" / "2026-07-21.json"

summaries = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
print(f"摘要库: {len(summaries)} 篇")

def normalize(url):
    """激进归一化：去query、去尾斜杠、小写、去特殊字符差异。"""
    p = urlparse(url)
    base = (p.netloc + p.path).rstrip("/").lower()
    # 统一数字格式
    base = base.replace("-2.49", "-249").replace("-1.94", "-194").replace("-1.53", "-153")
    base = base.replace("_", "-").replace(".", "-")
    return base

# 构建多级索引
exact_index = summaries  # 精确匹配
norm_index = {}  # 归一化匹配
prefix_index = {}  # 前缀匹配（path前40字符）
domain_index = {}  # 域名+path前20字符匹配

for key in summaries:
    norm = normalize(key)
    norm_index[norm] = key
    
    p = urlparse(key)
    prefix = (p.netloc + p.path[:40]).lower()
    if prefix not in prefix_index:
        prefix_index[prefix] = key
    
    domain = (p.netloc + p.path[:20]).lower()
    if domain not in domain_index:
        domain_index[domain] = key

def find_summary(url):
    """多级查找摘要。"""
    # 1. 精确匹配
    if url in exact_index:
        return exact_index[url]
    
    # 2. 去query参数后匹配
    p = urlparse(url)
    clean_url = f"{p.scheme}://{p.netloc}{p.path}"
    if clean_url in exact_index:
        return exact_index[clean_url]
    
    # 3. 归一化匹配
    norm = normalize(url)
    if norm in norm_index:
        return summaries[norm_index[norm]]
    
    # 4. 前缀匹配（40字符）
    prefix = (p.netloc + p.path[:40]).lower()
    if prefix in prefix_index:
        return summaries[prefix_index[prefix]]
    
    # 5. 域名+短前缀匹配（20字符）
    domain = (p.netloc + p.path[:20]).lower()
    if domain in domain_index:
        return summaries[domain_index[domain]]
    
    # 6. 遍历查找包含关系
    url_lower = url.lower()
    for key, val in summaries.items():
        key_clean = key.split("?")[0].lower()
        if key_clean in url_lower or url_lower in key_clean:
            return val
    
    return None


total_patched = 0
total_articles = 0
total_with_summary = 0

for cat in ["tech", "finance", "world"]:
    html_path = ROOT / "2026-07-21" / cat / f"{cat}-2026-07-21.html"
    content = html_path.read_text(encoding="utf-8")
    
    # 提取所有文章卡片：URL + 摘要div
    # 每个article块包含一个card-title链接和一个summary div
    article_pattern = re.compile(
        r'<article class="card"[^>]*>.*?'
        r'class="card-title">\s*<a href="([^"]+)"[^>]*>([^<]*)</a>'
        r'.*?'
        r'id="sum-(\d+)"[^>]*>([^<]*)</div>',
        re.DOTALL
    )
    
    patched = 0
    cat_total = 0
    cat_has = 0
    
    for match in article_pattern.finditer(content):
        raw_url = match.group(1)
        title = html_mod.unescape(match.group(2)).strip()
        sum_id = match.group(3)
        sum_content = match.group(4).strip()
        
        cat_total += 1
        url = html_mod.unescape(raw_url)
        
        if "暂无法生成概括" not in sum_content and sum_content:
            cat_has += 1
            continue
        
        # 查找摘要
        summary = find_summary(url)
        if summary:
            escaped = html_mod.escape(summary)
            old_pattern = f'id="sum-{sum_id}" hidden>{sum_content}</div>'
            new_pattern = f'id="sum-{sum_id}" hidden>{escaped}</div>'
            if old_pattern in content:
                content = content.replace(old_pattern, new_pattern, 1)
                patched += 1
                cat_has += 1
            else:
                # 尝试不依赖hidden属性
                old_pattern2 = f'id="sum-{sum_id}"[^>]*>{sum_content}</div>'
                content = re.sub(old_pattern2, f'id="sum-{sum_id}" hidden>{escaped}</div>', content, count=1)
                if "暂无法生成概括" not in content[match.start(4):match.end(4)+50]:
                    patched += 1
                    cat_has += 1
    
    html_path.write_text(content, encoding="utf-8")
    total_patched += patched
    total_articles += cat_total
    total_with_summary += cat_has
    remaining = content.count("暂无法生成概括")
    print(f"{cat}: 补丁 {patched} 篇, 剩余 {remaining} 个回退文本")

print(f"\n总计: 补丁 {total_patched} 篇")

# 最终验证
print("\n=== 最终覆盖率 ===")
for cat in ["tech", "finance", "world"]:
    html = (ROOT / "2026-07-21" / cat / f"{cat}-2026-07-21.html").read_text(encoding="utf-8")
    remaining = html.count("暂无法生成概括")
    total = len(re.findall(r'class="card"', html))
    has = total - remaining
    print(f"  {cat}: {has}/{total} ({has/total*100:.0f}%) - 剩余 {remaining} 个回退")
