from __future__ import annotations

from pipeline_common import feed_items, now_cn

DAILY_BRIEF_HN_FEED = "https://hnrss.org/frontpage"
DAILY_BRIEF_ARXIV_FEED = "https://export.arxiv.org/rss/cs.AI"
DAILY_BRIEF_HF_URL = "https://huggingface.co/models?sort=trending"
DAILY_BRIEF_GITHUB_PY_URL = "https://github.com/trending/python?since=daily"


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
    return items[:max_items]


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
