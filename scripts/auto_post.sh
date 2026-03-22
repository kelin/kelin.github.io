#!/usr/bin/env bash
set -euo pipefail

CATEGORY="${1:-all}"   # all|tech|game
MAX_POSTS="${2:-0}"    # 0 表示不限制篇数

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/blog_pipeline.py auto \
  --category "$CATEGORY" \
  --max-posts "$MAX_POSTS" \
  --strict-select \
  --min-selection-score 70 \
  --max-skip-report 8 \
  --max-brief-items 5 \
  --model gpt-5.3-codex \
  --reasoning low

echo "Done. Auto mode finished."
