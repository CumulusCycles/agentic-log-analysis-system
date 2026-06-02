#!/bin/bash
# PostToolUse formatter — auto-formats files after Claude writes or edits them.
# Hook payload arrives as JSON on stdin; the file path lives at .tool_input.file_path.

set -uo pipefail

INPUT="$(cat)"
FILE="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')"

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  exit 0
fi

case "$FILE" in
  *.py)
    if command -v uv &>/dev/null; then
      uv run black "$FILE" 2>/dev/null || true
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx|*.json)
    if command -v pnpm &>/dev/null; then
      pnpm dlx prettier --write "$FILE" 2>/dev/null || true
    fi
    ;;
esac

exit 0
