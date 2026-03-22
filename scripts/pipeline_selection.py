from __future__ import annotations

import datetime as dt

from pipeline_common import feed_items, now_cn, parse_date

DEFAULT_MIN_SELECTION_SCORE = 70
DEFAULT_MAX_SKIP_REPORT = 8
DEFAULT_MAX_BRIEF_ITEMS = 5
LOW_INFO_DESC_CHARS = 120
SLOW_FEED_INTERVAL_DAYS = 5

SOURCE_QUALITY_HINTS = [
    ("dwarkesh", 30, "高质量深访"),
    ("latent", 29, "工程向深度播客"),
    ("cognitive revolution", 28, "AI 深度讨论"),
    ("lex fridman", 26, "长访谈信息密度高"),
    ("designer notes", 26, "游戏研发一手访谈"),
    ("deconstructor", 26, "游戏行业深度分析"),
    ("eggplant", 22, "游戏设计访谈"),
    ("aias", 22, "游戏制作相关访谈"),
    ("hard fork", 18, "资讯+观点型节目"),
    ("gdc", 16, "官方资讯流"),
]

IMPORTANT_KEYWORDS = [
    "openai", "anthropic", "gemini", "nvidia", "unity", "unreal", "steam", "xbox", "playstation",
    "lawsuit", "regulation", "security", "vulnerability", "post-mortem", "benchmark", "release",
    "重大", "监管", "漏洞", "复盘", "崩溃", "事故", "发布",
]

MARKETING_KEYWORDS = [
    "sponsor", "sponsored", "promo", "promotion", "webinar", "register", "subscribe", "discount",
    "join us", "coming soon", "newsletter", "立即购买", "限时", "优惠", "报名", "直播预告",
]

ACTIONABLE_KEYWORDS = [
    "how", "guide", "case study", "post-mortem", "benchmark", "profiling", "architecture",
    "教程", "实践", "方法", "复盘", "架构", "性能", "排障",
]

NOVELTY_KEYWORDS = [
    "2026", "new", "launch", "release", "update", "paper", "open-source", "breaking",
    "发布", "开源", "更新", "首发", "新", "论文",
]


