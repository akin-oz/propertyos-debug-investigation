Before writing any fix, produce a one-line fix spec. Nothing gets coded until it's written.

Answer these in order:
1. Exact file and line number where the bug lives
2. What the bug currently does (one sentence — what wrong data or behaviour does it produce?)
3. What the correct behaviour should be (one sentence)
4. Does this fix touch any tenant-isolation surface? If yes — what guard do you add?
5. Is there anything you need to read before starting? (If yes — read it now)

Output the fix spec as one line:
`fix([scope]): [what changes] in [file:line] — was [wrong behaviour], now [correct behaviour]`

This line becomes the commit message.

Then confirm: run /pre-fix-check before writing the first line of code.
