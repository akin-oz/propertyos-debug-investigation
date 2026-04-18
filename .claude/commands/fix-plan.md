You are in plan-only mode. Do NOT write any code or modify any files.

Produce a numbered plan for fixing all bugs in this codebase. Read each relevant file before planning — never assume what the code does.

For each bug, output:
1. Bug name and product impact (what the user experiences — not technical jargon)
2. Exact file(s) and line(s) to change
3. Root cause (one sentence)
4. Fix approach (one sentence)
5. Dependencies on other bug fixes (if any)
6. How to verify it's fixed (specific test command or observable behaviour)

Bugs to plan:
- Bug 1: Cache poisoning — `backend/app/services/cache.py`
- Bug 2: Timezone handling — `backend/app/services/reservations.py`
- Bug 3 backend: Decimal precision — `backend/app/api/v1/dashboard.py`
- Bug 3 frontend: Type mismatch — `frontend/src/components/Dashboard.tsx`
- Additional: `backend/app/core/database_pool.py`, `frontend/src/`, `backend/app/core/secure_client.py`

Output format:
```
## Fix Plan

### Bug 1 — [name]
**Product impact:** ...
**File:** file:line
**Root cause:** ...
**Fix:** ...
**Dependencies:** none / Bug N first
**Verify:** `pytest tests/test_X.py` / observable behaviour

[repeat for each bug]

## Recommended fix order
1. [bug] — rationale
...
```

When I approve this plan, we execute one bug at a time using /bug-fix-start.