def contains_any(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


def source_quality_score(source_name: str) -> tuple[int, str]:
    n = (source_name or "").lower()
    for key, score, reason in SOURCE_QUALITY_HINTS:
        if key in n:
            return score, reason
    return 16, "常规来源"


def is_slow_source(source_cfg: dict, items: list[dict]) -> bool:
    dates: list[dt.datetime] = []
    for it in items:
        d = parse_date(it.get("published", ""))
        if d:
            dates.append(d)

    if len(dates) < 2:
        return False

    dates.sort(reverse=True)
    gaps: list[float] = []
    for i in range(len(dates) - 1):
        delta = (dates[i] - dates[i + 1]).total_seconds() / 86400.0
        if delta > 0:
            gaps.append(delta)

    if not gaps:
        return False

    avg_gap = sum(gaps) / len(gaps)
    return avg_gap >= SLOW_FEED_INTERVAL_DAYS


def evaluate_candidate(item: dict, min_selection_score: int) -> dict:
    title = (item.get("title") or "").strip()
    desc = (item.get("description") or "").strip()
    source = (item.get("source") or "").strip()
    source_type = (item.get("source_type") or "").strip().lower()
    text = f"{title} {desc}".lower()

    score = 0
    reasons: list[str] = []
    skip_reasons: list[str] = []

    src_score, src_reason = source_quality_score(source)
    score += src_score
    reasons.append(f"来源质量 {src_score}/30（{src_reason}）")

    dlen = len(desc)
    if dlen >= 600:
        density = 25
    elif dlen >= 350:
        density = 20
    elif dlen >= 180:
        density = 15
    elif dlen >= 90:
        density = 9
    else:
        density = 3
    score += density
    reasons.append(f"信息密度 {density}/25")

    if contains_any(text, NOVELTY_KEYWORDS):
        novelty = 14
    else:
        novelty = 8
    score += novelty
    reasons.append(f"新颖度 {novelty}/20")

    if contains_any(text, ACTIONABLE_KEYWORDS):
        actionable = 12
    else:
        actionable = 6
    score += actionable
    reasons.append(f"可执行性 {actionable}/15")

    has_marketing_signal = contains_any(text, MARKETING_KEYWORDS)
    if has_marketing_signal:
        score -= 20
        skip_reasons.append("营销/宣传信号明显")

    important_signal = contains_any(text, IMPORTANT_KEYWORDS)
    if important_signal:
        score += 8
        reasons.append("重要性加分 +8")

    if dlen < 60:
        score -= 12
        skip_reasons.append("描述信息过少")
    elif dlen < LOW_INFO_DESC_CHARS:
        score -= 6
        skip_reasons.append("描述信息偏少")

    important_but_low_info = important_signal and dlen < LOW_INFO_DESC_CHARS
    consult_like = source_type in {"official-content", "news", "newsletter"}
    if consult_like and dlen < LOW_INFO_DESC_CHARS and not important_signal:
        skip_reasons.append("资讯流且信息量不足")

    if item.get("_slow_source"):
        score = min(100, score + 12)
        reasons.append("低频源优先 +12")

    score = max(0, min(100, score))

    if has_marketing_signal:
        status = "rejected"
    elif important_but_low_info:
        status = "brief_merge"
    elif item.get("_slow_source"):
        status = "selected"
    elif score >= min_selection_score and not (consult_like and dlen < LOW_INFO_DESC_CHARS):
        status = "selected"
    else:
        status = "rejected"

    why = "；".join(reasons[:4])
    if status == "rejected":
        why_not = "；".join(skip_reasons) if skip_reasons else f"总分 {score} 低于阈值 {min_selection_score}"
    elif status == "brief_merge":
        why_not = "重要但信息不足，合并到快讯" if not skip_reasons else "；".join(skip_reasons)
    else:
        why_not = ""

    item["_score"] = score
    item["_status"] = status
    item["_why"] = why
    item["_why_not"] = why_not
    item["_important"] = important_signal
    item["_consult_like"] = consult_like
    return item


def select_with_diversity(candidates: list[dict], max_posts: int) -> tuple[list[dict], list[dict]]:
    ordered = sorted(candidates, key=lambda x: (x.get("_score", 0), x.get("_ts", 0)), reverse=True)
    selected: list[dict] = []
    skipped_due_quota: list[dict] = []
    used_sources: set[str] = set()

    for it in ordered:
        if it.get("_status") != "selected":
            continue
        src = it.get("source", "")
        if src in used_sources:
            continue
        selected.append(it)
        used_sources.add(src)
        if len(selected) >= max_posts:
            break

    if len(selected) < max_posts:
        selected_urls = {x.get("url") for x in selected}
        for it in ordered:
            if it.get("_status") != "selected":
                continue
            if it.get("url") in selected_urls:
                continue
            selected.append(it)
            selected_urls.add(it.get("url"))
            if len(selected) >= max_posts:
                break

    selected_urls = {x.get("url") for x in selected}
    for it in ordered:
        if it.get("_status") == "selected" and it.get("url") not in selected_urls:
            it["_why_not"] = "名额限制（优先级低于本轮已入选）"
            skipped_due_quota.append(it)

    return selected, skipped_due_quota


def pick_unseen_candidates(
    sources: list[dict],
    state: dict,
    category: str | None = None,
    lookback_days: int = 0,
) -> list[dict]:
    seen = set(state.get("seen_urls", []))
    candidates: list[dict] = []
    cutoff_ts = 0.0
    if int(lookback_days) > 0:
        cutoff_ts = (now_cn() - dt.timedelta(days=int(lookback_days))).timestamp()

    for s in sources:
        if not s.get("enabled", True):
            continue

        src_category = s.get("category", "tech")
        if category and category != "all" and src_category != category:
            continue

        name = s.get("name") or s.get("feed")
        feed = s.get("feed")
        if not feed:
            continue

        try:
            items = feed_items(s)
        except Exception as e:
            print(f"[WARN] feed failed: {name} -> {e}")
            continue

        slow_source = is_slow_source(s, items)

        for it in items:
            url = (it.get("url") or "").strip()
            if not url or url in seen:
                continue

            pub = parse_date(it.get("published", ""))
            ts = pub.timestamp() if pub else 0
            if cutoff_ts > 0:
                # 仅抓取最近 N 天；无发布时间的条目在 lookback 模式下跳过
                if ts <= 0 or ts < cutoff_ts:
                    continue

            it["_ts"] = ts
            it["_slow_source"] = slow_source
            it["_source_name"] = name
            candidates.append(it)

    candidates.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    return candidates


def update_daily_brief_pool(state: dict, rejected_items: list[dict]) -> None:
    if not rejected_items:
        return

    day_key = now_cn().strftime("%Y-%m-%d")
    pool = state.get("daily_brief_pool", {})
    day_items = pool.get(day_key, [])

    merged = list(day_items)
    for it in rejected_items:
        if it.get("_score", 0) < 60 and not it.get("_important"):
            continue
        merged.append(
            {
                "title": it.get("title", ""),
                "url": it.get("url", ""),
                "source": it.get("source", ""),
                "description": it.get("description", ""),
                "category": it.get("category", "tech"),
                "score": it.get("_score", 0),
                "why_not": it.get("_why_not", ""),
                "ts": it.get("_ts", 0),
            }
        )

    dedup: list[dict] = []
    seen = set()
    for x in sorted(merged, key=lambda z: (z.get("score", 0), z.get("ts", 0)), reverse=True):
        u = (x.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        dedup.append(x)

    pool[day_key] = dedup[:80]
    keys = sorted(pool.keys())
    for k in keys[:-3]:
        pool.pop(k, None)

    state["daily_brief_pool"] = pool


def get_daily_brief_pool_items(state: dict, day_key: str) -> list[dict]:
    pool = state.get("daily_brief_pool", {})
    items = pool.get(day_key, [])
    if not isinstance(items, list):
        return []
    return items
