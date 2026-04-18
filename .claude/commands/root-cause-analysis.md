Interrogate this bug through structured questioning until reaching:
1. The true root cause (not the symptom)
2. The systemic gap that allowed it to exist undetected

Work through four layers in order. Do not skip. Do not move to next until current is resolved.

**Layer 1 — The symptom (what the user experienced)**
- What exactly did the user see? (not what the code did — what the user experienced)
- When did they first notice it?
- Consistent or intermittent?
- Affects all users or specific ones?

**Layer 2 — The immediate technical cause**
- What line of code produced this outcome?
- What was the code trying to do vs what it actually did?
- What assumption turned out to be wrong?
- Can you reproduce it deterministically? What triggers it?

Drive toward a specific file, function, and line. "`cache.py:34` uses `revenue:{property_id}` as key" is specific. "The cache layer" is not.

**Layer 3 — The root cause (why the assumption was wrong)**
Ask 5 whys until you hit a human decision, missing constraint, or architectural gap — not another code symptom.
- Why was that assumption made in the first place?
- Was it correct at some point and then became wrong?
- Or was it never correct and just not caught?

**Layer 4 — The systemic gap (why it wasn't caught)**
- What test would have caught this before it shipped?
- Why didn't that test exist?
- Is there a linting rule, type constraint, or architectural boundary that would have made this bug impossible to write?
- Is this a one-off or a pattern — could the same class of bug exist elsewhere?

Do not accept generic answers. "We should have had better tests" is not an answer. "We had no test that logged in as two different tenants and asserted their revenue data was different" is an answer.

---

**Output when all four layers are resolved:**

```
Symptom:    [user-facing description]
Why 1:      [immediate technical cause]
Why 2:      [reason the code was written this way]
Why 3:      [reason the assumption was wrong]
Why 4:      [reason it wasn't caught]
Why 5:      [the systemic gap]
Root cause: [the bottom of the chain]

One-liner: "[Component] [did X] because [assumption], which was never validated by [missing constraint], allowing [user impact] to reach production."

Prevention: [one concrete thing — a specific test, a type constraint, an architectural rule — that makes this class of bug impossible or immediately detectable]
```

Rules:
- Ask one question at a time
- After each answer, state your updated hypothesis before asking the next question
- Push back on vague answers: "that's a symptom, not a cause"
- If the person is stuck, offer your best hypothesis and ask them to confirm or correct it
- The session ends only when all four layers are resolved and the output is produced

Pair output with /notes-update to pipe the one-liner directly into NOTES.md.
