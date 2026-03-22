from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import subprocess
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "_posts"
STATE_DIR = ROOT / ".blog_pipeline"
STATE_FILE = STATE_DIR / "state.json"
SOURCES_FILE = ROOT / "sources.json"
PROMPT_FILE = ROOT / "prompts" / "post_prompt.md"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
DEFAULT_MAX_SOURCE_CHARS = 22000
DEFAULT_MAX_ITEMS_PER_FEED = 30


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


def fetch_snapshot_text(url: str, max_chars: int = 7000) -> str:
    title, text = fetch_url_text(url)
    merged = f"TITLE: {title}\n\n{text}".strip()
    return merged[:max_chars]
