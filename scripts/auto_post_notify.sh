#!/usr/bin/env bash
set -euo pipefail

# usage:
#   ./scripts/auto_post_notify.sh tech 3
# default behavior: generate up to N posts + notify telegram + git add/commit/push

CATEGORY="${1:-tech}"  # all|tech|game
MAX_POSTS="${2:-3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/run_and_notify.py \
  --mode auto \
  --category "$CATEGORY" \
  --max-posts "$MAX_POSTS" \
  --strict-select \
  --min-selection-score 70 \
  --max-skip-report 8 \
  --max-brief-items 5 \
  --model gpt-5.3-codex \
  --reasoning low \
  --auto-publish \
  --push
