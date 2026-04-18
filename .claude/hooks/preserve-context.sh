#!/usr/bin/env bash
# PreCompact: snapshot current task state before compaction — re-read after if context drifts

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
SNAPSHOT="$REPO_ROOT/.claude/context-snapshot.md"

cat > "$SNAPSHOT" << EOF
# Context snapshot — $(date -u +"%Y-%m-%dT%H:%M:%SZ")

Saved before compaction. Re-read this at session start or after /compact to restore orientation.

## Modified files
$(git diff --name-only HEAD 2>/dev/null || echo "None")

## Diff summary
$(git diff --stat HEAD 2>/dev/null || echo "No staged changes")

## Recent commits
$(git log --oneline -5 2>/dev/null || echo "No commits yet")

## Reminder: active bugs
- Bug-1: backend/app/services/cache.py — tenant_id missing from cache key
- Bug-2: backend/app/services/reservations.py — timezone handling
- Bug-3: backend/app/api/v1/dashboard.py + frontend/src/components/Dashboard.tsx — float precision
EOF

echo "Context snapshot saved to .claude/context-snapshot.md"
exit 0
