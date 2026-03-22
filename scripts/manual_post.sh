#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <url> [title] [category: tech|game] [source_file]"
  exit 1
fi

URL="$1"
TITLE="${2:-}"
CATEGORY="${3:-tech}"
SOURCE_FILE="${4:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

CMD=(
  python3 scripts/blog_pipeline.py manual
  --url "$URL"
  --title "$TITLE"
  --category "$CATEGORY"
  --model gpt-5.3-codex
  --reasoning low
)

if [[ -n "$SOURCE_FILE" ]]; then
  CMD+=(--source-file "$SOURCE_FILE")
fi

"${CMD[@]}"

echo "Done. Check _posts/ for the new file."
