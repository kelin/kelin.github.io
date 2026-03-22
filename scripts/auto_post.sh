#!/usr/bin/env bash
set -euo pipefail

CATEGORY="${1:-all}"  # all|tech|game

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/blog_pipeline.py auto \
  --category "$CATEGORY" \
  --model gpt-5.3-codex \
  --reasoning low

echo "Done. If there was a new item, one post was generated in _posts/."
