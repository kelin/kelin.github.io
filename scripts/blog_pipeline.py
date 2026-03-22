#!/usr/bin/env python3
"""
Blog pipeline for single-post generation (manual + auto mode).

- manual mode: pass one URL
- auto mode: poll configured RSS/Atom sources and pick one newest unseen item
- output: one markdown post file per run under _posts/
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "_posts"
STATE_DIR = ROOT / ".blog_pipeline"
STATE_FILE = STATE_DIR / "state.json"
SOURCES_FILE = ROOT / "sources.json"
PROMPT_FILE = ROOT / "prompts" / "post_prompt.md"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
DEFAULT_MAX_SOURCE_CHARS = 22000
DEFAULT_MAX_ITEMS_PER_FEED = 30
DEFAULT_MIN_SELECTION_SCORE = 70
DEFAULT_MAX_SKIP_REPORT = 8
DEFAULT_MAX_BRIEF_ITEMS = 5
LOW_INFO_DESC_CHARS = 120

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

SLOW_FEED_INTERVAL_DAYS = 5
DAILY_BRIEF_HN_FEED = "https://hnrss.org/frontpage"
DAILY_BRIEF_ARXIV_FEED = "https://export.arxiv.org/rss/cs.AI"
DAILY_BRIEF_HF_URL = "https://huggingface.co/models?sort=trending"
DAILY_BRIEF_GITHUB_PY_URL = "https://github.com/trending/python?since=daily"


# -------------------- helpers --------------------

def now_cn() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "post"


def strip_html(html: str) -> str:
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", html)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_date(s: str) -> dt.datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None


# -------------------- source fetching --------------------

def fetch_url_text(url: str, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")

    encoding = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        encoding = m.group(1)

    html = raw.decode(encoding, errors="ignore")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = strip_html(title_match.group(1)) if title_match else ""
    text = strip_html(html)
    return title, text


def read_source_file_text(path_text: str) -> str:
    p = Path(path_text).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p.read_text(encoding="utf-8", errors="ignore")


def feed_items(source: dict) -> list[dict]:
    source_name = source.get("name") or source.get("feed") or "Unknown"
    feed_url = source.get("feed")
    if not feed_url:
        return []

    category = source.get("category", "tech")
    source_type = source.get("type", "podcast")
    max_items = int(source.get("max_items", DEFAULT_MAX_ITEMS_PER_FEED))
    include_pattern = source.get("include_title_regex", "")
    exclude_pattern = source.get("exclude_title_regex", "")

    req = urllib.request.Request(feed_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=35) as resp:
        xml = resp.read()

    root = ET.fromstring(xml)
    items: list[dict] = []

    def title_ok(title: str) -> bool:
        if include_pattern and not re.search(include_pattern, title, re.I):
            return False
        if exclude_pattern and re.search(exclude_pattern, title, re.I):
            return False
        return True

    # RSS
    if root.tag.lower().endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return []

        for it in channel.findall("item")[:max_items]:
            title = (it.findtext("title") or "").strip()
            if not title_ok(title):
                continue

            link = (it.findtext("link") or "").strip()
            if not link:
                link = (it.findtext("guid") or "").strip()

            pub_raw = (it.findtext("pubDate") or "").strip()
            desc = (it.findtext("description") or "").strip()
            dt_obj = parse_date(pub_raw)
            items.append(
                {
                    "source": source_name,
                    "category": category,
                    "source_type": source_type,
                    "title": title,
                    "url": link,
                    "published": dt_obj.isoformat() if dt_obj else "",
                    "description": strip_html(desc),
                }
            )
        return items

    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.findall("atom:entry", ns)[:max_items]:
        title = (it.findtext("atom:title", default="", namespaces=ns) or "").strip()
        if not title_ok(title):
            continue

        link = ""
        for l in it.findall("atom:link", ns):
            rel = l.attrib.get("rel", "alternate")
            if rel in ("alternate", ""):
                link = l.attrib.get("href", "")
                if link:
                    break

        pub_raw = (
            it.findtext("atom:published", default="", namespaces=ns)
            or it.findtext("atom:updated", default="", namespaces=ns)
        ).strip()
        summary = (
            it.findtext("atom:summary", default="", namespaces=ns)
            or it.findtext("atom:content", default="", namespaces=ns)
        )
        dt_obj = parse_date(pub_raw)

        items.append(
            {
                "source": source_name,
                "category": category,
                "source_type": source_type,
                "title": title,
                "url": link,
                "published": dt_obj.isoformat() if dt_obj else "",
                "description": strip_html(summary),
            }
        )

    return items


# -------------------- prompt --------------------

def render_prompt(template_text: str, values: dict[str, str]) -> str:
    out = template_text
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v or "")
    return out


def build_prompt(meta: dict, source_text: str, prompt_file: Path) -> str:
    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt file not found: {prompt_file}")

    template = prompt_file.read_text(encoding="utf-8")
    values = {
        "title": meta.get("title", ""),
        "program": meta.get("program", ""),
        "url": meta.get("url", ""),
        "published": meta.get("published", ""),
        "description": meta.get("description", ""),
        "category": meta.get("category", ""),
        "source_type": meta.get("source_type", ""),
        "source_text": source_text,
    }
    return render_prompt(template, values).strip()


# -------------------- codex --------------------

def run_codex(prompt: str, model: str, reasoning: str) -> str:
    cmd = [
        "codex",
        "exec",
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{reasoning}"',
        "-",
    ]
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed: {proc.stderr[-1000:]}")

    out = proc.stdout.strip()
    if not out:
        raise RuntimeError("codex returned empty output")
    return out


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def translate_title_to_zh(title: str, model: str) -> str:
    t = (title or "").strip()
    if not t or has_cjk(t):
        return t

    prompt = (
        "把下面标题翻译成自然、简洁的中文标题。"
        "只输出翻译结果，不要解释，不要引号。\n\n"
        f"原始标题：{t}"
    )
    try:
        out = run_codex(prompt=prompt, model=model, reasoning="minimal")
        line = out.splitlines()[0].strip()
        return line or t
    except Exception:
        return t


# -------------------- output --------------------

def front_matter(meta: dict) -> str:
    dt_cn = now_cn()
    title = (meta.get("title") or "untitled").replace('"', '\\"')
    source_program = (meta.get("program") or "").replace('"', '\\"')
    source_episode = (meta.get("title_raw") or meta.get("title") or "").replace('"', '\\"')
    source_url = meta.get("url", "")
    category = meta.get("category", "tech")

    tags = ["AI", "Summary", "SinglePost"]
    tags.append("Tech" if category == "tech" else "Game")

    tags_render = ", ".join([f'"{x}"' for x in tags])

    return textwrap.dedent(
        f"""---
