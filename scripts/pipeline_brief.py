from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline_common import feed_items, http_get_bytes, load_json, now_cn, parse_date

DAILY_BRIEF_HN_FEED = "https://hnrss.org/frontpage"
DAILY_BRIEF_ARXIV_FEED = "https://export.arxiv.org/rss/cs.AI"
DAILY_BRIEF_ARXIV_FALLBACK = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&start=0&max_results=12"
DAILY_BRIEF_HF_API = "https://huggingface.co/api/trending?type=model"
DAILY_BRIEF_GITHUB_PY_URL = "https://github.com/trending/python?since=daily"

GAME_SOURCE_HINTS = [
    "gdc",
    "designer notes",
    "eggplant",
    "game maker",
    "deconstructor",
    "idlethumbs",
]


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

    # arXiv 的 RSS 在周末/节假日可能 0 条，回退到 API 最新投稿
    if not items and "arxiv" in source_name.lower():
        src_fallback = {
            "name": source_name,
            "feed": DAILY_BRIEF_ARXIV_FALLBACK,
            "category": "tech",
            "type": "research",
            "max_items": max_items,
            "enabled": True,
        }
        items = feed_items(src_fallback)

    return items[:max_items]


def fetch_hf_trending_models(max_items: int = 8) -> list[dict]:
    raw, _ = http_get_bytes(DAILY_BRIEF_HF_API, timeout=20)
    data = json.loads(raw.decode("utf-8", errors="ignore"))

    out: list[dict] = []
    for x in data.get("recentlyTrending", [])[:max_items]:
        rd = x.get("repoData", {})
        model_id = (rd.get("id") or "").strip()
        if not model_id:
            continue
        out.append(
            {
                "title": model_id,
                "url": f"https://huggingface.co/{model_id}",
                "likes": rd.get("likes", 0),
                "downloads": rd.get("downloads", 0),
                "updated": rd.get("lastModified", ""),
                "pipeline_tag": rd.get("pipeline_tag", ""),
                "source": "HuggingFace Trending Models",
                "category": "tech",
            }
        )
    return out


def fetch_github_trending_python(max_items: int = 8) -> list[dict]:
    raw, _ = http_get_bytes(DAILY_BRIEF_GITHUB_PY_URL, timeout=20)
    html = raw.decode("utf-8", errors="ignore")

    repos = re.findall(r'<h2[^>]*class="h3 lh-condensed"[^>]*>\s*<a[^>]*href="/([^"]+)"', html)

    out: list[dict] = []
    seen: set[str] = set()
    for full in repos:
        repo = full.strip()
        if not repo or repo in seen or repo.count("/") != 1:
            continue
        seen.add(repo)
        out.append(
            {
                "title": repo,
                "url": f"https://github.com/{repo}",
                "source": "GitHub Trending Python",
                "category": "tech",
            }
        )
        if len(out) >= max_items:
            break

    return out


def infer_item_category(item: dict) -> str:
    c = (item.get("category") or "").strip().lower()
    if c in {"tech", "game"}:
        return c

    src = (item.get("source") or "").lower()
    if any(k in src for k in GAME_SOURCE_HINTS):
        return "game"
    return "tech"


def split_rejected_by_category(rejected_pool: list[dict]) -> tuple[list[dict], list[dict]]:
    tech: list[dict] = []
    game: list[dict] = []
    for x in rejected_pool:
        cat = infer_item_category(x)
        x["category"] = cat
        if cat == "game":
            game.append(x)
        else:
            tech.append(x)

    tech.sort(key=lambda z: (z.get("score", 0), z.get("ts", 0)), reverse=True)
    game.sort(key=lambda z: (z.get("score", 0), z.get("ts", 0)), reverse=True)
    return tech, game


