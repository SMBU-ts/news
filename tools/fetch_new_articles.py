#!/usr/bin/env python3
"""抓取 13 篇宽带头破解成功的文章正文 -> summaries/raw/068-080.txt"""
import json, re, html as hlib, urllib.request, random, gzip, time
from pathlib import Path

UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

# 13 篇新可达 URL
reachable = [
    ("https://seekingalpha.com/news/4615192-the-great-bust-the-soaring-cost-of-living-the-american-dream?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "The great bust? The soaring cost of living the American Dream"),
    ("https://seekingalpha.com/news/4615191-kandis-subsidiary-china-battery-exchange-secures-18-station-procurement-order-from-contemporary-amperex-technology?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "Kandi subsidiary China Battery Exchange secures order from CATL"),
    ("https://seekingalpha.com/news/4615145-brookfield-cpp-investments-to-buy-lxp-trust-for-52b-cash?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "Brookfield, CPP Investments to buy LXP Trust"),
    ("https://seekingalpha.com/news/4615188-jersey-mikes-looks-to-raise-more-than-1b-as-its-ipo-roadshow-begins?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "Jersey Mike IPO roadshow begins"),
    ("https://seekingalpha.com/news/4615186-vertical-aerospace-adds-a-new-customer-for-its-valo-aircraft?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "Vertical Aerospace adds new customer for Valo aircraft"),
    ("https://www.marketwatch.com/story/scared-of-the-ai-trade-here-are-three-investment-themes-instead-says-goldman-sachs-e620a510?mod=mw_rss_topstories", "Scared of AI trade? Goldman suggests 3 themes instead"),
    ("https://seekingalpha.com/news/4615189-star-group-declares-01975-dividend?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "Star Group declares dividend"),
    ("https://seekingalpha.com/news/4615133-world-record-mile-run-puts-berkshires-brooks-brand-in-the-spotlight?utm_source=feed_news_all&utm_medium=referral&feed_item_type=news", "World record mile puts Berkshire Brooks brand in spotlight"),
    ("https://www.marketwatch.com/story/no-one-talks-about-faang-anymore-now-its-time-to-retire-magnificent-seven-as-well-citigroup-argues-ddf312c5?mod=mw_rss_topstories", "Time to retire Magnificent Seven as talking point"),
    ("https://www.marketwatch.com/story/my-husband-and-i-are-retired-our-financial-adviser-who-is-in-his-30s-called-us-you-guyses-is-that-unprofessional-ccddaa9f?mod=mw_rss_topstories", "Retired couple: adviser called them 'you guyses'"),
    ("https://www.marketwatch.com/story/is-an-opportunity-to-buy-chip-stocks-nearing-these-two-big-wall-street-banks-are-divided-ba1b03af?mod=mw_rss_topstories", "Is opportunity to buy chip stocks nearing?"),
    ("https://www.marketwatch.com/story/inflation-is-broadening-out-says-goldman-economist-44fa437f?mod=mw_rss_topstories", "Inflation broadening out says Goldman economist"),
    ("https://www.marketwatch.com/story/if-history-is-a-guide-theres-still-another-week-before-earnings-will-start-to-move-the-stock-market-52baccad?mod=mw_rss_topstories", "History says another week before earnings move market"),
]

BLOCK_RE = re.compile(r'<(script|style|noscript|head|svg|iframe|template)[^>]*>.*?</\1>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')
MAX_TEXT = 5000

def extract_text(html_bytes):
    if not html_bytes:
        return ""
    try:
        text = html_bytes.decode("utf-8", "ignore")
    except Exception:
        return ""
    text = BLOCK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = hlib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 1]
    return "\n".join(lines)[:MAX_TEXT]

raw_dir = Path(__file__).resolve().parent.parent / "summaries" / "raw"
existing = max(int(f.stem) for f in raw_dir.glob("*.txt") if f.stem.isdigit())
print(f"Existing max: {existing:03d}")

mapping = {}
for i, (url, short_title) in enumerate(reachable):
    n = existing + i + 1
    fn = f"{n:03d}.txt"
    ua = random.choice(UAS)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
        text = extract_text(data)
        (raw_dir / fn).write_text(text, encoding="utf-8")
        mapping[url] = {"file": fn, "len": len(text), "title": short_title}
        print(f"  {fn}: {short_title[:45]} -> {len(text)} chars")
    except Exception as e:
        print(f"  FAIL {short_title[:30]}: {e}")
    time.sleep(1.5 + random.random())

out = raw_dir / "new_mapping.json"
out.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nDone: {len(mapping)} bodies saved, mapping -> {out.name}")
