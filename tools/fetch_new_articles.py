#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 2 动态正文抓取：从 summaries/raw/<date>/index.json 读取 Round 1
（tools/extract_articles.py）未成功的条目，用「宽松 UA + Referer + 随机抖动 +
指数退避重试」再抓一次；成功后写入 NNN.txt 并把该条目在 index.json 中标记为
ok=True / rawfile=NNN.txt / round=2。

要点：
  - 不再硬编码任何 URL，目标完全由 index.json 决定（与 build_rss 解耦）。
  - 复用 summary_lib.extract_text 做正文提取（与 Round 1 口径一致、去噪、截断）。
  - 抓取逻辑与 crawler.py 同源：随机 UA 池 + 429/5xx 自动重试 + gzip 解压。
  - 失败条目标记 round=2（表示该轮已尝试），交由 Round 3（Playwright）兜底，
    因此本脚本可安全重复运行而不会产生副作用（幂等）。
  - 标准库实现，零第三方依赖。

用法：
  python tools/fetch_new_articles.py [YYYY-MM-DD]      # 默认今天
"""
import json
import re
import sys
import time
import random
import gzip
import ssl
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date as dt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from summary_lib import extract_text  # 复用 Round 1 同款正文提取

DATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else dt.today().strftime("%Y-%m-%d")
RAW_DIR = ROOT / "summaries" / "raw" / DATE
INDEX = RAW_DIR / "index.json"

# 复用 crawler.py 的随机 UA 池思路（此处内联以便单文件直接运行）
DEFAULT_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

RETRIES = 3
BACKOFF = 1.5
TIMEOUT = 20
MIN_TEXT = 80        # 与 extract_articles.py 的阈值保持一致
REFERRER = "https://www.google.com/"


def fetch_one(url):
    """宽松重试抓取，返回 (data_bytes_or_None, err_or_None)。"""
    headers = {
        "User-Agent": random.choice(DEFAULT_UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "text/plain;q=0.8,*/*;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": REFERRER,
        "Connection": "keep-alive",
    }
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
            if data[:2] == b"\x1f\x8b":           # 服务器强塞了 gzip
                data = gzip.decompress(data)
            return data, None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            # 429/5xx 可重试；其余 4xx（401/403/404）重试无意义，直接放弃
            if e.code not in (429, 500, 502, 503, 504):
                return None, last_err
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as e:
            last_err = str(e)
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            time.sleep(BACKOFF * attempt + random.uniform(0, 1.0))
    return None, last_err


def _next_index(index):
    """返回下一个可用的三位编号（同时考虑 index 中已有 rawfile 与磁盘文件）。"""
    nums = []
    for e in index:
        rf = e.get("rawfile") or ""
        if rf[:3].isdigit():
            nums.append(int(rf[:3]))
    for f in RAW_DIR.glob("*.txt"):
        if f.stem.isdigit():
            nums.append(int(f.stem))
    return max(nums) if nums else 0


def main():
    if not INDEX.exists():
        print(f"✗ 找不到 {INDEX}，请先运行 tools/extract_articles.py（Round 1）生成 index.json。")
        return
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    # 目标：Round 1 失败（ok=False）且尚未进入 Round 2（round<2）
    targets = [e for e in index if (not e.get("ok")) and e.get("round", 0) < 2]
    if not targets:
        total_ok = sum(1 for e in index if e.get("ok"))
        print(f"Round 2: 没有需要重试的条目（累计 ok={total_ok}/{len(index)}）。")
        return

    nxt = _next_index(index)
    ok_new = 0
    for e in targets:
        url = e.get("url", "")
        title = (e.get("title") or "")[:40]
        print(f"  R2 [{title!r}] ...", end=" ", flush=True)
        data, err = fetch_one(url)
        if data is None:
            e["round"] = 2           # 标记已尝试 Round 2，交给 Playwright
            print(f"FAIL ({err})")
            time.sleep(1.0 + random.random())
            continue
        text = extract_text(data)
        if len(text) >= MIN_TEXT:
            nxt += 1
            fn = f"{nxt:03d}.txt"
            (RAW_DIR / fn).write_text(text, encoding="utf-8")
            e["rawfile"] = fn
            e["ok"] = True
            e["round"] = 2
            ok_new += 1
            print(f"OK ({len(text)} chars) -> {fn}")
        else:
            e["round"] = 2           # 正文过短，视为仍失败，交 Round 3
            print(f"短文本 ({len(text)} chars) -> 仍 FAIL")
        time.sleep(1.0 + random.random())

    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    total_ok = sum(1 for e in index if e.get("ok"))
    print(f"\nRound 2 完成：新增成功 {ok_new} 篇，累计 ok={total_ok}/{len(index)}，"
          f"仍失败 {len(index) - total_ok} 篇（交给 Round 3）。")
    print(f"回写 -> {INDEX.name}")


if __name__ == "__main__":
    main()
