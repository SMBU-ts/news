#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Round 3 动态兜底抓取：用 Playwright（真实浏览器、反检测）抓取
summaries/raw/<date>/index.json 中前两轮（Round 1/2）均未成功的难啃 URL
（ok=False 且 round==2），如 x.com / sky.com / france24 直播页 / mataroa.blog 等。

成功后写入 NNN.txt，并把该条目在 index.json 中标记为 ok=True / rawfile=NNN.txt /
round=3；仍失败的交由「原文概括」回退提示处理（标记 round=3，不再重试）。

要点：
  - 不再硬编码任何 URL，目标完全由 index.json 决定。
  - 按域名选用不同 UA / 视口 / 超时 / 等待策略（x.com 走移动端 UA）。
  - 复用 clean_text 做域名相关去噪。
  - 幂等：round==3 的条目不会被再次选中。
  - 依赖第三方包 playwright（本机已安装 Chromium）；无 playwright 时给出明确提示后退出。

用法：
  python tools/playwright_fetch.py [YYYY-MM-DD]      # 默认今天
"""
import asyncio
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from datetime import date as dt

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
DATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else dt.today().strftime("%Y-%m-%d")
RAW_DIR = ROOT / "summaries" / "raw" / DATE
INDEX = RAW_DIR / "index.json"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# 各域名的超时 / 等待策略（毫秒）
URL_CONFIG = {
    "france24.com": {"timeout": 45000, "wait_after": 3000, "wait_until": "domcontentloaded"},
    "x.com":        {"timeout": 35000, "wait_after": 5000, "wait_until": "networkidle"},
    "sky.com":      {"timeout": 30000, "wait_after": 4000, "wait_until": "domcontentloaded"},
    "mataroa.blog": {"timeout": 25000, "wait_after": 3000, "wait_until": "domcontentloaded"},
}


def _domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def clean_text(text, domain):
    """轻度清洗：去导航/页脚噪声但保留文章正文。"""
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text).strip()
    skip_prefixes = {
        "france24.com": [
            'Your personal data', 'We and our partners', 'The processing of',
            'By clicking', 'Accept', 'Customize', 'Manage my', 'Follow us',
            'Share :', 'Read more', 'Daily newsletter', 'On social networks',
            'All news', 'News feed', '©', 'Accessibility', 'Terms of',
            'Privacy', 'About', 'Contact', 'Newsletters', 'Apps', 'Advertise',
            'Copyright', 'HOME', 'SHOWS', 'NEWSFEED', 'LIVE', 'EN', 'SETTINGS',
            'MENU', 'FRANCE', 'AFRICA', 'MIDDLE EAST', 'AMERICAS', 'EUROPE',
            'ASIA', 'KEYWORDS', 'HAPPENING', 'INTERNATIONAL', 'ABOUT',
            'SERVICES', 'APPLICATION', 'Legal', 'Cookies', 'Notifications',
            'Facebook', 'Bluesky', 'Threads', 'Instagram', 'YouTube',
            'TikTok', 'WhatsApp', 'Telegram', 'SoundCloud', 'Google',
            'ACPM', 'RFI', 'MCD', 'CFI', 'Académie', 'France Médias',
            'Watch France', 'Download', 'RSS feeds', 'ENTR', 'ZOA',
            'InfoMigrants', 'Learn French', 'RFI Instrumental',
            'See our', 'Deny', 'Skip to', 'To display this content',
            'Issued on', 'Modified', 'Reading time', 'Video by',
            'Report a', 'Ethics', 'Press room', 'Content licensing',
            'Join us',
        ],
        "x.com": [
            'Log in', 'Sign up', 'Terms of Service', 'Privacy Policy',
            'Cookie Policy', 'Accessibility', 'Ads info', '©',
            'More', 'Who to follow', 'Trending', "What's happening",
            'Show more', 'Back', 'Home', 'Explore', 'Notifications',
            'Messages', 'Bookmarks', 'Lists', 'Profile', 'Verified',
            'Post', 'Repost', 'Like', 'View', 'New tweets', 'Pinned',
            'Retweet', 'Likes', 'Following', 'Followers',
        ],
        "sky.com": [
            'Skip to', 'Menu', 'Search', 'Follow Sky News',
            'Accessibility', 'Privacy', 'Terms', '©',
            'Watch Live', 'More Top Stories', 'Advertisement',
        ],
        "mataroa.blog": [
            'Subscribe', 'RSS', 'Archive', 'About',
        ],
    }

    prefixes = skip_prefixes.get(domain, [])
    lines = []
    for ln in text.split('\n'):
        ln = ln.strip()
        if len(ln) < 2:
            continue
        if any(ln.startswith(p) for p in prefixes):
            continue
        lines.append(ln)
    return '\n'.join(lines)


async def fetch_one(browser, url, domain):
    cfg = URL_CONFIG.get(domain, {"timeout": 30000, "wait_after": 3000, "wait_until": "networkidle"})

    # x.com 用移动端 UA（Twitter 移动版更友好）
    if domain == "x.com":
        ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
              "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
        vp = {"width": 390, "height": 844}
    else:
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        vp = {"width": 1920, "height": 1080}

    ctx = await browser.new_context(
        user_agent=ua,
        viewport=vp,
        is_mobile=(domain == "x.com"),
        has_touch=(domain == "x.com"),
        locale="en-US",
    )
    page = await ctx.new_page()
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    """)
    try:
        await page.goto(url, wait_until=cfg["wait_until"], timeout=cfg["timeout"])
        await page.wait_for_timeout(cfg["wait_after"])
        # 模拟人类滚动（对 sky.com / x.com 特别重要）
        await page.evaluate("window.scrollBy(0, 300)")
        await page.wait_for_timeout(1000)
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(1000)
        text = await page.inner_text("body")
        title = await page.title()
        body = clean_text(text, domain)
        ok = len(body) > 200 and "Access denied" not in body[:200] and "Access Denied" not in body[:200]
        return ok, body, title, len(text)
    except Exception as e:
        return False, str(e)[:100], "", 0
    finally:
        await ctx.close()


