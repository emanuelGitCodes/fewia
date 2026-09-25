# Junior brief template

Fill every field. A junior sees only this brief and the files it names.
Do not paste secrets, tokens, or credential values.

```text
ITEM: <slug>-NN — <one-line title>
ROLE: <junior name>
COMPLEXITY: simple | standard | complex | exceptional | maximum
WRITER MODEL: default order | --model <id> | --only --model <id>
EFFORT OVERRIDE: none | <level>

BASE BRANCH: main | claude/<slug>-MM
WORK BRANCH: claude/<slug>-NN

GOAL:
<What the item delivers, in two to four sentences.>

OWNED FILES (the writer MAY change only these):
- <path>
- <path>

READ-ONLY CONTEXT (read these for integration):
- <path> — <why>

CONTRACTS (fixed by the senior; do not change):
- <signature, type, endpoint, or table>

ACCEPTANCE:
- <observable behavior 1>
- <observable behavior 2>

TESTS THE WRITER MUST ADD:
- <behavior and failure case>
- <boundary case>

OUT OF SCOPE:
- <things the writer MUST NOT do>

GATES:
- backend: ruff check, ruff format --check, mypy --strict, pytest
- frontend: npm test, npm run build   (only when frontend files change)
- extra: <focused command, if any>

CAP: 150 added code lines. Tests and docs do not count.

PROTOCOL: Follow .claude/skills/feature-loop/references/junior-protocol.md.
```

A repair message through `SendMessage` uses this shape:

```text
REPAIR ROUND: <n>
REVIEWED SHA: <sha>
BLOCKING FINDINGS:
1. <file:line> — <defect> — <failure scenario>
NON-BLOCKING TO FOLD IN:
- <finding>
KEEP: the same owned files, contracts, and writer model constraints.
```
