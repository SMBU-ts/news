#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""互动数据获取模块（Python 标准库实现）。

从外部 API 获取新闻文章的互动指标（阅读量、评论数、点赞数等）。
当前支持的来源：
  - hn: Hacker News (Firebase API, 公开免费, 返回 score + descendants)

所有函数在网络不可达时静默返回空字典，不影响主构建流程。
"""

import json
import time
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

DEFAULT_TIMEOUT = 8          # 单条请求超时
DEFAULT_TOTAL_BUDGET = 60    # 整批获取的总时间预算（秒）
DEFAULT_MAX_ITEMS = 50       # 最多获取的文章数

# ============== Hacker News Firebase API ==============

HN_TOPSTORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


def _hn_fetch(path, timeout=DEFAULT_TIMEOUT):
    """获取 HN Firebase API 端点。失败返回 None。"""
    req = urllib.request.Request(path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError, json.JSONDecodeError):
        return None


def get_hn_engagement(timeout=DEFAULT_TIMEOUT, max_items=DEFAULT_MAX_ITEMS,
                      min_score=1, total_budget=DEFAULT_TOTAL_BUDGET):
    """批量获取 Hacker News 首页热门文章互动数据。

    流程:
      1. GET /v0/topstories.json -> [id, id, ...]
      2. 取前 max_items 个 ID
      3. 逐个获取文章详情（受 total_budget 总时间限制）
      4. 构建 {url -> {score, descendants}} 映射
      5. 失败返回空字典（静默降级）

    参数:
      timeout:        单次请求超时（秒）
      max_items:      最多检查的文章数（默认50）
      min_score:      低于此分的文章不收录（默认1）
      total_budget:   整批获取的总时间预算（秒，默认60）

    返回:
      dict: {url_str -> {"score": int, "comments": int}}
    """
    t_start = time.monotonic()
    ids = _hn_fetch(HN_TOPSTORIES, timeout)
    if not isinstance(ids, list) or not ids:
        return {}

    ids = ids[:max_items]
    result = {}

    for item_id in ids:
        # 检查总时间预算
        elapsed = time.monotonic() - t_start
        if elapsed >= total_budget:
            break

        # 动态调整单条超时（不超过剩余预算）
        remaining = total_budget - elapsed
        item_timeout = min(timeout, max(3, int(remaining)))

        item = _hn_fetch(HN_ITEM.format(item_id), item_timeout)
        if not isinstance(item, dict):
            continue

        score = item.get("score", 0)
        if score < min_score:
            continue

        url = item.get("url", "")
        descendants = item.get("descendants", 0)

        # 有外链 URL 的文章 -> 用 url 做键
        if url:
            result[url] = {"score": int(score), "comments": int(descendants)}

        # 同时用 HN 讨论页 URL 做键（部分 RSS 条目指向 HN 本身）
        hn_url = f"https://news.ycombinator.com/item?id={item_id}"
        result[hn_url] = {"score": int(score), "comments": int(descendants)}

    return result


# ============== 注册表 ==============

ENGAGEMENT_FETCHERS = {
    "hn": get_hn_engagement,
}


# ============== 统一入口 ==============

def fetch_for_source(engagement_type, timeout=DEFAULT_TIMEOUT, total_budget=DEFAULT_TOTAL_BUDGET):
    """根据源配置中的 engagement 类型获取互动数据。

    参数:
      engagement_type: 源类型键（"hn"、"none" 等）
      timeout:         单条请求超时（秒）
      total_budget:    整批获取的总时间预算（秒）

    返回:
      dict: {url -> {"score": int, "comments": int}}
      如果类型未知或获取失败，返回空字典。
    """
    fetcher = ENGAGEMENT_FETCHERS.get(engagement_type)
    if not fetcher:
        return {}
    try:
        return fetcher(timeout=timeout, total_budget=total_budget)
    except Exception:
        return {}
