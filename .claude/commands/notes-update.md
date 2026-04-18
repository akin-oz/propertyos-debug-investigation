Append a bug fix entry to NOTES.md. Use this exact structure — no deviations.

```
## [Bug name] — [YYYY-MM-DD]

**What the user experienced:** [product language — what did the client see or complain about? No technical jargon.]

**Why it was dangerous:** [product and security impact — not just what the code did, but what it meant for the business]

**Root cause:** [one sentence — specific file:line and what assumption was wrong]

**The fix:** [what changed, why this approach over alternatives]

**Regression test added:** [test name and exactly what it asserts]

**What I'd watch for next:** [related risks or follow-up work]
```

Rules:
- "What the user experienced" must be understandable by a non-technical stakeholder
- "Root cause" must include a file:line reference
- "Regression test added" must name the actual test function

After writing, confirm: does NOTES.md now have entries for every bug fixed so far in this session?

Pair with /root-cause-analysis to generate the one-liner root cause before writing this entry.
