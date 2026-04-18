Use the context-auditor agent to scan CLAUDE.md and this session for drift.

The auditor checks:
1. Which CLAUDE.md rules were violated in this session?
2. Which corrections were made verbally that aren't captured in CLAUDE.md yet?
3. Which CLAUDE.md entries are now stale given what we learned?
4. Which entries are vague enough to be open to interpretation? (Flag for sharpening)

Output format:
```
## Context audit — [timestamp]

### Rules violated this session
- [rule] — [when/how it happened]

### Corrections not yet in CLAUDE.md
- [correction] → suggested entry: "[exact CLAUDE.md line]"

### Stale entries
- [entry] → [why stale] → [suggested replacement or delete]

### Vague entries to sharpen
- [entry] → [sharper version]

### CLAUDE.md patch
[exact lines to add / modify / remove — ready to apply]
```

After producing the audit, ask: "Apply this patch to CLAUDE.md?" — do not modify the file without approval.
