#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

python3 scripts/run_and_notify.py \
  --mode daily-brief \
  --model gpt-5.3-codex \
  --reasoning low \
  --auto-publish \
  --push
