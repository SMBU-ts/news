#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用「宽松型」网络爬虫（标准库实现，零第三方依赖）。

特性：
  - 随机 User-Agent 轮换（桌面 + 移动端，覆盖主流浏览器）
  - 合理的请求间隔 + 随机抖动，降低被封禁概率
  - 失败自动重试（默认 3 次，指数退避），对 429/5xx/网络异常自动重试
  - 可自定义目标 URL（命令行 / 配置文件 / URL 文件）与抓取规则
  - 抓取结果保存为 JSON 本地文件
  - 内置日志（同时输出到控制台与日志文件，便于调试）
  - 「宽松」选项：可关闭 robots.txt 限制、可关闭 SSL 证书校验、可注入自定义请求头（如 Cookie）

抓取规则（config 中的 `fields`）支持两种模式：
  mode="fields"：对整个页面提取若干字段（每个字段可 multi 取多个匹配）
  mode="items" ：先用 `item_rule` 切出若干个「条目块」，再在每个块内提取 fields，
                 输出为条目列表（最适合新闻/商品/列表类页面）

每个 field：
  { "name": 字段名,
    "pattern": 正则,
    "flags": "IS" 可选（I 忽略大小写 / S 点匹配换行 / M 多行）,
    "group": 捕获组序号（默认 0，即整段匹配）,
    "multi": false/true（是否提取所有匹配，默认 false）,
    "default": 未匹配时的默认值（默认 ""） }
