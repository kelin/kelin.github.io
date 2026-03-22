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


# -------------------- output --------------------

def front_matter(meta: dict) -> str:
    dt_cn = now_cn()
    title = (meta.get("title") or "untitled").replace('"', '\\"')
    source_program = (meta.get("program") or "").replace('"', '\\"')
    source_episode = (meta.get("title") or "").replace('"', '\\"')
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
    episode = meta.get("title") or "untitled"
    slug = slugify(episode)[:90]
    filename = out_name or f"{dt_cn}-{slug}.md"

    path = POSTS_DIR / filename
    content = front_matter(meta) + body_md.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return path


# -------------------- picking --------------------

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

        for it in items:
            url = (it.get("url") or "").strip()
            if not url or url in seen:
                continue

            pub = parse_date(it.get("published", ""))
            ts = pub.timestamp() if pub else 0
            it["_ts"] = ts
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

    max_posts = max(1, int(args.max_posts))
    generated_urls: list[str] = []
    generated_count = 0

    for item in candidates:
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

    if generated_count == 0:
        print("[ERR] no posts generated from current candidates")
        return 4

    seen = list(dict.fromkeys(state.get("seen_urls", []) + generated_urls))
    state["seen_urls"] = seen[-6000:]
    state["last_run"] = now_cn().isoformat()
    state["last_category"] = args.category
    state["last_generated_count"] = generated_count
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
    p_auto.set_defaults(func=cmd_auto)

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
