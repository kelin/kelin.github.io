#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [title]"
  exit 1
fi

URL="$1"
TITLE="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/blog_pipeline.py manual \
  --url "$URL" \
  --title "$TITLE" \
  --model gpt-5.3-codex \
  --reasoning low

echo "Done. Check _posts/ for the new file."
