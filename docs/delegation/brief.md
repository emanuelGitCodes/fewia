# Work item brief

The coordinator fills this template for each work item. Keep it to about
60 lines. List file paths. Do not paste file contents or secrets.

```text
ITEM: <slug>-NN — <title>
ROLE: <role>   TIER: S | M | L   COMPLEXITY: <class>
WRITER MODEL: --only --model <id> --effort <level> [--advisor <id>]
BASE BRANCH: <branch>   WORK BRANCH: <branch>

GOAL: <two to four sentences>

OWNED FILES:
- <path>

READ FOR CONTEXT:
- <path> — <why>

CONTRACTS (fixed):
- <signature, type, endpoint, table, or command>

ACCEPTANCE:
- <observable behavior>

PROBED FACTS:
- <repository fact the coordinator checked before dispatch>

TESTS THE WRITER MUST ADD:
- <behavior and failure case>

OUT OF SCOPE:
- <what the writer MUST NOT do>

GATES: dev_supervisor.gates --base <base>, plus <extra command, if any>
CAP: 1000 added code lines. Tests and docs do not count.
PROTOCOL: docs/delegation/junior.md
```

A repair message uses this shape:

```text
REPAIR ROUND: <n>   REVIEWED SHA: <sha>
BLOCKING:
1. <file:line> — <defect> — <failure scenario>
FOLD IN:
- <non-blocking finding>
KEEP: the owned files, the contracts, and the writer model constraints.
```
