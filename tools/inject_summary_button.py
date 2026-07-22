#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「原文概括」按钮 + 摘要面板 + 配套 CSS/JS 注入已生成的分类页 HTML。

- 不依赖 RSS、不重新抓取，直接对现有 HTML 做 DOM 级改造（与 build_*.py 产物一致）。
- 摘要来源于 summaries/<date>.json（url -> 摘要）；缺失的条目回退「暂无法生成概括」。
- 幂等：已注入过的文件再次运行不会重复添加。

用法：
    python tools/inject_summary_button.py [date]
默认 date=2026-07-20。
"""
import json
import re
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-07-20"

SUMMARIES = ROOT / "summaries" / f"{DATE}.json"
FALLBACK = "暂无法生成概括"

PAGES = {
    "tech": ROOT / "2026-07-20" / "tech" / "tech-2026-07-20.html",
    "finance": ROOT / "2026-07-20" / "finance" / "finance-2026-07-20.html",
    "world": ROOT / "2026-07-20" / "world" / "world-2026-07-20.html",
    "ai-daily": ROOT / "2026-07-20" / "ai-daily" / "ai-daily-2026-07-20.html",
}

CSS = """
  .card-actions { display:flex; gap:8px; flex-wrap:wrap; align-self:flex-start; margin-top:2px; }
  .summary-btn { font-family:inherit; line-height:inherit; background:transparent; cursor:pointer; margin:0; appearance:none; -webkit-appearance:none; }
  .summary-btn:focus-visible { outline:2px solid var(--c); outline-offset:2px; }
  .summary { margin-top:10px; padding:12px 14px; background:#f8fafc;
      border-left:3px solid var(--c); border-radius:0 10px 10px 0;
      font-size:13.5px; color:var(--ink); line-height:1.7; }
"""

JS = """
  document.addEventListener('click', function(e){
    var b = e.target.closest('.summary-btn'); if(!b) return;
    var el = document.getElementById(b.getAttribute('data-target')); if(!el) return;
    var open = el.hasAttribute('hidden');
    if(open){ el.removeAttribute('hidden'); } else { el.setAttribute('hidden',''); }
    b.setAttribute('aria-expanded', String(open));
  });
"""

# 匹配卡片末尾的「阅读原文」链接，捕获其完整锚点与紧跟的 </article>
# （不限定前一个闭合标签，兼容 RSS 页的 </div> 与 AI 日报页的 </p>）
CARD_RE = re.compile(
    r'(?P<pre>\s*)(?P<read><a class="read" href="(?P<url>[^"]*)"[^>]*>阅读原文 →</a>)(?P<post>\s*</article>)',
    re.S,
)


def load_summaries():
    try:
        return json.loads(SUMMARIES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    summaries = load_summaries()
    print(f"Loaded {len(summaries)} precomputed summaries from {SUMMARIES.name}")

    for cat, path in PAGES.items():
        if not path.exists():
            print("MISSING", path)
            continue
        doc = path.read_text(encoding="utf-8")
        if 'class="read summary-btn"' in doc:
            print(f"[{cat}] already injected, skip")
            continue

        # 1) 注入 CSS（用摘要面板样式作去重标记，避免与按钮类名混淆）
        if ".summary {" not in doc and "</style>" in doc:
            doc = doc.replace("</style>", CSS + "</style>", 1)
        # 2) 注入 JS（用切换逻辑特征串去重）
        if "closest('.summary-btn')" not in doc and "</body>" in doc:
            doc = doc.replace("</body>", "<script>" + JS + "</script></body>", 1)

        # 3) 逐卡片包裹按钮 + 摘要面板
        counter = {"n": 0}

        def repl(m):
            counter["n"] += 1
            n = counter["n"]
            anchor = m.group(2)
            raw_url = html.unescape(m.group("url"))
            text = summaries.get(raw_url, FALLBACK)
            safe = html.escape(text, quote=True)
            return (
                f'{m.group("pre")}'
                f'<div class="card-actions">\n'
                f'            {anchor}\n'
                f'            <button type="button" class="read summary-btn" '
                f'data-target="sum-{n}" aria-expanded="false">原文概括</button>\n'
                f'          </div>\n'
                f'          <div class="summary" id="sum-{n}" hidden>{safe}</div>\n'
                f'        {m.group("post")}'
            )

        new_doc, count = CARD_RE.subn(repl, doc)
        path.write_text(new_doc, encoding="utf-8")
        real = sum(1 for _ in range(count) if True)
        print(f"[{cat}] injected {count} buttons ({path.name})")

    print("Done.")


if __name__ == "__main__":
    main()
