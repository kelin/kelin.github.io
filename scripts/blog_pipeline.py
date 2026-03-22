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
import os
import re
import subprocess
import sys
import textwrap
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "_posts"
STATE_DIR = ROOT / ".blog_pipeline"
STATE_FILE = STATE_DIR / "state.json"
SOURCES_FILE = ROOT / "sources.json"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
DEFAULT_MAX_SOURCE_CHARS = 18000


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


def feed_items(feed_url: str, source_name: str) -> list[dict]:
    req = urllib.request.Request(feed_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml = resp.read()

    root = ET.fromstring(xml)
    items: list[dict] = []

    # RSS
    if root.tag.lower().endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return []
        for it in channel.findall("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub_raw = (it.findtext("pubDate") or "").strip()
            desc = (it.findtext("description") or "").strip()
            dt_obj = parse_date(pub_raw)
            items.append(
                {
                    "source": source_name,
                    "title": title,
                    "url": link,
                    "published": dt_obj.isoformat() if dt_obj else "",
                    "description": strip_html(desc),
                }
            )
        return items

    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.findall("atom:entry", ns):
        title = (it.findtext("atom:title", default="", namespaces=ns) or "").strip()
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
                "title": title,
                "url": link,
                "published": dt_obj.isoformat() if dt_obj else "",
                "description": strip_html(summary),
            }
        )
    return items


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


def build_prompt(meta: dict, source_text: str) -> str:
    prompt = f"""
你是专业中文科技播客/视频内容编辑。
请根据下面资料，生成一篇“单篇详细总结”，输出为 Markdown 正文（不要 YAML front matter，不要代码块包裹）。

【写作目标】
- 内容对象：博主/播客/视频内容总结（不是泛新闻快讯）
- 深度：详细，信息密度高，可直接发布到个人博客
- 风格：清晰、具体、少空话

【必须使用的固定结构】
## 节目信息
- 节目：...
- 本期：...
- 链接：...

## 一、先介绍节目
## 二、先介绍嘉宾
## 三、这期讲了什么（按节目脉络）
- 至少 8 个小点，尽量结合时间线或话题顺序

## 四、关键概念白话版
- 至少 5 个术语/概念，每个用 2~4 句解释

## 五、我们怎么看
- 用“我们”的口吻给出有判断力的分析
- 避免空泛陈述，写清楚依据和影响

## 六、一句可直接借鉴
- 给出可执行的一句话

【素材元信息】
- 标题：{meta.get('title', '')}
- 来源：{meta.get('program', '')}
- 链接：{meta.get('url', '')}
- 发布时间：{meta.get('published', '')}
- 简介：{meta.get('description', '')}

【正文素材（可能含噪声，需筛选）】
{source_text}
""".strip()
    return prompt


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


def front_matter(title: str, source_url: str, source_program: str, source_episode: str) -> str:
    dt_cn = now_cn()
    return textwrap.dedent(
        f"""---
title: "{title.replace('"', '\\"')}"
date: "{dt_cn.strftime('%Y-%m-%d %H:%M:%S %z')}"
source_program: "{source_program.replace('"', '\\"')}"
source_episode: "{source_episode.replace('"', '\\"')}"
source_url: "{source_url}"
tags: ["AI", "Podcast", "Video", "Summary"]
---

"""
    )


def write_post(meta: dict, body_md: str, out_name: str | None = None) -> Path:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)

    dt_cn = now_cn().strftime("%Y-%m-%d")
    episode = meta.get("title") or "untitled"
    slug = slugify(episode)[:80]
    filename = out_name or f"{dt_cn}-{slug}.md"

    path = POSTS_DIR / filename
    title = f"{episode}｜内容总结"
    fm = front_matter(title=title, source_url=meta.get("url", ""), source_program=meta.get("program", ""), source_episode=episode)
    content = fm + body_md.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def pick_newest_unseen(sources: list[dict], state: dict) -> dict | None:
    seen = set(state.get("seen_urls", []))
    candidates = []

    for s in sources:
        name = s.get("name") or s.get("feed")
        feed = s.get("feed")
        if not feed:
            continue
        try:
            items = feed_items(feed, name)
        except Exception as e:
            print(f"[WARN] feed failed: {name} -> {e}")
            continue

        for it in items:
            url = it.get("url", "")
            if not url or url in seen:
                continue
            pub = parse_date(it.get("published", ""))
            ts = pub.timestamp() if pub else 0
            it["_ts"] = ts
            candidates.append(it)

    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("_ts", 0), reverse=True)
    return candidates[0]


def generate_one(meta: dict, args) -> Path:
    # Fetch source page text first
    page_title, page_text = fetch_url_text(meta["url"])
    if page_title and not meta.get("title"):
        meta["title"] = page_title

    source_text = page_text[: args.max_source_chars]
    prompt = build_prompt(meta, source_text)

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
    }

    out_path = generate_one(meta, args)
    print(f"[OK] generated: {out_path}")
    return 0


def cmd_auto(args) -> int:
    sources = load_json(SOURCES_FILE, default=[])
    if not sources:
        print(f"[ERR] no sources config: {SOURCES_FILE}")
        return 2

    state = load_json(STATE_FILE, default={"seen_urls": []})
    item = pick_newest_unseen(sources, state)
    if not item:
        print("[OK] no new items")
        return 0

    meta = {
        "title": item.get("title", ""),
        "program": item.get("source", ""),
        "url": item.get("url", ""),
        "published": item.get("published", ""),
        "description": item.get("description", ""),
    }

    out_path = generate_one(meta, args)
    print(f"[OK] generated: {out_path}")

    # mark seen
    seen = list(dict.fromkeys(state.get("seen_urls", []) + [meta["url"]]))
    state["seen_urls"] = seen[-5000:]
    state["last_run"] = now_cn().isoformat()
    save_json(STATE_FILE, state)
    print(f"[OK] state updated: {STATE_FILE}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Single-post blog pipeline (manual + auto)")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="gpt-5.3-codex", help="Codex model")
    common.add_argument("--reasoning", default="low", choices=["minimal", "low", "medium", "high", "xhigh"], help="Codex reasoning effort")
    common.add_argument("--max-source-chars", type=int, default=DEFAULT_MAX_SOURCE_CHARS, help="Max source chars fed into Codex")
    common.add_argument("--output-filename", default=None, help="Optional fixed output filename under _posts/")

    sp = p.add_subparsers(dest="mode", required=True)

    p_manual = sp.add_parser("manual", parents=[common], help="Generate one post from one URL")
    p_manual.add_argument("--url", required=True)
    p_manual.add_argument("--title", default="")
    p_manual.add_argument("--program", default="")
    p_manual.add_argument("--description", default="")
    p_manual.set_defaults(func=cmd_manual)

    p_auto = sp.add_parser("auto", parents=[common], help="Auto-pick one newest unseen item from sources.json")
    p_auto.set_defaults(func=cmd_auto)

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