def fetch_category_source_items(sources_file: str | Path, category: str, max_sources: int = 4, max_items_per_source: int = 1) -> list[dict]:
    sources = load_json(Path(sources_file), default=[])
    out: list[dict] = []

    for s in sources:
        if not s.get("enabled", True):
            continue
        if s.get("category", "tech") != category:
            continue

        source_name = s.get("name") or s.get("feed") or "Unknown"
        try:
            items = feed_items(s)
        except Exception:
            continue

        for it in items[:max_items_per_source]:
            out.append(
                {
                    "title": it.get("title", ""),
                    "url": it.get("url", ""),
                    "source": source_name,
                    "published": it.get("published", ""),
                    "category": category,
                }
            )

    out.sort(key=lambda x: parse_date(x.get("published", "")).timestamp() if parse_date(x.get("published", "")) else 0, reverse=True)

    # 按来源去重，最多保留 N 个来源
    final: list[dict] = []
    seen_sources: set[str] = set()
    for it in out:
        src = (it.get("source") or "").strip()
        if not src or src in seen_sources:
            continue
        seen_sources.add(src)
        final.append(it)
        if len(final) >= max_sources:
            break

    return final


def _append_group(lines: list[str], label: str, items: list[dict], max_items: int = 12) -> None:
    lines.append(label)
    if not items:
        lines.append("(empty)")
        lines.append("")
        return

    for i, x in enumerate(items[:max_items], 1):
        extra_bits = []
        if x.get("score") is not None:
            extra_bits.append(f"score={x.get('score', 0)}")
        if x.get("why_not"):
            extra_bits.append(f"why_not={x.get('why_not')}")
        if x.get("likes"):
            extra_bits.append(f"likes={x.get('likes')}")
        if x.get("downloads"):
            extra_bits.append(f"downloads={x.get('downloads')}")
        if x.get("updated"):
            extra_bits.append(f"updated={x.get('updated')}")
        extra = " | ".join(extra_bits)
        if extra:
            lines.append(f"{i}. {x.get('source','')} | {x.get('title','')} | {extra} | url={x.get('url','')}")
        else:
            lines.append(f"{i}. {x.get('source','')} | {x.get('title','')} | url={x.get('url','')}")

    lines.append("")


def build_daily_brief_prompt(
    day_key: str,
    rejected_pool: list[dict],
    hn_items: list[dict],
    arxiv_items: list[dict],
    hf_items: list[dict],
    gh_py_items: list[dict],
    game_source_items: list[dict],
) -> str:
    tech_rejected, game_rejected = split_rejected_by_category(rejected_pool)

    # 标准化 source 字段，方便模型按来源分章
    for x in hn_items:
        x.setdefault("source", "Hacker News Front Page")
        x.setdefault("category", "tech")
    for x in arxiv_items:
        x.setdefault("source", "arXiv cs.AI")
        x.setdefault("category", "tech")

    lines: list[str] = []
    lines.append(f"你是信息策展编辑。请写一篇 {day_key} 的‘每日快讯’中文短文，面向 AI/游戏开发者。")
    lines.append("必须使用以下固定结构：")
    lines.append("## Tech 章节")
    lines.append("### Tech｜主文落选重点（按来源分小节）")
    lines.append("### Tech｜外部来源（按来源分小节：HN、arXiv、HF、GitHub）")
    lines.append("## Game 章节")
    lines.append("### Game｜主文落选重点（按来源分小节）")
    lines.append("### Game｜来源补充（按来源分小节）")
    lines.append("每个条目必须含 4 行：核心事实 / 影响判断 / 建议动作 / 原链接。")
    lines.append("不要每条都用同一句开头，不要空话，不要编造。")
    lines.append(f"标题固定：{day_key} 每日快讯")
    lines.append("")

    _append_group(lines, "[TECH_REJECTED]", tech_rejected, max_items=15)
    _append_group(lines, "[GAME_REJECTED]", game_rejected, max_items=15)
    _append_group(lines, "[TECH_EXTERNAL_HN]", hn_items, max_items=8)
    _append_group(lines, "[TECH_EXTERNAL_ARXIV]", arxiv_items, max_items=8)
    _append_group(lines, "[TECH_EXTERNAL_HF]", hf_items, max_items=8)
    _append_group(lines, "[TECH_EXTERNAL_GITHUB]", gh_py_items, max_items=8)
    _append_group(lines, "[GAME_EXTERNAL_FROM_SOURCES]", game_source_items, max_items=8)

    lines.append("输出 Markdown，不要 front matter。")
    return "\n".join(lines)
