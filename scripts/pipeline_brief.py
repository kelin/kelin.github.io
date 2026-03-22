from __future__ import annotations

import json
import re
import urllib.request

from pipeline_common import feed_items, now_cn

DAILY_BRIEF_HN_FEED = "https://hnrss.org/frontpage"
DAILY_BRIEF_ARXIV_FEED = "https://export.arxiv.org/rss/cs.AI"
DAILY_BRIEF_ARXIV_FALLBACK = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&start=0&max_results=12"
DAILY_BRIEF_HF_API = "https://huggingface.co/api/trending?type=model"
DAILY_BRIEF_GITHUB_PY_URL = "https://github.com/trending/python?since=daily"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"


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
    req = urllib.request.Request(DAILY_BRIEF_HF_API, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))

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
            }
        )
    return out


def fetch_github_trending_python(max_items: int = 8) -> list[dict]:
    req = urllib.request.Request(DAILY_BRIEF_GITHUB_PY_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

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
            }
        )
        if len(out) >= max_items:
            break

    return out


def build_daily_brief_prompt(
    day_key: str,
    rejected_pool: list[dict],
    hn_items: list[dict],
    arxiv_items: list[dict],
    hf_items: list[dict],
    gh_py_items: list[dict],
) -> str:
    lines: list[str] = []
    lines.append(f"你是信息策展编辑。请写一篇 {day_key} 的‘每日快讯’中文短文，面向 AI/游戏开发者。")
    lines.append("要求：")
    lines.append("1) 不要每条都用同一句开头（例如不要重复‘为什么值得看’）。")
    lines.append("2) 每条用 3 行：核心事实 / 影响判断 / 建议动作，再给原链接。")
    lines.append("3) 语言简洁但信息要具体，不要空泛。")
    lines.append("4) 必须包含两个部分：主文落选重点 + 外部信源精选。")
    lines.append(f"5) 标题固定：{day_key} 每日快讯。")
    lines.append("6) 不确定就写‘源信息不足’，不要编造。")
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
    lines.append("[HuggingFace Trending Models]")
    for i, x in enumerate(hf_items[:10], 1):
        lines.append(
            f"{i}. {x.get('title','')} | likes={x.get('likes',0)} | downloads={x.get('downloads',0)} | updated={x.get('updated','')} | url={x.get('url','')}"
        )

    lines.append("")
    lines.append("[GitHub Trending Python]")
    for i, x in enumerate(gh_py_items[:10], 1):
        lines.append(f"{i}. {x.get('title','')} | {x.get('url','')}")

    lines.append("")
    lines.append("输出 Markdown，不要 front matter。")
    return "\n".join(lines)
