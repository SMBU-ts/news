#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享的中文「原文概括」生成模块（标准库实现，零第三方依赖）。

在构建脚本（build_rss.py / build_dashboard.py）渲染每篇文章卡片时调用
``summarize(url, title)``，返回一段约 100–200 字的中文摘要；若未配置 API
密钥、或抓取 / 提取 / 生成任一环节失败，则返回固定友好提示
``暂无法生成概括``。

配置（均通过环境变量，兼容 OpenAI 兼容端点）：
    SUMMARY_API_KEY / DEEPSEEK_API_KEY   大模型 API Key（二者取一即可）
    SUMMARY_API_BASE                     默认 https://api.deepseek.com/v1
    SUMMARY_MODEL                        默认 deepseek-chat

未设置 Key 时 ``ENABLED`` 为 False，``summarize`` 直接返回友好提示，
页面依旧能正常渲染出按钮与提示文案。
"""
import os
import re
import json
import html
import urllib.request
import urllib.error

# ---------------- 配置 ----------------
SUMMARY_FAIL = "暂无法生成概括"

API_KEY = (os.environ.get("SUMMARY_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
API_BASE = os.environ.get("SUMMARY_API_BASE", "https://api.deepseek.com/v1").strip().rstrip("/")
MODEL = os.environ.get("SUMMARY_MODEL", "deepseek-chat").strip()
ENABLED = bool(API_KEY)

# 预生成摘要缓存：url -> 摘要文本（由 summaries/<date>.json 载入，
# 例如用本仓库的 gen_summaries / 助手模型离线生成后提交，构建时优先使用，
# 无需联网或 API Key 也能展示真实摘要；重构建不丢失）。
_PRECOMP: dict = {}


def load_precomputed(path):
    """从 JSON 文件载入预生成摘要（url -> 摘要）。失败静默忽略。"""
    global _PRECOMP
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _PRECOMP.update({str(k): str(v) for k, v in data.items() if v})
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 20      # 单篇原文抓取超时（秒）
LLM_TIMEOUT = 30        # 单次大模型调用超时（秒）
MAX_TEXT = 5000         # 送入模型的正文长度上限（字符）

_BLOCK_RE = re.compile(
    r"<(script|style|noscript|head|svg|iframe|template)[^>]*>.*?</\1>",
    re.I | re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")


# ---------------- 抓取 ----------------
def fetch(url, timeout=FETCH_TIMEOUT):
    """抓取 URL 原始字节（含 gzip 自动解压）。失败抛异常由调用方处理。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if data[:2] == b"\x1f\x8b":           # 服务器强塞了 gzip
        import gzip
        data = gzip.decompress(data)
    return data


# ---------------- 正文提取（标准库启发式） ----------------
def extract_text(html_bytes):
    """从 HTML 字节中提取可读正文（去噪、折叠空白、截断）。"""
    if not html_bytes:
        return ""
    try:
        text = html_bytes.decode("utf-8", errors="ignore")
    except Exception:
        try:
            text = html_bytes.decode("latin-1", errors="ignore")
        except Exception:
            return ""
    # 去掉会污染正文的块
    text = _BLOCK_RE.sub(" ", text)
    # 去所有标签
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    # 顺手去掉极可能是孤立标点的行，降低噪声
    lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 1]
    text = "\n".join(lines)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
    return text


# ---------------- 大模型摘要 ----------------
def llm_summary(text, title):
    """调用 OpenAI 兼容端点生成中文摘要，任何失败返回空串。"""
    if not text or not API_KEY:
        return ""
    system = ("你是中文新闻编辑。请用简洁流畅的中文概括以下新闻的核心要点，"
             "长度约 100–200 字。只基于原文、不编造、不添加原文没有的信息；"
             "若原文信息不足，请直接说明无法概括。")
    user = f"标题：{title}\n\n正文：\n{text}"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API_BASE + "/chat/completions",
        data=data,
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
        },
        method="POST",
    )
    last_err = None
    for _ in range(2):          # 最多重试 1 次
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                resp = json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"]
            return (content or "").strip()
        except Exception as e:      # 网络/解析/结构异常一律视为失败
            last_err = e
            continue
    return ""


# ---------------- 统一入口 ----------------
def summarize(url, title):
    """对单篇原文生成中文摘要。

    返回：
        - 成功：摘要文本（约 100–200 字）
        - 失败/未启用：常量 ``SUMMARY_FAIL``（暂无法生成概括）
    """
    if not url:
        return SUMMARY_FAIL
    # 优先使用预生成摘要（助手模型离线生成并提交的 summaries/<date>.json），
    # 无需联网或 API Key 也能展示真实摘要，且重构建不丢失。
    if url in _PRECOMP:
        return _PRECOMP[url] or SUMMARY_FAIL
    if not ENABLED:
        return SUMMARY_FAIL
    try:
        raw = fetch(url)
        text = extract_text(raw)
        if len(text) < 50:           # 抓取到的正文过短（JS 渲染/付费墙等）
            return SUMMARY_FAIL
        summary = llm_summary(text, title or "")
        return summary if summary else SUMMARY_FAIL
    except Exception:
        return SUMMARY_FAIL
