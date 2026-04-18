#!/usr/bin/env bash
# Stop hook: run tests before Claude finishes — exit 2 forces it to continue until tests pass

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
BACKEND="$REPO_ROOT/backend"

CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(py|ts|tsx)$')

if [[ -z "$CHANGED" ]]; then
  exit 0
fi

if echo "$CHANGED" | grep -q "backend/"; then
  echo "==> Running backend tests..."
  cd "$BACKEND" && uv run pytest tests/ -x -q 2>&1
  if [[ $? -ne 0 ]]; then
    echo "" >&2
    echo "Tests failed. Fix failing tests before finishing." >&2
    exit 2
  fi
fi

echo "All tests pass."
exit 0
