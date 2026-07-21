#!/usr/bin/env python3
"""Playwright 反检测抓取剩余难啃 URL：x.com / sky.com / france24-live / mataroa.blog。

已包含反检测（隐藏 webdriver、模拟插件、真实 UA、人类滚动）。
用法：
    python tools/playwright_fetch.py
    python tools/playwright_fetch.py --only-remaining   # 只抓剩余 6 篇
"""
import asyncio, re, json, time, sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "summaries" / "raw"
SUMMARY_JSON = ROOT / "summaries" / "2026-07-20.json"

# ── 剩余 6 篇难啃 URL ──────────────────────────────────
REMAINING_URLS = [
    # x.com (3) — 本机不会被封 IP，沙箱封 x.com TCP
    "https://x.com/Alibaba_Qwen/status/2078754377473601787",
    "https://x.com/OpenBMB/status/2078839529591759025",
    "https://x.com/thsottiaux/status/2078697631019303273",
    # sky.com (1) — Akamai CDN，本机可能通过
    "https://news.sky.com/story/ebola-deaths-in-dr-congo-rise-to-930-amid-attacks-on-health-workers-13565139",
    # mataroa.blog (1) — 沙箱超时，本机大概率通
    "https://ludic.mataroa.blog/blog/ai-mania-is-eviscerating-global-decision-making",
    # france24 那篇直播页（之前超时，加长 timeout）
    "https://www.france24.com/en/middle-east/20260719-middle-east-live-us-launches-strikes-to-punish-iran-after-troops-killed",
]

# 各 URL 的超时和等待策略（秒）
URL_CONFIG = {
    "france24.com": {"timeout": 45000, "wait_after": 3000, "wait_until": "domcontentloaded"},
    "x.com":        {"timeout": 35000, "wait_after": 5000, "wait_until": "networkidle"},
    "sky.com":      {"timeout": 30000, "wait_after": 4000, "wait_until": "domcontentloaded"},
    "mataroa.blog": {"timeout": 25000, "wait_after": 3000, "wait_until": "domcontentloaded"},
}


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
            'More', 'Who to follow', 'Trending', 'What\'s happening',
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


async def main():
    only = "--only-remaining" in sys.argv
    existing = max(int(f.stem) for f in RAW_DIR.glob("*.txt") if f.stem.isdigit())

    # 跳过已在 JSON 中有摘要的 URL
    try:
        done_urls = set(json.loads(SUMMARY_JSON.read_text(encoding="utf-8")).keys())
    except Exception:
        done_urls = set()

    urls = [(u, u.split("/")[2].replace("www.", "")) for u in REMAINING_URLS]
    urls = [(u, d) for u, d in urls if u not in done_urls]

    if not urls:
        print("所有 URL 已有摘要，无需重复抓取。")
        return

    print(f"待抓取: {len(urls)} 篇 (已有 {len(done_urls)} 篇摘要)")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                  "--disable-dev-shm-usage"],
        )
        results = {}
        n = existing
        for i, (url, domain) in enumerate(urls, 1):
            slug = url.split("/")[-1][:50]
            print(f"[{i}/{len(urls)}] {domain}: {slug}...", end=" ", flush=True)
            ok, body, title, raw_len = await fetch_one(browser, url, domain)
            if ok:
                n += 1
                fn = f"{n:03d}.txt"
                (RAW_DIR / fn).write_text(body[:5000], encoding="utf-8")
                results[url] = {"file": fn, "len": len(body), "title": title[:60]}
                print(f"OK ({len(body)} chars) -> {fn}")
            else:
                print(f"FAIL ({body[:80]})")
            await asyncio.sleep(1.5)
        await browser.close()

    if results:
        out = RAW_DIR / "playwright_remaining.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone: {len(results)}/{len(urls)} new bodies saved")


if __name__ == "__main__":
    asyncio.run(main())
