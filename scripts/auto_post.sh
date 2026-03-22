#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/blog_pipeline.py auto \
  --model gpt-5.3-codex \
  --reasoning low

echo "Done. If there was a new item, one post was generated in _posts/."
