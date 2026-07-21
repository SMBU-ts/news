#!/usr/bin/env python3
"""外科手术式更新：仅替换已有 HTML 中特定「暂无法生成概括」为真实摘要。
只会修改匹配到对应 URL 且当前面板内容=「暂无法生成概括」的卡片，其余不动。"""
import re
import json
import sys
import html as hlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-20"
SUMMARIES_PATH = ROOT / "summaries" / f"{DATE}.json"
FINANCE_HTML = ROOT / DATE / "finance" / f"finance-{DATE}.html"

summaries = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
doc = FINANCE_HTML.read_text(encoding="utf-8")

updated = 0
# 匹配每篇文章块：阅读原文链接（取 url）... 摘要面板（"暂无法生成概括"）
PAT = re.compile(
    r'(<a class="read" href="(?P<url>[^"]+)"[^>]*?>阅读原文 →</a>.*?</button>'
    r'\s*</div>\s*<div class="summary"[^>]*id="(?P<id>[^"]+)"[^>]*>)'
    r'暂无法生成概括'
    r'(?P<closing></div>)',
    re.S,
)

def repl(m):
    global updated
    url = hlib.unescape(m.group("url"))
    if url in summaries:
        updated += 1
        return m.group(1) + summaries[url] + m.group("closing")
    return m.group(0)

new_doc, n = PAT.subn(repl, doc)
print(f"替换了 {updated} 处回退 → 真实摘要 (finance)")
FINANCE_HTML.write_text(new_doc, encoding="utf-8")
print("Done.")
