#!/usr/bin/env bash
# PreToolUse: block edits to linter/formatter configs — fix the code, not the rules

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")
BLOCKED=(".ruff.toml" "eslint.config.js" "eslint.config.mjs" "pyproject.toml" ".eslintrc" ".eslintrc.js" ".eslintrc.json" ".eslintrc.yml")

for blocked in "${BLOCKED[@]}"; do
  if [[ "$BASENAME" == "$blocked" ]]; then
    echo "BLOCKED: Do not modify $BASENAME to silence violations. Fix the code instead." >&2
    exit 2
  fi
done

exit 0
