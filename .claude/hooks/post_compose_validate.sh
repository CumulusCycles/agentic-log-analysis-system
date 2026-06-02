#!/bin/bash
# PostToolUse — validates docker-compose.yml after any edit.
# Hook payload arrives as JSON on stdin; the file path lives at .tool_input.file_path.

set -uo pipefail

INPUT="$(cat)"
FILE="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')"

if [ -z "$FILE" ]; then
  exit 0
fi

if [[ "$FILE" != *"docker-compose"* && "$FILE" != *"/compose.yml" && "$FILE" != *"/compose.yaml" ]]; then
  exit 0
fi

# Skip when the compose file does not exist yet (e.g. pre-Phase-2 scaffold).
if [ ! -f "$FILE" ]; then
  exit 0
fi

echo "[hook] Validating docker-compose.yml..."

# Run validation from the directory containing the file so relative paths resolve.
COMPOSE_DIR="$(dirname "$FILE")"
if ! (cd "$COMPOSE_DIR" && docker compose config --quiet) 2>/dev/null; then
  echo "[hook] WARNING: docker-compose.yml has syntax errors" >&2
  exit 0
fi

if ! grep -q "platform: linux/arm64" "$FILE"; then
  echo "[hook] WARNING: Not all services may have platform: linux/arm64 set" >&2
fi

echo "[hook] docker-compose.yml valid"
exit 0
