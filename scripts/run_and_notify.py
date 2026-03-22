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
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
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


def extract_generated_path(stdout: str) -> str:
    # from: [OK] generated: /path/to/post.md
    m = re.search(r"\[OK\]\s+generated:\s+(.+)", stdout)
    return m.group(1).strip() if m else ""


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
        if args.category:
            cmd += ["--category", args.category]
    else:
        cmd += ["--category", args.category]
        cmd += ["--sources-file", args.sources_file]

    if args.output_filename:
        cmd += ["--output-filename", args.output_filename]
    if args.max_source_chars:
        cmd += ["--max-source-chars", str(args.max_source_chars)]

    return cmd


def main() -> int:
    file_env = load_env_file(DEFAULT_NOTIFY_ENV_FILE)
    default_bot_token = os.getenv("TG_BOT_TOKEN", "").strip() or file_env.get("TG_BOT_TOKEN", "")
    default_chat_id = os.getenv("TG_CHAT_ID", "").strip() or file_env.get("TG_CHAT_ID", "")

    p = argparse.ArgumentParser(description="Run blog pipeline, then notify Telegram when done")
    p.add_argument("--mode", choices=["manual", "auto"], required=True)

    # pipeline args
    p.add_argument("--url", default="")
    p.add_argument("--title", default="")
    p.add_argument("--program", default="")
    p.add_argument("--description", default="")
    p.add_argument("--category", default="tech", choices=["all", "tech", "game"])
    p.add_argument("--sources-file", default=str(ROOT / "sources.json"))
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

    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode == 0:
        out_path = extract_generated_path(stdout)
        if out_path:
            text = f"✅ Codex 已完成\n文件：{out_path}"
        else:
            text = "✅ Codex 已完成（未解析到输出文件路径，请看日志）"
        maybe_notify(text)

        print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return 0

    fail_msg = "❌ Codex 生成失败"
    if stderr:
        fail_msg += f"\n错误：{stderr[-400:]}"
    maybe_notify(fail_msg)

    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
