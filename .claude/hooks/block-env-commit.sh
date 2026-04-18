#!/usr/bin/env bash
# PreToolUse: block .env files from being written or staged

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

if [[ -n "$FILE_PATH" ]]; then
  BASENAME=$(basename "$FILE_PATH")
  if [[ "$BASENAME" == ".env" || "$BASENAME" == ".env.local" || "$BASENAME" == ".env.production" || "$BASENAME" == ".env.staging" ]]; then
    echo "BLOCKED: Never write to .env files. Use environment variables or a secrets manager." >&2
    exit 2
  fi
fi

if [[ -n "$COMMAND" ]]; then
  if echo "$COMMAND" | grep -qE "git (add|commit).+\.env"; then
    echo "BLOCKED: Cannot stage or commit .env files." >&2
    exit 2
  fi
fi

exit 0