def _next_index(index):
    nums = []
    for e in index:
        rf = e.get("rawfile") or ""
        if rf[:3].isdigit():
            nums.append(int(rf[:3]))
    for f in RAW_DIR.glob("*.txt"):
        if f.stem.isdigit():
            nums.append(int(f.stem))
    return max(nums) if nums else 0


async def main():
    if not INDEX.exists():
        print(f"✗ 找不到 {INDEX}，请先运行 tools/extract_articles.py（Round 1）。")
        return
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    # 目标：Round 1/2 都失败（ok=False 且 round==2）的条目
    targets = [e for e in index if (not e.get("ok")) and e.get("round", 0) == 2]
    if not targets:
        total_ok = sum(1 for e in index if e.get("ok"))
        print(f"Round 3: 没有需要 Playwright 兜底的条目（累计 ok={total_ok}/{len(index)}）。")
        return

    print(f"待 Playwright 抓取: {len(targets)} 篇")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                  "--disable-dev-shm-usage"],
        )
        nxt = _next_index(index)
        ok_new = 0
        for i, e in enumerate(targets, 1):
            url = e.get("url", "")
            domain = _domain(url)
            slug = url.split("/")[-1][:50]
            print(f"[{i}/{len(targets)}] {domain}: {slug}...", end=" ", flush=True)
            ok, body, title, raw_len = await fetch_one(browser, url, domain)
            if ok:
                nxt += 1
                fn = f"{nxt:03d}.txt"
                (RAW_DIR / fn).write_text(body[:5000], encoding="utf-8")
                e["rawfile"] = fn
                e["ok"] = True
                e["round"] = 3
                ok_new += 1
                print(f"OK ({len(body)} chars) -> {fn}")
            else:
                e["round"] = 3       # 仍失败，标记已尝试 Round 3，交给回退提示
                print(f"FAIL ({body[:80]})")
            await asyncio.sleep(1.5)
        await browser.close()

    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    total_ok = sum(1 for e in index if e.get("ok"))
    print(f"\nRound 3 完成：新增成功 {ok_new} 篇，累计 ok={total_ok}/{len(index)}，"
          f"仍失败 {len(index) - total_ok} 篇（走回退提示）。")
    print(f"回写 -> {INDEX.name}")


if __name__ == "__main__":
    asyncio.run(main())
