#!/usr/bin/env python3
"""Playwright 批量抓取 france24 16 篇文章并保存正文（绕过 Cloudflare）。"""
import asyncio, re, json, time, html as hlib
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "summaries" / "raw" / "index.json"
RAW_DIR = ROOT / "summaries" / "raw"

# 16 篇 france24 URL（从 index.json 提取）
FAILED_FRANCE24 = [
    "https://www.france24.com/en/replay-outgoing-uk-pm-keir-starmer-gives-farewell-speech",
    "https://www.france24.com/en/middle-east/20260720-us-strikes-iran-ninth-consecutive-day-more-ships-targeted-strait-of-hormuz-kuwait-bahrain",
    "https://www.france24.com/en/andy-burnham-expected-to-focus-on-uk-s-cost-of-living-in-first-speech",
    "https://www.france24.com/en/europe/20260720-hungary-pm-magyar-proposes-chess-grandmaster-judit-polgar-for-president",
    "https://www.france24.com/en/uk-prepares-to-get-its-seventh-prime-minister-in-a-decade",
    "https://www.france24.com/en/absolute-joy-spilling-out-for-spain-s-new-golden-generation-of-football",
    "https://www.france24.com/en/the-winners-are-those-that-played-football-spanish-fans-celebrate-world-cup-win",
    "https://www.france24.com/en/europe/20260720-ukraine-drone-attack-on-moscow-region-wounds-10-people",
    "https://www.france24.com/en/tv-shows/business/20260720-andy-burnham-s-promise-to-deliver-tangible-improvements-to-britons-lives-put-to-the-test",
    "https://www.france24.com/en/asia-pacific/20260720-indian-police-baton-charge-cockroach-party-protesters-marching-to-parliament",
    "https://www.france24.com/en/middle-east/20260719-middle-east-live-us-launches-strikes-to-punish-iran-after-troops-killed",
    "https://www.france24.com/en/tv-shows/sports/20260720-spain-beat-argentina-to-win-world-cup-for-second-time",
    "https://www.france24.com/en/europe/20260720-last-chance-labour-s-andy-burnham-set-to-take-over-as-new-british-pm",
    "https://www.france24.com/en/video/20260720-world-cup-2026-argentine-coach-in-tears-after-defeat-to-spain",
    "https://www.france24.com/en/video/20260720-madrid-fans-react-to-spain-s-world-cup-win",
    "https://www.france24.com/en/world-cup-2026-spanish-fans-celebrate-their-team-s-victory-in-new-york",
]


def clean_text(text):
    """轻度清洗：去导航/页脚噪声但保留文章正文。"""
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text).strip()
    # 去掉常见的导航/页脚噪音行
    skip_prefixes = [
        'Your personal data', 'We and our partners', 'The processing of',
        'By clicking', 'You can change', 'Accept', 'Customize',
        'Manage my', 'France 24', 'Follow us', 'Share :',
        'Read more', 'Daily newsletter', 'On social networks',
        'The page you', 'All news', 'News feed', '©',
        'Accessibility', 'Terms of', 'Privacy', 'About', 'Contact',
        'Newsletters', 'Apps', 'Advertise', 'Copyright',
    ]
    lines = []
    for ln in text.split('\n'):
        ln = ln.strip()
        if len(ln) < 2:
            continue
        skip = False
        for pref in skip_prefixes:
            if ln.startswith(pref):
                skip = True
                break
        if not skip:
            lines.append(ln)
    return '\n'.join(lines)


async def fetch_one(browser, url):
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    page = await ctx.new_page()
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    """)
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        text = await page.inner_text("body")
        title = await page.title()
        body = clean_text(text)
        ok = len(body) > 300  # 过短说明被拦截
        return ok, body, title, len(text)
    except Exception as e:
        return False, str(e)[:100], "", 0
    finally:
        await ctx.close()


async def main():
    existing = max(int(f.stem) for f in RAW_DIR.glob("*.txt") if f.stem.isdigit())
    print(f"Existing max: {existing:03d}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
                  "--disable-dev-shm-usage"],
        )
        results = {}
        n = existing
        for i, url in enumerate(FAILED_FRANCE24, 1):
            print(f"[{i:2d}/16] {url.split('/')[-1][:50]}...", end=" ", flush=True)
            ok, body, title, raw_len = await fetch_one(browser, url)
            if ok:
                n += 1
                fn = f"{n:03d}.txt"
                (RAW_DIR / fn).write_text(body[:5000], encoding="utf-8")
                results[url] = {"file": fn, "len": len(body), "title": title[:50]}
                print(f"OK ({len(body)} chars) -> {fn}")
            else:
                print(f"FAIL: {body[:80]}")
            await asyncio.sleep(1.5)
        await browser.close()

    out = RAW_DIR / "playwright_mapping.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone: {len(results)}/16 bodies saved")


if __name__ == "__main__":
    asyncio.run(main())
