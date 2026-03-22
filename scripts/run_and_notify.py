#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "blog_pipeline.py"
DEFAULT_NOTIFY_ENV_FILE = ROOT / ".blog_pipeline" / "notify.env"


def load_env_file(path: Path) -> dict[str, str]:
    envs: dict[str, str] = {}
    if not path.exists():
        return envs

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            envs[k] = v
    return envs


def tg_send(bot_token: str, chat_id: str, text: str, disable_preview: bool = True) -> None:
    api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true" if disable_preview else "false",
        }
    ).encode("utf-8")

    req = urllib.request.Request(api, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        _ = resp.read()


def extract_generated_paths(stdout: str) -> list[str]:
    paths: list[str] = []
    for line in (stdout or "").splitlines():
        m = re.search(r"\[OK\]\s+generated:\s+(.+)", line)
        if m:
            paths.append(m.group(1).strip())
    return paths


def is_no_new_items(stdout: str) -> bool:
    # from blog_pipeline auto mode: [OK] no new items
    return "[OK] no new items" in (stdout or "")


def build_pipeline_cmd(args) -> list[str]:
    cmd = [
        sys.executable,
        str(PIPELINE),
        args.mode,
        "--model",
        args.model,
        "--reasoning",
        args.reasoning,
        "--prompt-file",
        args.prompt_file,
    ]

    if args.mode == "manual":
        if not args.url:
            raise ValueError("manual 模式必须传 --url")
        cmd += ["--url", args.url]
        if args.title:
            cmd += ["--title", args.title]
        if args.program:
            cmd += ["--program", args.program]
        if args.description:
            cmd += ["--description", args.description]
        if args.source_file:
            cmd += ["--source-file", args.source_file]
        if args.category:
            cmd += ["--category", args.category]
    else:
        cmd += ["--category", args.category]
        cmd += ["--sources-file", args.sources_file]
        cmd += ["--max-posts", str(args.max_posts)]

    if args.output_filename:
        cmd += ["--output-filename", args.output_filename]
    if args.max_source_chars:
        cmd += ["--max-source-chars", str(args.max_source_chars)]

    return cmd


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def git_current_branch() -> str:
    proc = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], ROOT)
    if proc.returncode != 0:
        return "main"
    return (proc.stdout or "").strip() or "main"


def git_remote_url(remote: str) -> str:
    proc = run_cmd(["git", "remote", "get-url", remote], ROOT)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def to_commit_url(remote_url: str, sha: str) -> str:
    if not remote_url or not sha:
        return ""

    url = remote_url.strip()
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    if url.endswith(".git"):
        url = url[:-4]

    if "github.com" in url:
        return f"{url}/commit/{sha}"
    return ""


def rel_path_for_git(path_text: str) -> str:
    p = Path(path_text).resolve()
    try:
        return str(p.relative_to(ROOT))
    except Exception:
        return path_text


def read_site_url_config() -> tuple[str, str]:
    cfg = ROOT / "_config.yml"
    site_url = ""
    baseurl = ""
    if not cfg.exists():
        return site_url, baseurl

    for raw in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k == "url":
            site_url = v
        elif k == "baseurl":
            baseurl = v

    return site_url.rstrip("/"), baseurl.strip()


def post_path_to_blog_url(path_text: str, site_url: str, baseurl: str) -> str:
    if not site_url:
        return ""

    name = Path(path_text).name
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})-(.+)\.(md|markdown)$", name)
    if not m:
        return ""

    y, mo, d, slug, _ext = m.groups()
    base = ("/" + baseurl.strip("/") if baseurl and baseurl != "/" else "")
    return f"{site_url}{base}/{y}/{mo}/{d}/{slug}.html"


