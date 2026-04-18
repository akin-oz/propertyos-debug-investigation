End-of-session ritual. Execute in this exact order — do not skip steps.

1. Run /context-audit — collect all violations and corrections from this session
2. Show me the CLAUDE.md patch and wait for approval before applying
3. Apply approved patch to CLAUDE.md
4. Run /notes-update for any bug fixed this session without a NOTES.md entry
5. Stage and commit:
   ```
   git add CLAUDE.md NOTES.md
   git commit -m "chore: update CLAUDE.md post-session"
   ```
6. Confirm: `git status` — any uncommitted changes?
7. Final check: does NOTES.md have an entry for every bug fixed?

Output a session summary:
```
## Session summary — [YYYY-MM-DD]

Bugs fixed: [list with commit hashes]
Tests added: [list with file paths]
CLAUDE.md changes: [summary of what changed and why]
CI status: [green / red — what's failing]
Next session: [first thing to tackle, specific file if applicable]
```

This commit is the self-improving loop made visible in git history. The git log of CLAUDE.md tells the story of a system that gets better over time.
