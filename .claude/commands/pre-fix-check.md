Before fixing any bug, answer all 5 questions. Do not proceed until every answer is concrete.

**What?**
The concrete deliverable — not "fix authentication" but "remove the mock-token-123 fallback in secureApi.ts:47 and add a decodeJwtPayload helper that returns null on malformed tokens"

**Where?**
Exact file path and line number. If you don't know — read the file first.

**Why?**
What is this bug doing to users? Frame in product language.

**How to verify?**
A success condition you can check: specific pytest command, expected HTTP response, or observable UI behaviour.

**What not to do?**
Explicit scope limits — what adjacent code stays untouched?

---

If any answer is "I'm not sure" — stop and read the relevant file.

Output format:
```
What:        [one concrete sentence]
Where:       [file:line]
Why:         [user impact in product language]
Verify:      [specific command or behaviour]
Scope limit: [what not to touch]
```

Nothing gets coded until this checklist is complete and you've confirmed all five.
