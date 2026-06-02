#!/bin/bash
# PreToolUse guard — blocks dangerous bash commands before execution.
# Hook payload arrives as JSON on stdin; the command lives at .tool_input.command.
# Exit 2 = block the command (stderr is shown to Claude); Exit 0 = allow.

set -uo pipefail

INPUT="$(cat)"
COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')"

if [ -z "$COMMAND" ]; then
  exit 0
fi

if echo "$COMMAND" | grep -q "docker compose down -v"; then
  echo "BLOCKED: 'docker compose down -v' destroys all persistent volumes." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE "rm -rf /|rm -rf \*|rm -rf ~"; then
  echo "BLOCKED: Dangerous rm command detected." >&2
  exit 2
fi

# Block any access to .env files (reads, copies, moves) — .env.example remains allowed.
if echo "$COMMAND" | grep -qE "(cat|less|more|head|tail|grep|awk|sed|cp|mv)[[:space:]]+.*\.env([[:space:]]|$)"; then
  echo "BLOCKED: Do not access .env files directly. Use .env.example for templates." >&2
  exit 2
fi

# Block writes to .env (redirects, tee).
if echo "$COMMAND" | grep -qE ">>?[[:space:]]*\.env([[:space:]]|$)|tee[[:space:]]+.*\.env([[:space:]]|$)"; then
  echo "BLOCKED: Do not write to .env files. Edit .env.example instead." >&2
  exit 2
fi

exit 0