title: "{title}｜内容总结"
date: "{dt_cn.strftime('%Y-%m-%d %H:%M:%S %z')}"
source_program: "{source_program}"
source_episode: "{source_episode}"
source_url: "{source_url}"
source_category: "{category}"
tags: [{tags_render}]
---

"""
    )


def write_post(meta: dict, body_md: str, out_name: str | None = None) -> Path:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    dt_cn = now_cn().strftime("%Y-%m-%d")
    episode = meta.get("title_raw") or meta.get("title") or "untitled"
    slug = slugify(episode)[:90]
    filename = out_name or f"{dt_cn}-{slug}.md"

    path = POSTS_DIR / filename
    content = front_matter(meta) + body_md.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return path


# -------------------- picking --------------------

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

    # 咨询流 + 信息少：默认忽略；但若事件重要，进入“合并快讯”候选
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


def build_brief_roundup_post(items: list[dict], category: str) -> tuple[dict, str]:
    cat_name = "科技" if category == "tech" else "游戏" if category == "game" else "综合"
    date_text = now_cn().strftime("%Y-%m-%d")
    title = f"{date_text} {cat_name}重要快讯（信息有限）"

    lines = [
        "## 说明",
        "以下条目具备重要性信号，但原始信息量不足，不适合单独长文，先做简短整合。",
        "",
        "## 今日快讯",
    ]

    for idx, it in enumerate(items, 1):
        t = (it.get("title") or "未命名条目").strip()
        src = (it.get("source") or "未知来源").strip()
        url = (it.get("url") or "").strip()
        desc = (it.get("description") or "").strip()
        why = (it.get("_why_not") or "信息不足但重要").strip()
        if len(desc) > 160:
            desc = desc[:160].rstrip() + "…"

        lines.append(f"### {idx}. {t}")
        lines.append(f"- 来源：{src}")
        lines.append(f"- 链接：{url}")
        lines.append(f"- 入选原因：{why}")
        if desc:
            lines.append(f"- 已知信息：{desc}")
        lines.append("")

    meta = {
        "title": title,
        "title_raw": title,
        "program": "Auto Curator",
        "url": items[0].get("url", "") if items else "",
        "published": now_cn().isoformat(),
        "description": "重要但信息不足条目的合并快讯",
        "category": category if category in {"tech", "game"} else "tech",
        "source_type": "brief-roundup",
    }
    body = "\n".join(lines).strip() + "\n"
    return meta, body


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
    # 仅保留最近3天
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


def top_feed_items_for_brief(feed_url: str, source_name: str, max_items: int = 8) -> list[dict]:
    src = {
        "name": source_name,
        "feed": feed_url,
        "category": "tech",
        "type": "news",
        "max_items": max_items,
        "enabled": True,
    }
    items = feed_items(src)
    return items[:max_items]


def fetch_snapshot_text(url: str, max_chars: int = 7000) -> str:
    title, text = fetch_url_text(url)
    merged = f"TITLE: {title}\n\n{text}".strip()
    return merged[:max_chars]


def build_daily_brief_prompt(day_key: str, rejected_pool: list[dict], hn_items: list[dict], arxiv_items: list[dict], hf_text: str, gh_py_text: str) -> str:
    lines: list[str] = []
    lines.append(f"你是信息策展编辑。请写一篇 {day_key} 的‘每日快讯’中文短文，面向 AI/游戏开发者。")
    lines.append("要求：")
    lines.append("1) 短、准、可执行；不要营销语。")
    lines.append(f"2) 标题固定：{day_key} 每日快讯。")
    lines.append("3) 必须包含两个部分：")
    lines.append("   - 主文落选但值得关注（从给定 rejected pool 里选）")
    lines.append("   - 外部信源精选（HN/arXiv/HuggingFace/GitHub Trending Python）")
    lines.append("4) 每条给一句‘为什么值得看’和原链接。")
    lines.append("5) 不确定就写‘源信息不足’。不编造。")
    lines.append("")

    lines.append("[主文落选池]")
    if rejected_pool:
        for i, x in enumerate(rejected_pool[:20], 1):
            lines.append(
                f"{i}. {x.get('title','')} | {x.get('source','')} | score={x.get('score',0)} | why_not={x.get('why_not','')} | url={x.get('url','')}"
            )
    else:
        lines.append("(empty)")

    lines.append("")
    lines.append("[Hacker News Front Page]")
    for i, x in enumerate(hn_items[:10], 1):
        lines.append(f"{i}. {x.get('title','')} | {x.get('url','')}")

    lines.append("")
    lines.append("[arXiv cs.AI]")
    for i, x in enumerate(arxiv_items[:10], 1):
        lines.append(f"{i}. {x.get('title','')} | {x.get('url','')}")

    lines.append("")
    lines.append("[HuggingFace Trending Models 页面文本截断]")
    lines.append(hf_text[:4500] if hf_text else "(fetch failed)")

    lines.append("")
    lines.append("[GitHub Trending Python 页面文本截断]")
    lines.append(gh_py_text[:4500] if gh_py_text else "(fetch failed)")

    lines.append("")
    lines.append("输出 Markdown，不要 front matter。")
    return "\n".join(lines)


def pick_unseen_candidates(sources: list[dict], state: dict, category: str | None = None) -> list[dict]:
    seen = set(state.get("seen_urls", []))
    candidates: list[dict] = []

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
            it["_ts"] = ts
            it["_slow_source"] = slow_source
            it["_source_name"] = name
            candidates.append(it)

    candidates.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    return candidates


# -------------------- commands --------------------

def generate_one(meta: dict, args) -> Path:
    source_file = (getattr(args, "source_file", "") or "").strip()

    if source_file:
        page_text = read_source_file_text(source_file)
        page_title = ""
    else:
        page_title, page_text = fetch_url_text(meta["url"])

    if page_title and not meta.get("title"):
        meta["title"] = page_title

    raw_title = (meta.get("title") or "").strip()
    meta["title_raw"] = raw_title
    meta["title"] = translate_title_to_zh(raw_title, model=args.model)

    source_text = page_text[: args.max_source_chars]
    if not source_text.strip():
        raise RuntimeError("source text is empty (可能被反爬拦截或源文件为空)")

    prompt = build_prompt(meta, source_text, prompt_file=Path(args.prompt_file))

    body = run_codex(prompt=prompt, model=args.model, reasoning=args.reasoning)
    out_path = write_post(meta, body, out_name=args.output_filename)
    return out_path


def cmd_manual(args) -> int:
    meta = {
        "title": args.title or "",
        "program": args.program or urlparse(args.url).netloc,
        "url": args.url,
        "published": now_cn().isoformat(),
        "description": args.description or "",
        "category": args.category,
        "source_type": args.source_type,
    }

    out_path = generate_one(meta, args)
    print(f"[OK] generated: {out_path}")
    return 0


def cmd_auto(args) -> int:
    sources = load_json(Path(args.sources_file), default=[])
    if not sources:
        print(f"[ERR] no sources config: {args.sources_file}")
        return 2

    state = load_json(STATE_FILE, default={"seen_urls": []})
    candidates = pick_unseen_candidates(sources, state, category=args.category)
    if not candidates:
        print("[OK] no new items")
        return 0

    max_posts_arg = int(args.max_posts)
    max_posts = len(candidates) if max_posts_arg <= 0 else max(1, max_posts_arg)
    min_score = int(args.min_selection_score)

    rejected: list[dict] = []

    if args.strict_select:
        evaluated = [evaluate_candidate(x, min_score) for x in candidates]
        selected_items, skipped_due_quota = select_with_diversity(evaluated, max_posts)
        brief_pool = [x for x in evaluated if x.get("_status") == "brief_merge"]
        rejected = [x for x in evaluated if x.get("_status") == "rejected"] + skipped_due_quota

        update_daily_brief_pool(state, rejected)

        for it in selected_items:
            print(f"[SELECT] {it.get('url','')} | score={it.get('_score',0)} | why={it.get('_why','')}")

        max_skip_report = max(0, int(args.max_skip_report))
        if max_skip_report > 0:
            rejected_sorted = sorted(rejected, key=lambda x: (x.get("_score", 0), x.get("_ts", 0)), reverse=True)
            for it in rejected_sorted[:max_skip_report]:
                print(f"[SKIP] {it.get('url','')} | score={it.get('_score',0)} | why={it.get('_why_not','未达标')}")
    else:
        selected_items = candidates[:max_posts]
        brief_pool = []

    generated_urls: list[str] = []
    generated_count = 0

    for item in selected_items:
        if generated_count >= max_posts:
            break

        meta = {
            "title": item.get("title", ""),
            "program": item.get("source", ""),
            "url": item.get("url", ""),
            "published": item.get("published", ""),
            "description": item.get("description", ""),
            "category": item.get("category", "tech"),
            "source_type": item.get("source_type", "podcast"),
        }

        try:
            out_path = generate_one(meta, args)
            print(f"[OK] generated: {out_path}")
            generated_urls.append(meta["url"])
            generated_count += 1
        except Exception as e:
            print(f"[WARN] generate failed: {meta.get('url')} -> {e}")
            continue

    # 重要但信息不足：合并成一篇短快讯（只占一个名额）
    if args.strict_select and brief_pool and generated_count < max_posts:
        keep_n = max(1, int(args.max_brief_items))
        brief_items = sorted(brief_pool, key=lambda x: (x.get("_score", 0), x.get("_ts", 0)), reverse=True)[:keep_n]
        for it in brief_items:
            print(f"[MERGE] {it.get('url','')} | score={it.get('_score',0)} | why={it.get('_why_not','重要但信息不足，合并快讯')}")

        meta, body = build_brief_roundup_post(brief_items, category=args.category)
        out_name = f"{now_cn().strftime('%Y-%m-%d')}-brief-{args.category}-{now_cn().strftime('%H%M%S')}.md"
        out_path = write_post(meta, body, out_name=out_name)
        print(f"[OK] generated: {out_path}")
        generated_count += 1
        for it in brief_items:
            if it.get("url"):
                generated_urls.append(it["url"])

    if generated_count == 0:
        print("[ERR] no posts generated from current candidates")
        return 4

    seen = list(dict.fromkeys(state.get("seen_urls", []) + generated_urls))
    state["seen_urls"] = seen[-6000:]
    state["last_run"] = now_cn().isoformat()
    state["last_category"] = args.category
    state["last_generated_count"] = generated_count
    state["strict_select"] = bool(args.strict_select)
    state["min_selection_score"] = min_score
    save_json(STATE_FILE, state)
    print(f"[OK] state updated: {STATE_FILE}")
    return 0


def cmd_daily_brief(args) -> int:
    state = load_json(STATE_FILE, default={"seen_urls": []})
    day_key = now_cn().strftime("%Y-%m-%d")

    rejected_pool = get_daily_brief_pool_items(state, day_key)

    hn_items: list[dict] = []
    arxiv_items: list[dict] = []
    hf_text = ""
    gh_py_text = ""

    try:
        hn_items = top_feed_items_for_brief(DAILY_BRIEF_HN_FEED, "Hacker News", max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief HN fetch failed: {e}")

    try:
        arxiv_items = top_feed_items_for_brief(DAILY_BRIEF_ARXIV_FEED, "arXiv cs.AI", max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief arXiv fetch failed: {e}")

    try:
        hf_text = fetch_snapshot_text(DAILY_BRIEF_HF_URL, max_chars=7000)
    except Exception as e:
        print(f"[WARN] daily brief HF fetch failed: {e}")

    try:
        gh_py_text = fetch_snapshot_text(DAILY_BRIEF_GITHUB_PY_URL, max_chars=7000)
    except Exception as e:
        print(f"[WARN] daily brief GitHub trending fetch failed: {e}")

    if not rejected_pool and not hn_items and not arxiv_items and not hf_text and not gh_py_text:
        print("[ERR] daily brief has no source material")
        return 4

    prompt = build_daily_brief_prompt(
        day_key=day_key,
        rejected_pool=rejected_pool,
        hn_items=hn_items,
        arxiv_items=arxiv_items,
        hf_text=hf_text,
        gh_py_text=gh_py_text,
    )

    body = run_codex(prompt=prompt, model=args.model, reasoning=args.reasoning)

    title = f"{day_key} 每日快讯"
    meta = {
        "title": title,
        "title_raw": title,
        "program": "Auto Curator Daily Brief",
        "url": "https://hnrss.org/frontpage",
        "published": now_cn().isoformat(),
        "description": "主文落选重点 + HN/arXiv/HF/GitHub Daily Brief",
        "category": "tech",
        "source_type": "daily-brief",
    }

    out_name = args.output_filename or f"{day_key}-daily-brief.md"
    out_path = write_post(meta, body, out_name=out_name)
    print(f"[OK] generated: {out_path}")

    state["last_daily_brief"] = now_cn().isoformat()
    state["last_daily_brief_file"] = str(out_path)
    save_json(STATE_FILE, state)
    print(f"[OK] state updated: {STATE_FILE}")
    return 0


def cmd_check_sources(args) -> int:
    sources = load_json(Path(args.sources_file), default=[])
    if not sources:
        print(f"[ERR] no sources config: {args.sources_file}")
        return 2

    ok = 0
    fail = 0
    for s in sources:
        name = s.get("name", "<unnamed>")
        category = s.get("category", "tech")
        feed = s.get("feed", "")
        if not feed:
            print(f"[FAIL] {name} ({category}) -> empty feed")
            fail += 1
            continue

        try:
            items = feed_items(s)
            if items:
                print(f"[ OK ] {name} ({category}) -> {feed} | items: {len(items)} | latest: {items[0].get('title','')[:80]}")
                ok += 1
            else:
                print(f"[FAIL] {name} ({category}) -> {feed} | no items")
                fail += 1
        except Exception as e:
            print(f"[FAIL] {name} ({category}) -> {feed} | {e}")
            fail += 1

    print(f"\nsummary: ok={ok}, fail={fail}, total={ok+fail}")
    return 0 if fail == 0 else 1


# -------------------- parser --------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Single-post blog pipeline (manual + auto)")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="gpt-5.3-codex", help="Codex model")
    common.add_argument(
        "--reasoning",
        default="low",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Codex reasoning effort",
    )
    common.add_argument(
        "--max-source-chars",
        type=int,
        default=DEFAULT_MAX_SOURCE_CHARS,
        help="Max source chars fed into Codex",
    )
    common.add_argument("--output-filename", default=None, help="Optional fixed output filename under _posts/")
    common.add_argument("--prompt-file", default=str(PROMPT_FILE), help="Prompt template file path")

    sp = p.add_subparsers(dest="mode", required=True)

    p_manual = sp.add_parser("manual", parents=[common], help="Generate one post from one URL")
    p_manual.add_argument("--url", required=True)
    p_manual.add_argument("--title", default="")
    p_manual.add_argument("--program", default="")
    p_manual.add_argument("--description", default="")
    p_manual.add_argument("--category", default="tech", choices=["tech", "game"], help="Post category")
    p_manual.add_argument("--source-type", default="podcast", help="podcast/video/blog")
    p_manual.add_argument("--source-file", default="", help="Optional local txt/md file as source; when set, skip URL fetch")
    p_manual.set_defaults(func=cmd_manual)

    p_auto = sp.add_parser("auto", parents=[common], help="Auto-pick newest unseen items from sources.json")
    p_auto.add_argument("--sources-file", default=str(SOURCES_FILE), help="sources config JSON")
    p_auto.add_argument("--category", default="all", choices=["all", "tech", "game"], help="Source category filter")
    p_auto.add_argument("--max-posts", type=int, default=3, help="Max posts to generate per auto run")
    p_auto.add_argument("--strict-select", action="store_true", help="Enable strict quality selection mode")
    p_auto.add_argument("--min-selection-score", type=int, default=DEFAULT_MIN_SELECTION_SCORE, help="Strict mode score threshold")
    p_auto.add_argument("--max-skip-report", type=int, default=DEFAULT_MAX_SKIP_REPORT, help="Max skipped items printed with reasons")
    p_auto.add_argument("--max-brief-items", type=int, default=DEFAULT_MAX_BRIEF_ITEMS, help="Max low-info important items merged into one brief post")
    p_auto.set_defaults(func=cmd_auto)

    p_daily = sp.add_parser("daily-brief", parents=[common], help="Generate one daily brief post")
    p_daily.set_defaults(func=cmd_daily_brief)

    p_check = sp.add_parser("check-sources", help="Validate source feeds from sources.json")
    p_check.add_argument("--sources-file", default=str(SOURCES_FILE), help="sources config JSON")
    p_check.set_defaults(func=cmd_check_sources)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except urllib.error.HTTPError as e:
        print(f"[ERR] HTTP error: {e}")
        return 3
    except urllib.error.URLError as e:
        print(f"[ERR] URL error: {e}")
        return 3
    except Exception as e:
        print(f"[ERR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