def git_publish(generated_paths: list[str], args) -> tuple[bool, str, str, str]:
    # returns (ok, short_message, sha, commit_url)
    paths_to_add: list[str] = []
    for generated_path in generated_paths:
        if generated_path:
            paths_to_add.append(rel_path_for_git(generated_path))

    # auto mode usually changes state.json
    state_path = ROOT / ".blog_pipeline" / "state.json"
    if state_path.exists():
        paths_to_add.append(str(state_path.relative_to(ROOT)))

    # optional extra add paths
    for x in args.extra_add:
        x = x.strip()
        if x:
            paths_to_add.append(x)

    # de-dup while preserving order
    seen = set()
    final_add: list[str] = []
    for p in paths_to_add:
        if p not in seen:
            seen.add(p)
            final_add.append(p)

    if final_add:
        add_proc = run_cmd(["git", "add", *final_add], ROOT)
        if add_proc.returncode != 0:
            return False, f"git add 失败: {(add_proc.stderr or '').strip()[-200:]}", "", ""

    diff_proc = run_cmd(["git", "diff", "--cached", "--quiet"], ROOT)
    if diff_proc.returncode == 0:
        return True, "没有检测到可提交变更（可能已是最新）", "", ""

    if diff_proc.returncode not in (0, 1):
        return False, f"git diff --cached 检查失败: {(diff_proc.stderr or '').strip()[-200:]}", "", ""

    msg = args.commit_message.strip()
    if not msg:
        if len(generated_paths) == 1:
            name = Path(generated_paths[0]).name
            msg = f"feat(post): add {name}"
        elif len(generated_paths) > 1:
            msg = f"feat(post): add {len(generated_paths)} generated posts"
        else:
            msg = "feat(post): update generated content"

    commit_proc = run_cmd(["git", "commit", "-m", msg], ROOT)
    if commit_proc.returncode != 0:
        return False, f"git commit 失败: {(commit_proc.stderr or '').strip()[-260:]}", "", ""

    sha_proc = run_cmd(["git", "rev-parse", "HEAD"], ROOT)
    sha = (sha_proc.stdout or "").strip() if sha_proc.returncode == 0 else ""

    if args.push:
        branch = args.branch.strip() or git_current_branch()
        push_proc = run_cmd(["git", "push", args.remote, branch], ROOT)
        if push_proc.returncode != 0:
            return (
                False,
                f"git push 失败（{args.remote}/{branch}）: {(push_proc.stderr or '').strip()[-260:]}",
                sha,
                "",
            )

        remote_url = git_remote_url(args.remote)
        commit_url = to_commit_url(remote_url, sha)
        return True, f"已提交并推送到 {args.remote}/{branch}", sha, commit_url

    return True, "已提交（未推送）", sha, ""


