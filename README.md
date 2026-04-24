# PropertyOS — Debugging Investigation

Multi-tenant cache poisoning, money precision, timezone correctness, fail-open
auth, PII in telemetry — the failure modes that cause real Sev-1 incidents,
reproduced and fixed in one repo.

A multi-tenant property revenue dashboard was handed over with a vague
complaint: *"two clients say the numbers are wrong, and one of them is seeing
data that doesn't belong to them."* This repo is the investigation that
followed — **14 production-class bugs** found and fixed across data
isolation, financial accuracy, and deployment, each with an incident-voice
postmortem and a regression test that makes the bug unshippable again.

## The 14 bugs

### Trust — data isolation

| # | Bug | Severity |
|---|---|---|
| 1 | Cross-tenant cache poisoning — cache key missing `tenant_id` | P0 |
| 5 | Property dropdown showed every client's properties | P0 |
| 8 | Unknown email silently granted full access to Tenant A | P0 |
| 10 | Revenue summary defaulted to `prop-001` before any selection | Medium |
| 11 | `window.debugAuth` exposed full JWT to any script on the page | High |
| 14 | Emails and JWT fragments logged to Sentry/Datadog | High |

### Accuracy — financial correctness

| # | Bug | Severity |
|---|---|---|
| 2 | Monthly revenue used naive UTC instead of property timezone | High |
| 3 | `float()` on money caused cent drift and `NaN` renders | Medium |
| 9 | Hardcoded `+12%` growth badge rendered for every tenant | High |

### Infrastructure — the system wasn't running correctly

| # | Bug | Severity |
|---|---|---|
| 4 | nginx missing `/api/` proxy — every API call returned HTML | P0 |
| 6 | `QueuePool` passed to async engine — 503 on every request | High |
| 7 | Supabase `.single()` returned list — 500 on every dashboard load | High |
| 12 | Fresh Docker containers started without RLS policies | High |
| 13 | Two independent Redis connection pools under load | Medium |

Each bug has a full postmortem in [POSTMORTEM.md](POSTMORTEM.md) — impact,
cause, why it wasn't caught, fix, and what prevents recurrence — and a
working-notes entry in [NOTES.md](NOTES.md).

## The through-line

> Every layer had the right infrastructure. The pieces were never wired
> together.

Row-level security policies existed — but the backend connected as a
superuser, so they did nothing. A timezone-aware monthly revenue function
existed — but no endpoint called it. A secure client wrapper with
tenant-scoped queries existed — but the dashboard bypassed it. An IndexedDB
logout cleaner existed — but the logout path never called it. **9 of the 14
bugs had this same shape.** The bugs weren't missing features. They were
missing wires.

That pattern shaped every fix: before writing new code, find the correct code
that's already there and connect it.

## What would have caught these

Two artifacts in the repo do disproportionate work:

- **One Playwright test** — log in as Tenant A, log out, log in as Tenant B,
  assert zero A-data survives in DOM, localStorage, sessionStorage, or
  network response bodies. **Would have caught Bugs 1, 3, 9, and the
  IndexedDB persistence leak before they shipped.** One test, four bugs.
  [`frontend/e2e/tenant-isolation.spec.ts`](frontend/e2e/tenant-isolation.spec.ts).
- **Three CI convention tests** — grep `app/` at CI time for `float(revenue)`,
  `datetime.utcnow()`, and inline `f"revenue:..."` cache keys. **Would have
  blocked Bugs 1, 2, and 3 at PR review.** Finding violations *while writing
  them* caught 16 instances of `datetime.utcnow()` and 7 stray `print()`
  calls in legacy modules that nobody had flagged.
  [`backend/tests/test_conventions.py`](backend/tests/test_conventions.py).

This is the move the repo is really about. Catching one bug is luck.
Preventing a whole class of bugs with a lint rule is engineering.

## What's in the repo

