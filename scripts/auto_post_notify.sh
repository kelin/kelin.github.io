#!/usr/bin/env bash
set -euo pipefail

# usage:
#   TG_BOT_TOKEN=xxx TG_CHAT_ID=yyy ./scripts/auto_post_notify.sh tech

CATEGORY="${1:-tech}"  # all|tech|game

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/run_and_notify.py \
  --mode auto \
  --category "$CATEGORY" \
  --model gpt-5.3-codex \
  --reasoning low