def main() -> int:
    file_env = load_env_file(DEFAULT_NOTIFY_ENV_FILE)
    default_bot_token = os.getenv("TG_BOT_TOKEN", "").strip() or file_env.get("TG_BOT_TOKEN", "")
    default_chat_id = os.getenv("TG_CHAT_ID", "").strip() or file_env.get("TG_CHAT_ID", "")

    p = argparse.ArgumentParser(description="Run blog pipeline, optionally git-publish, then notify Telegram")
    p.add_argument("--mode", choices=["manual", "auto"], required=True)

    # pipeline args
    p.add_argument("--url", default="")
    p.add_argument("--title", default="")
    p.add_argument("--program", default="")
    p.add_argument("--description", default="")
    p.add_argument("--source-file", default="", help="manual mode: use local txt/md as source text (skip URL fetch)")
    p.add_argument("--category", default="tech", choices=["all", "tech", "game"])
    p.add_argument("--sources-file", default=str(ROOT / "sources.json"))
    p.add_argument("--max-posts", type=int, default=3, help="auto mode: max posts per run")
    p.add_argument("--output-filename", default="")
    p.add_argument("--max-source-chars", type=int, default=0)

    p.add_argument("--model", default="gpt-5.3-codex")
    p.add_argument("--reasoning", default="low", choices=["minimal", "low", "medium", "high", "xhigh"])
    p.add_argument("--prompt-file", default=str(ROOT / "prompts" / "post_prompt.md"))

    # telegram args
    p.add_argument("--notify-env-file", default=str(DEFAULT_NOTIFY_ENV_FILE), help="telegram env file (optional)")
    p.add_argument("--bot-token", default=default_bot_token)
    p.add_argument("--chat-id", default=default_chat_id)
    p.add_argument("--notify-start", action="store_true", help="开始时也发一条通知")
    p.add_argument("--dry-run-notify", action="store_true", help="只打印通知内容，不实际发送")
    p.add_argument("--notify-only", action="store_true", help="仅发测试通知，不跑 pipeline")
    p.add_argument("--notify-no-new", action="store_true", help="auto 模式无新内容时也发送通知（默认不发）")

    # git publish args
    p.add_argument("--auto-publish", action="store_true", help="生成成功后自动 git add/commit")
    p.add_argument("--push", action="store_true", help="与 --auto-publish 一起使用：自动 git push")
    p.add_argument("--remote", default="origin", help="push remote, default origin")
    p.add_argument("--branch", default="", help="push branch, default current branch")
    p.add_argument("--commit-message", default="", help="custom commit message")
    p.add_argument("--extra-add", action="append", default=[], help="extra path to git add (repeatable)")

    args = p.parse_args()

    runtime_file_env = load_env_file(Path(args.notify_env_file)) if args.notify_env_file else {}
    bot_token = args.bot_token.strip() or runtime_file_env.get("TG_BOT_TOKEN", "")
    chat_id = args.chat_id.strip() or runtime_file_env.get("TG_CHAT_ID", "")

    if not bot_token or not chat_id:
        print("[WARN] 未设置 Telegram bot token/chat id，通知将跳过。")

    def maybe_notify(text: str) -> None:
        if args.dry_run_notify:
            print("[DRY_NOTIFY]", text)
            return
        if not bot_token or not chat_id:
            return
        tg_send(bot_token, chat_id, text)

    if args.notify_only:
        maybe_notify("✅ Telegram 通知测试成功：run_and_notify.py 已可用")
        print("[OK] notify-only done")
        return 0

    cmd = build_pipeline_cmd(args)

    if args.notify_start:
        maybe_notify(f"🚀 开始生成文章\nmode={args.mode} category={args.category}")

    proc = run_cmd(cmd, ROOT)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        fail_msg = "❌ Codex 生成失败"
        if stderr:
            fail_msg += f"\n错误：{stderr[-400:]}"
        maybe_notify(fail_msg)

        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return proc.returncode

    if args.mode == "auto" and is_no_new_items(stdout):
        if args.notify_no_new:
            maybe_notify(f"ℹ️ 本次检查无新内容\ncategory={args.category}")
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return 0

    generated_paths = extract_generated_paths(stdout)
    site_url, baseurl = read_site_url_config()
    blog_links = [post_path_to_blog_url(p, site_url, baseurl) for p in generated_paths]
    blog_links = [x for x in blog_links if x]

    notify_lines = ["✅ Codex 已完成"]
    if generated_paths:
        notify_lines.append(f"本次生成：{len(generated_paths)} 篇")

    if args.auto_publish:
        ok, msg, sha, commit_url = git_publish(generated_paths, args)
        if ok:
            notify_lines.append(f"仓库：{msg}")
        else:
            notify_lines.append(f"仓库操作失败：{msg}")
            maybe_notify("\n".join(notify_lines))
            if stdout:
                print(stdout)
            if stderr:
                print(stderr, file=sys.stderr)
            return 4

    if blog_links:
        notify_lines.append("博客链接：")
        for u in blog_links[:8]:
            notify_lines.append(f"- {u}")
    elif generated_paths:
        notify_lines.append("（未能构造公开博客链接，已生成本地文件）")
        for p in generated_paths[:5]:
            notify_lines.append(f"- {p}")

    maybe_notify("\n".join(notify_lines))

    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