- **[POSTMORTEM.md](POSTMORTEM.md)** — one incident write-up per bug in the
  voice I'd use internally: impact first, technical cause second, explicit
  answer to *why didn't we catch this*.
- **[NOTES.md](NOTES.md)** — engineer's working notes for each bug and the
  architectural hardening that followed (typed tenant identifiers, single
  mandatory tenant dependency, cache key centralisation, RLS session wiring,
  structured logging, mypy `--strict` gate, convention tests). Plus an
  out-of-scope table of 20 deferred findings with severity, and a
  prioritised "if I had one more week" list.
- **`backend/tests/`** — 89 tests: unit, integration, contract
  (schemathesis), convention lints.
- **`frontend/e2e/`** — Playwright suite, including the tenant-switch test
  above.
- **`database/migrations/`** — RLS policies and an `app_user` role with
  `NOSUPERUSER, NOINHERIT` so RLS becomes a real backstop instead of a
  false safety net.

## The Claude Code setup

The investigation was run inside Claude Code with deliberate configuration:

- **[CLAUDE.md](CLAUDE.md)** — stop rules (`float()` on money, superuser
  bypassing RLS, silencing linters to make violations go away), conventions,
  pointers to auth and context files.
- **`.claude/agents/`** — purpose-built subagents: `security-reviewer`,
  `context-auditor`, `test-writer`, `explore-agent`, `cto-interviewer`.
  Each has a narrow brief and read-only or narrowly-scoped tool access.
- **`.claude/commands/`** — slash commands for the workflow:
  `/bug-fix-start`, `/pre-fix-check`, `/fix-plan`, `/root-cause-analysis`,
  `/ai-code-review`, `/context-audit`, `/notes-update`, `/session-end`.
- **`.claude/context-snapshot.md`** — re-read after compaction so long
  sessions don't lose the architectural picture.

The point isn't agent novelty. It's that the workflow produced the same
artifacts a human-run investigation would — postmortems, regression tests,
an honest out-of-scope list — because the slash commands forced them at
each step.

## What I'd build next

The fixes close the specific bugs. These are the architectural moves that
would close the *class* of bug — what I'd prioritise with another week:

- **Make forgetting `tenant_id` a type error.** A `TenantScopedSession`
  wrapper that carries `tenant_id` and refuses to build a query without it.
  Today the filter is a convention; tomorrow it's the type system.
- **Turn on Postgres RLS for real.** Restrict the app role to a non-superuser
  `app_user` with `NOSUPERUSER, NOINHERIT`, set `app.tenant_id` per request,
  and let RLS be the backstop instead of a false safety net (see PM-5,
  PM-12).
- **One contract, one source of truth.** Generate TypeScript types from the
  OpenAPI schema so `total_revenue: Decimal` on the backend fails the
  frontend build the moment someone types it as `number` (see PM-3).
- **Tenant-aware audit log.** Every read of tenant-scoped data writes
  `(actor, tenant_id, resource, timestamp)` to an append-only table. Makes
  "was client data accessed" answerable, not guessed at.
- **Structured redacting logger everywhere.** Finish the `lib/logger.ts`
  migration and add an ESLint rule that makes `console.log` a build failure
  outside tests (see PM-14).
- **Money as a type.** A `Money` value object that wraps `Decimal` + currency
  and has no `__float__` — makes `float(revenue)` impossible to write, not
  just discouraged (see PM-3).

## Running it

```bash
docker-compose up
# Frontend: http://localhost:3000
# API:      http://localhost:8000/docs
```

Test credentials — both tenants share `prop-001` by design, which is what
demonstrates the cache poisoning bug:

- Tenant A: `tenant-a@example.com` / `client_a_2024`
- Tenant B: `tenant-b@example.com` / `client_b_2024`

```bash
cd backend && python -m pytest        # 89 passed
cd frontend && npx playwright test    # tenant-isolation E2E
```

## About this repo

An anonymised debugging investigation against a realistic multi-tenant
codebase. All bugs and fixes are real; client names are not.