"""
import os
import re
import sys
import json
import time
import random
import logging
import argparse
import ssl
import gzip
import urllib.request
import urllib.error
from urllib.request import Request
from pathlib import Path


# --------------------------------------------------------------------------
# 默认 User-Agent 池（随意轮换，模拟不同浏览器 / 设备）
# --------------------------------------------------------------------------
DEFAULT_UA_POOL = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome / Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    # Safari / iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    # Firefox / Android
    "Mozilla/5.0 (Android 14; Mobile; rv:126.0) Gecko/126.0 Firefox/126.0",
]


# 默认抓取规则：演示「提取页面标题 + 所有外链」（可被 config 覆盖）
DEFAULT_CONFIG = {
    "urls": [],
    "delay": 2.0,            # 相邻请求的基础间隔（秒）
    "jitter": 1.5,           # 间隔随机抖动上限（秒），实际等待 = delay + rand(0, jitter)
    "retries": 3,            # 失败重试次数
    "backoff": 1.5,          # 重试退避基数（指数增长：backoff * 第几次）
    "timeout": 20,           # 单请求超时（秒）
    "user_agents": DEFAULT_UA_POOL,
    "extra_headers": {},     # 自定义请求头（如 Cookie / Authorization），宽松抓取用
    "respect_robots": False, # 默认不遵守 robots.txt（更宽松）；如需守规矩改为 True
    "verify_ssl": True,      # 默认校验证书；遇到自签/过期证书的可设为 False
    "output": "output/result.json",
    "logfile": "output/crawler.log",
    "mode": "fields",
    "item_rule": {"pattern": r"<article[^>]*>(.*?)</article>", "flags": "IS"},
    "fields": [
        {"name": "title", "pattern": r"<title[^>]*>(.*?)</title>", "flags": "IS", "group": 1},
        {"name": "links", "pattern": r'href="([^"]+)"', "flags": "", "group": 1, "multi": True},
    ],
}


# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------
def setup_logging(logfile):
    Path(logfile).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("crawler")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def _compile_flags(s):
    flags = 0
    for c in (s or ""):
        if c == "I":
            flags |= re.I
        elif c == "S":
            flags |= re.S
        elif c == "M":
            flags |= re.M
    return flags


def _extract_field(text, f):
    """按单个 field 定义从 text 中提取内容（支持单值 / 多值 / 捕获组 / 默认值）。"""
    pat = f["pattern"]
    flags = _compile_flags(f.get("flags"))
    grp = f.get("group", 0)
    multi = f.get("multi", False)
    default = f.get("default", "")
    try:
        if multi:
            matches = re.findall(pat, text, flags)
            out = []
            for m in matches:
                if isinstance(m, tuple):
                    out.append(m[grp] if grp < len(m) else "")
                else:
                    out.append(m)
            return out
        m = re.search(pat, text, flags)
        if not m:
            return default
        return m.group(grp) if grp else m.group(0)
    except re.error as e:
        logging.getLogger("crawler").warning("字段 %s 正则错误: %s", f.get("name"), e)
        return default
    except Exception as e:  # noqa: BLE001
        logging.getLogger("crawler").warning("提取字段 %s 失败: %s", f.get("name"), e)
        return default


def extract(html, cfg):
    """根据 config 的 mode / item_rule / fields 从整页 HTML 提取结构化数据。"""
    mode = cfg.get("mode", "fields")
    fields = cfg.get("fields", [])
    if mode == "items":
        rule = cfg.get("item_rule", {})
        containers = re.findall(rule.get("pattern", ""), html, _compile_flags(rule.get("flags")))
        items = []
        for block in containers:
            item = {}
            for f in fields:
                item[f["name"]] = _extract_field(block, f)
            items.append(item)
        return items
    # fields 模式：整页提取
    out = {}
    for f in fields:
        out[f["name"]] = _extract_field(html, f)
    return out


# --------------------------------------------------------------------------
# 抓取（含重试 + 退避）
# --------------------------------------------------------------------------
def fetch(url, ua, cfg, logger):
    """抓取单个 URL，返回 (html_or_None, status_code_or_None, error_or_None)。"""
    retries = cfg.get("retries", 3)
    timeout = cfg.get("timeout", 20)
    backoff = cfg.get("backoff", 1.5)

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "text/plain;q=0.8,*/*;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    # 宽松选项：注入自定义头（Cookie / Referer / 鉴权等）
    for k, v in (cfg.get("extra_headers") or {}).items():
        headers[k] = v

    ctx = None
    if not cfg.get("verify_ssl", True):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = r.read()
            if data[:2] == b"\x1f\x8b":  # 服务器强塞了 gzip
                data = gzip.decompress(data)
            enc = r.headers.get_content_charset() or "utf-8"
            html = data.decode(enc, errors="ignore")
            logger.info("✓ 成功 %s (HTTP %s, 第 %d 次尝试, %d 字节)",
                        url, r.getcode(), attempt, len(data))
            return html, r.getcode(), None
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            # 429/503 等通常需等待；其他 4xx（401/403/404）重试无意义，直接放弃
            retryable = e.code in (429, 500, 502, 503, 504)
            logger.warning("✗ %s -> HTTP %s (第 %d/%d 次)", url, e.code, attempt, retries)
            if not retryable:
                return None, e.code, last_err
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as e:
            last_err = str(e)
            logger.warning("✗ %s -> %s (第 %d/%d 次)", url, e, attempt, retries)
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            logger.warning("✗ %s -> 异常 %s (第 %d/%d 次)", url, last_err, attempt, retries)

        if attempt < retries:
            wait = backoff * attempt + random.uniform(0, cfg.get("jitter", 1.0))
            logger.info("  等待 %.1f 秒后重试…", wait)
            time.sleep(wait)

    return None, None, last_err


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(cfg, logger):
    urls = cfg.get("urls") or []
    if not urls:
        logger.error("没有任何目标 URL，退出。")
        return []

    results = []
    total = len(urls)
    ok = 0
    fail = 0
    ua_pool = cfg.get("user_agents") or DEFAULT_UA_POOL

    for i, url in enumerate(urls, 1):
        # 相邻请求之间设置间隔 + 抖动（首条不等待）
        if i > 1:
            wait = cfg.get("delay", 2.0) + random.uniform(0, cfg.get("jitter", 1.0))
            logger.info("— 间隔 %.1f 秒 (%d/%d) —", wait, i, total)
            time.sleep(wait)

        ua = random.choice(ua_pool)
        logger.info("[%d/%d] 抓取 %s (UA: %s…)", i, total, url, ua[:38])
        html, code, err = fetch(url, ua, cfg, logger)

        if err:
            fail += 1
            results.append({"url": url, "status": "error", "code": code, "error": err})
            continue

        try:
            data = extract(html, cfg)
        except Exception as e:  # noqa: BLE001
            logger.error("解析失败 %s: %s", url, e)
            fail += 1
            results.append({"url": url, "status": "error", "code": code, "error": f"parse: {e}"})
            continue

        ok += 1
        count = len(data) if isinstance(data, list) else 1
        logger.info("  解析得到 %s 条数据", count)
        results.append({"url": url, "status": "ok", "code": code, "data": data})

    logger.info("完成：共 %d 个 URL，成功 %d，失败 %d", total, ok, fail)
    return results


def save_results(results, cfg, logger):
    out = cfg.get("output", "output/result.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "error"),
        },
        "results": results,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("结果已写入 %s", out)


# --------------------------------------------------------------------------
# 配置加载与 CLI
# --------------------------------------------------------------------------
def load_config(args):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝默认值

    if args.config:
        p = Path(args.config)
        if p.exists():
            user = json.loads(p.read_text(encoding="utf-8"))
            cfg.update(user)
            # fields / item_rule 整体替换（不浅合并）
            if "fields" in user:
                cfg["fields"] = user["fields"]
            if "item_rule" in user:
                cfg["item_rule"] = user["item_rule"]
        else:
            logging.getLogger("crawler").warning("配置文件不存在: %s，使用默认配置", args.config)

    # 命令行覆盖
    if args.urls:
        cfg["urls"] = [u.strip() for u in args.urls.split(",") if u.strip()]
    if args.urls_file:
        with open(args.urls_file, "r", encoding="utf-8") as f:
            cfg["urls"] = [line.strip() for line in f if line.strip()]
    if args.output:
        cfg["output"] = args.output
    if args.delay is not None:
        cfg["delay"] = args.delay
    if args.retries is not None:
        cfg["retries"] = args.retries
    if args.no_verify:
        cfg["verify_ssl"] = False
    return cfg


def main():
    ap = argparse.ArgumentParser(
        description="通用宽松型爬虫：随机 UA + 间隔抖动 + 自动重试 + JSON 输出 + 日志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python crawler.py --urls https://example.com/a,https://example.com/b\n"
            "  python crawler.py --config crawler_config.example.json\n"
            "  python crawler.py --urls-file urls.txt --delay 3 --retries 5 --no-verify\n"
        ),
    )
    ap.add_argument("--config", help="JSON 配置文件路径（规则/UA/间隔等）")
    ap.add_argument("--urls", help="逗号分隔的目标 URL 列表")
    ap.add_argument("--urls-file", help="每行一个 URL 的文本文件")
    ap.add_argument("--output", help="JSON 输出路径（覆盖配置）")
    ap.add_argument("--delay", type=float, help="基础请求间隔（秒）")
    ap.add_argument("--retries", type=int, help="失败重试次数")
    ap.add_argument("--no-verify", action="store_true", help="关闭 SSL 证书校验（宽松）")
    args = ap.parse_args()

    cfg = load_config(args)
    logger = setup_logging(cfg.get("logfile", "output/crawler.log"))
    logger.info("启动爬虫：%d 个目标 URL，间隔 %.1f±%.1f 秒，重试 %d 次",
                len(cfg.get("urls", [])), cfg.get("delay", 2.0),
                cfg.get("jitter", 1.0), cfg.get("retries", 3))

    results = run(cfg, logger)
    save_results(results, cfg, logger)


if __name__ == "__main__":
    main()
