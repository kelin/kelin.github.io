#!/usr/bin/env python3
"""
Blog pipeline CLI (manual / auto / daily-brief / check-sources).
"""

from __future__ import annotations

import argparse
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

from pipeline_brief import (
    DAILY_BRIEF_ARXIV_FEED,
    DAILY_BRIEF_HN_FEED,
    build_brief_roundup_post,
    build_daily_brief_prompt,
    fetch_github_trending_python,
    fetch_hf_trending_models,
    top_feed_items_for_brief,
)
from pipeline_common import (
    DEFAULT_MAX_SOURCE_CHARS,
    PROMPT_FILE,
    SOURCES_FILE,
    STATE_FILE,
    build_prompt,
    fetch_url_text,
    load_json,
    now_cn,
    read_source_file_text,
    run_codex,
    save_json,
    translate_title_to_zh,
    write_post,
)
from pipeline_selection import (
    DEFAULT_MAX_BRIEF_ITEMS,
    DEFAULT_MAX_SKIP_REPORT,
    DEFAULT_MIN_SELECTION_SCORE,
    evaluate_candidate,
    get_daily_brief_pool_items,
    pick_unseen_candidates,
    select_with_diversity,
    update_daily_brief_pool,
)


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
    return write_post(meta, body, out_name=args.output_filename)


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
    hf_items: list[dict] = []
    gh_py_items: list[dict] = []

    try:
        hn_items = top_feed_items_for_brief(DAILY_BRIEF_HN_FEED, "Hacker News", max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief HN fetch failed: {e}")

    try:
        arxiv_items = top_feed_items_for_brief(DAILY_BRIEF_ARXIV_FEED, "arXiv cs.AI", max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief arXiv fetch failed: {e}")

    try:
        hf_items = fetch_hf_trending_models(max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief HF fetch failed: {e}")

    try:
        gh_py_items = fetch_github_trending_python(max_items=10)
    except Exception as e:
        print(f"[WARN] daily brief GitHub trending fetch failed: {e}")

    if not rejected_pool and not hn_items and not arxiv_items and not hf_items and not gh_py_items:
        print("[ERR] daily brief has no source material")
        return 4

    prompt = build_daily_brief_prompt(
        day_key=day_key,
        rejected_pool=rejected_pool,
        hn_items=hn_items,
        arxiv_items=arxiv_items,
        hf_items=hf_items,
        gh_py_items=gh_py_items,
    )

    body = run_codex(prompt=prompt, model=args.model, reasoning=args.reasoning)

    title = f"{day_key} 每日快讯"
    meta = {
        "title": title,
        "title_raw": title,
        "program": "Auto Curator Daily Brief",
        "url": DAILY_BRIEF_HN_FEED,
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
    from pipeline_common import feed_items

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
    raise SystemExit(main())
