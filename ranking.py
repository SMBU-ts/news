#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可配置热度排名引擎（Python 标准库实现）。

提供基于多因素的新闻文章评分与排名：

  SCORE = w_e * S_e + w_r * S_r + w_a * S_a + w_i * S_i + w_c * S_c

因子说明:
  S_e  互动数据评分   HN score + comments，对数归一化
  S_r  时效性评分     指数衰减 exp(-age / tau)
  S_a  信源权威评分   源 weight 在同分类内 min-max 归一化
  S_i  标题信息量评分 长度 + 数字密度 + 专有名词
  S_c  跨源报道加成   Jaccard 关键词相似度检测多源报道

所有权重和参数通过 feeds.yaml 的 _ranking 节配置。
"""

import math
import re
import datetime

# ============== 常量 ==============

# 停用词（用于跨源检测的关键词提取）
_STOP_WORDS = {
    # 中文功能词
    "的", "了", "在", "是", "我", "你", "他", "她", "和", "与", "或", "也",
    "都", "就", "这", "那", "有", "为", "以", "及", "等", "但", "而", "从",
    "被", "把", "向", "对", "让", "给", "到", "中", "上", "下", "后", "前",
    # 英文常见词
    "and", "the", "to", "of", "in", "a", "for", "is", "on", "that", "with",
    "this", "as", "it", "at", "by", "from", "has", "been", "its", "an",
    "was", "are", "will", "can", "be", "have", "not", "but", "or", "if",
    "so", "do", "did", "does", "how", "what", "when", "where", "who", "why",
}

# 标题信息量参数
_TITLE_MIN_LEN = 15
_TITLE_MAX_LEN = 80
_TITLE_OPT_LEN = 50

# 跨源检测参数
_CROSS_JACCARD_THRESHOLD = 0.25
_CROSS_SOURCE_CAP = 3.0

# 默认权重
_DEFAULT_WEIGHTS = {
    "engagement": 0.35,
    "recency": 0.25,
    "authority": 0.20,
    "informativeness": 0.10,
    "cross_source": 0.10,
}

# 默认排名配置
_DEFAULT_CONFIG = {
    "method": "top_n",
    "top_n": 20,
    "percentile": None,
    "threshold": None,
    "weights": dict(_DEFAULT_WEIGHTS),
    "recency_half_life": 6.0,
    "engagement_poll_timeout": 15,
}


# ============== 配置解析 ==============

def resolve_ranking_config(cat, raw_config):
    """解析分类的排名配置。

    参数:
      cat:        分类名（如 "tech"）
      raw_config: feeds.yaml 中 _ranking 字典的内容，或 None

    返回:
      dict: 包含 method, top_n, percentile, threshold, weights,
            recency_half_life, engagement_poll_timeout
      None: 如果 raw_config 为 None（表示不使用排名系统）
    """
    if not raw_config or not isinstance(raw_config, dict):
        return None

    # 从 defaults 开始
    defaults = raw_config.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}

    # 合并分类级覆盖
    cat_override = raw_config.get(cat, {})
    if not isinstance(cat_override, dict):
        cat_override = {}

    # 合并配置：defaults <- cat_override
    merged = dict(_DEFAULT_CONFIG)
    for key in ("method", "top_n", "percentile", "threshold",
                "recency_half_life", "engagement_poll_timeout"):
        if key in defaults:
            merged[key] = defaults[key]
        if key in cat_override:
            merged[key] = cat_override[key]

    # 合并权重：default_weights <- defaults.weights <- cat_override.weights
    weights = dict(_DEFAULT_WEIGHTS)
    if "weights" in defaults and isinstance(defaults["weights"], dict):
        weights.update(defaults["weights"])
    if "weights" in cat_override and isinstance(cat_override["weights"], dict):
        weights.update(cat_override["weights"])
    merged["weights"] = weights

    # 归一化权重（确保总和为 1.0）
    total = sum(weights.values())
    if total > 0:
        merged["weights"] = {k: v / total for k, v in weights.items()}
    else:
        # 全部为零 -> 回退默认
        merged["weights"] = dict(_DEFAULT_WEIGHTS)

    return merged


# ============== 评分因子 ==============

def s_engagement(link, engagement_map, default=0.3):
    """互动数据归一化评分。

    策略:
      1. 精确匹配文章 URL
      2. 如有数据: score = log(1 + total) / log(1 + max_in_batch)
         total = score + comments
      3. 无数据: 返回 default（0.3 = 中等基础分，避免无数据源被完全压制）

    返回: float in [0.0, 1.0]
    """
    if not engagement_map or not link:
        return default

    link_stripped = link.strip()
    data = engagement_map.get(link_stripped)
    if not data:
        return default

    raw_total = data.get("score", 0) + data.get("comments", 0)
    if raw_total <= 0:
        return 0.0

    # 找 batch 中的最大值用于归一化
    max_total = max(
        (d.get("score", 0) + d.get("comments", 0))
        for d in engagement_map.values()
    )
    if max_total <= 0:
        return 0.0

    return min(1.0, math.log(1 + raw_total) / math.log(1 + max_total))


def s_recency(pub_date, now, half_life_hours):
    """时效性评分（指数衰减）。

    S_r = exp(-age_hours / tau)
    tau = half_life_hours / ln(2)

    示例（half_life=6h）:
      0h 前: S_r = 1.0
      6h 前: S_r = 0.5
     24h 前: S_r = 0.0625

    返回: float in [0.0, 1.0]
    """
    if not pub_date:
        return 0.5  # 无日期 -> 中等值

    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    age_hours = (now - pub_date).total_seconds() / 3600.0
    if age_hours < 0:
        age_hours = 0  # 未来日期 -> 满分

    tau = half_life_hours / math.log(2) if half_life_hours > 0 else 999999
    return max(0.0, min(1.0, math.exp(-age_hours / tau)))


def s_authority(source, source_weights):
    """信源权威度评分。

    将源 weight 在同分类的所有源中做 min-max 归一化。
    如果所有 weight 相等，返回 1.0（均等）。

    返回: float in [0.0, 1.0]
    """
    if not source_weights:
        return 1.0

    weights = list(source_weights.values())
    w = source_weights.get(source, 1.0)

    w_min = min(weights)
    w_max = max(weights)

    if w_max == w_min:
        return 1.0  # 所有权重相等

    return (w - w_min) / (w_max - w_min)


def s_informativeness(title):
    """标题信息量评分。

    基于以下因素（纯 stdlib）:
      1. 标题长度（太短=噪声，40-80字符最佳）
      2. 含数字量（量化信息=更具体）
      3. 英文大写词/专有名词计数

    各因素等权平均后映射到 [0, 1]。

    返回: float in [0.0, 1.0]
    """
    if not title:
        return 0.0

    title = title.strip()
    length = len(title)

    # 因子1: 长度评分（钟形曲线，最优在 _TITLE_OPT_LEN 附近）
    if length < _TITLE_MIN_LEN:
        f_len = length / _TITLE_MIN_LEN * 0.5
    elif length > _TITLE_MAX_LEN:
        f_len = max(0.3, 1.0 - (length - _TITLE_MAX_LEN) / 80.0)
    else:
        # 在 [_TITLE_MIN_LEN, _TITLE_MAX_LEN] 范围内，最优值附近为1.0
        if length <= _TITLE_OPT_LEN:
            f_len = 0.5 + 0.5 * (length - _TITLE_MIN_LEN) / max(1, _TITLE_OPT_LEN - _TITLE_MIN_LEN)
        else:
            f_len = 0.5 + 0.5 * (_TITLE_MAX_LEN - length) / max(1, _TITLE_MAX_LEN - _TITLE_OPT_LEN)

    # 因子2: 数字密度（含数字=更具体的信息）
    digits = sum(1 for c in title if c.isdigit())
    f_digits = min(1.0, digits / 5.0)

    # 因子3: 英文大写词计数（专有名词/品牌名/缩写）
    # 提取首字母大写的英文词
    cap_words = re.findall(r'\b[A-Z][a-zA-Z]{2,}\b', title)
    f_caps = min(1.0, len(cap_words) / 3.0)

    return (f_len + f_digits + f_caps) / 3.0


def s_cross_source(idx, articles):
    """跨源报道加成评分。

    当多个来源报道同一事件时，该事件重要性更高。
    使用 Jaccard 关键词相似度检测。

    策略:
      1. 对每篇文章标题提取关键词
      2. 计算该文章与所有其他文章的 Jaccard 相似度
      3. 统计相似度超过阈值的来源数
      4. S_c = min(n_similar / cap, 1.0)

    返回: float in [0.0, 1.0]
    """
    if len(articles) <= 1:
        return 0.0

    target = articles[idx]
    target_source = target.get("source", "")
    target_tokens = _tokenize(target.get("title", ""))

    if not target_tokens:
        return 0.0

    similar_count = 0
    for i, other in enumerate(articles):
        if i == idx:
            continue
        other_source = other.get("source", "")
        if other_source == target_source:
            continue  # 只算跨源

        other_tokens = _tokenize(other.get("title", ""))
        if not other_tokens:
            continue

        sim = _jaccard(target_tokens, other_tokens)
        if sim >= _CROSS_JACCARD_THRESHOLD:
            similar_count += 1

    if similar_count == 0:
        return 0.0

    return min(1.0, similar_count / _CROSS_SOURCE_CAP)


# ============== 辅助函数 ==============

def _tokenize(title):
    """提取标题中的关键词（去停用词后取词）。

    对中文标题：按字符分词，取2字以上的连续中文片段。
    对英文标题：按空格分词，去停用词，取3字母以上的词。

    返回: set of str
    """
    if not title:
        return set()

    tokens = set()

    # 英文词（3+字母）
    for word in re.findall(r'[a-zA-Z]{3,}', title):
        word_lower = word.lower()
        if word_lower not in _STOP_WORDS:
            tokens.add(word_lower)

    # 中文连续片段（2+字符）
    for seg in re.findall(r'[\u4e00-\u9fff]{2,}', title):
        # 取前4个字符作为关键词（粗粒度）
        if len(seg) >= 2:
            tokens.add(seg[:min(4, len(seg))])

    return tokens


def _jaccard(a, b):
    """计算 Jaccard 相似度。

    参数:
      a, b: set 或 list

    返回: float in [0.0, 1.0]
    """
    a_set = set(a)
    b_set = set(b)
    if not a_set or not b_set:
        return 0.0
    intersection = a_set & b_set
    union = a_set | b_set
    return len(intersection) / len(union)


# ============== 核心评分 ==============

def score_articles(articles, engagement_map, config, source_weights, now):
    """计算文章列表的热度评分。

    参数:
      articles:        [{title, link, summary, source, dt}, ...]
      engagement_map:  {url -> {score, comments}}
      config:          resolve_ranking_config() 的返回值
      source_weights:  {source_name -> weight}
      now:             当前时间（含时区）

    返回:
      [score, score, ...] 并行列表，每个 score in [0, 100]
    """
    weights = config.get("weights", _DEFAULT_WEIGHTS)
    half_life = config.get("recency_half_life", 6.0)

    scores = []
    for idx, article in enumerate(articles):
        # 各因子评分（均 in [0, 1]）
        se = s_engagement(article.get("link", ""), engagement_map)
        sr = s_recency(article.get("dt"), now, half_life)
        sa = s_authority(article.get("source", ""), source_weights)
        si = s_informativeness(article.get("title", ""))
        sc = s_cross_source(idx, articles)

        # 加权求和 -> [0, 100]
        total = (
            weights.get("engagement", 0) * se +
            weights.get("recency", 0) * sr +
            weights.get("authority", 0) * sa +
            weights.get("informativeness", 0) * si +
            weights.get("cross_source", 0) * sc
        )

        scores.append(round(total * 100, 2))

    return scores


# ============== 排名筛选 ==============

def apply_ranking(articles, scores, config):
    """根据配置的方法筛选文章。

    参数:
      articles: 去重后的文章列表
      scores:   对应的评分列表（相同顺序）
      config:   {method, top_n, percentile, threshold}

    返回:
      list[dict]: 按分数降序排列的筛选后文章列表
    """
    if not articles:
        return []

    # 按分数降序排列
    paired = sorted(zip(scores, articles), key=lambda x: x[0], reverse=True)

    method = config.get("method", "top_n")

    if method == "threshold":
        threshold = config.get("threshold", 0)
        result = [art for score, art in paired if score >= threshold]
        # 至少保留 5 条（避免过度过滤）
        if len(result) < 5 and len(paired) >= 5:
            result = [art for _, art in paired[:5]]
        elif len(result) < 5:
            result = [art for _, art in paired]
        return result

    elif method == "percentile":
        percentile = config.get("percentile")
        if percentile is None or percentile <= 0:
            percentile = 60
        # 保留前 percentile% 的条目（向上取整，至少 5 条）
        keep = max(5, math.ceil(len(paired) * percentile / 100))
        keep = min(keep, len(paired))
        return [art for _, art in paired[:keep]]

    else:  # top_n (默认)
        top_n = config.get("top_n", 20)
        keep = min(top_n, len(paired))
        return [art for _, art in paired[:keep]]
