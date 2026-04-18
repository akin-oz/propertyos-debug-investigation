Run a 3-lens parallel code review on all changes in this branch vs main.

Spawn 3 subagents simultaneously. Each has a single review lens:

**Subagent 1 — Security reviewer**
Role: security engineer. Check exclusively:
- New fail-open paths (returns data when it should error)
- Hardcoded credentials, tokens, or fallback values
- Auth bypasses or missing authentication checks
- Missing input validation at system boundaries

**Subagent 2 — Tenant isolation reviewer**
Role: multi-tenancy specialist. Check exclusively:
- Data access without `tenant_id` filter — queries that could return cross-tenant data
- New tables or queries not in `secure_client.py` allowlist
- Cache keys that could collide across tenants
- Endpoints that accept a resource ID without validating tenant ownership

**Subagent 3 — Financial precision reviewer**
Role: fintech engineer. Check exclusively:
- Any use of `float()` on monetary values (must be `Decimal.quantize()`)
- String/number type mismatches between backend response and frontend consumer
- Revenue totals that could accumulate floating-point drift
- Display formatting that could show misleading precision

Each subagent reads `git diff main` and returns:
- Issues found: severity (P0/P1/P2), file:line, recommended fix
- Areas explicitly checked and found clean

Synthesise all three outputs into `REVIEW.md`:
```
## Security review
[findings or "No issues found"]

## Tenant isolation review
[findings or "No issues found"]

## Financial precision review
[findings or "No issues found"]

## Verdict
[safe to open PR / fix these issues first]
```
