#!/usr/bin/env bash
# PostToolUse: run linters after every file edit so Claude sees violations in real-time

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

REPO_ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null || pwd)

if [[ "$FILE_PATH" == *.py ]]; then
  echo "==> ruff check $FILE_PATH"
  cd "$REPO_ROOT/backend" && uv run ruff check "$FILE_PATH" --fix 2>&1 || true
fi

if [[ "$FILE_PATH" == *.ts || "$FILE_PATH" == *.tsx ]]; then
  echo "==> eslint $FILE_PATH"
  cd "$REPO_ROOT/frontend" && npx eslint "$FILE_PATH" --fix 2>&1 || true
fi

exit 0
