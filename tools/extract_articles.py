#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已生成的分类页 HTML 中解析文章条目，尝试抓取并提取正文到本地文件。

用法：
  python tools/extract_articles.py [YYYY-MM-DD]   # 默认今天

输出：
  summaries/raw/<date>/index.json  [{url,title,source,date,category,rawfile,ok}]
  summaries/raw/<date>/<n>.txt     提取后的正文（仅 ok=True 时有内容）

不可达（403/超时等）的条目 rawfile 为空、ok=False，交由「原文概括」回退提示处理。
"""
import json
import re
import html
import sys
from pathlib import Path
from datetime import date as dt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from summary_lib import fetch, extract_text  # noqa: E402

DATE = sys.argv[1] if len(sys.argv) > 1 else dt.today().strftime("%Y-%m-%d")

PAGES = {
    "tech": ROOT / DATE / "tech" / f"tech-{DATE}.html",
    "finance": ROOT / DATE / "finance" / f"finance-{DATE}.html",
    "world": ROOT / DATE / "world" / f"world-{DATE}.html",
    "ai-daily": ROOT / DATE / "ai-daily" / f"ai-daily-{DATE}.html",
}

RAW_DIR = ROOT / "summaries" / "raw" / DATE
RAW_DIR.mkdir(parents=True, exist_ok=True)

_card_re = re.compile(r'<article class="card".*?</article>', re.S)
_title_re = re.compile(r'<h3 class="card-title">\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)
_read_re = re.compile(r'<a class="read"[^>]*href="([^"]*)"[^>]*>阅读原文', re.S)
_chip_re = re.compile(r'<span class="chip"[^>]*>(.*?)</span>', re.S)
_meta_re = re.compile(r'<div class="card-meta">(.*?)</div>', re.S)


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def main():
    index = []
    n = 0
    for cat, path in PAGES.items():
        if not path.exists():
            print("MISSING", path)
            continue
        doc = path.read_text(encoding="utf-8")
        for m in _card_re.finditer(doc):
            card = m.group(0)
            tm = _title_re.search(card)
            rm = _read_re.search(card)
            cm = _chip_re.search(card)
            mm = _meta_re.search(card)
            title = html.unescape(strip_tags(tm.group(2))) if tm else ""
            url = html.unescape(rm.group(1)) if rm else ""
            source = html.unescape(strip_tags(cm.group(1))) if cm else ""
            date = html.unescape(strip_tags(mm.group(1))).replace("🕒", "").strip() if mm else ""
            if not url:
                continue
            n += 1
            rawfile = ""
            ok = False
            try:
                raw = fetch(url)
                text = extract_text(raw)
                if len(text) >= 80:
                    rawfile = f"{n:03d}.txt"
                    (RAW_DIR / rawfile).write_text(text, encoding="utf-8")
                    ok = True
            except Exception as e:
                print(f"  skip {url[:60]} -> {type(e).__name__}")
            index.append({
                "url": url, "title": title, "source": source,
                "date": date, "category": cat, "rawfile": rawfile, "ok": ok,
                "round": 1 if ok else 0,
            })
            print(f"[{cat}] {'OK ' if ok else 'FAIL'} {n:03d} {title[:40]}")
    (RAW_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_count = sum(1 for x in index if x["ok"])
    print(f"\nTotal={len(index)} fetched_ok={ok_count} failed={len(index)-ok_count}")
    print(f"Index -> {RAW_DIR/'index.json'}")


if __name__ == "__main__":
    main()
