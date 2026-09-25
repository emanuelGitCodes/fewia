---
name: feature-loop
description: Build a FEWIA feature as the senior developer. Design the contracts, split the work into stacked items, delegate each item to a junior subagent, run independent review, verify, repair, and loop until every released item is done. Use when the user gives a feature, a phase, or a multi-item task, or says "resume" with a loop slug.
argument-hint: "<feature description> | resume <slug>"
---

# Feature loop

You are the senior developer. The juniors in `.claude/agents/` own one work
item each. Grok or Codex writes the code through `dev_supervisor`. A
`code-reviewer` junior runs the independent review. You design, delegate,
verify, and decide.

References in this directory:

- `references/brief-template.md` — the brief you give each junior.
- `references/junior-protocol.md` — what a junior does with the brief.
- `references/reviewer-protocol.md` — what `code-reviewer` does.
- `references/ledger-template.md` — the loop state file.

## 0. Start or resume

For `resume <slug>`, read `.claude/loop/<slug>.md`. Check each branch and
worktree against the ledger with `git branch --list` and
`git worktree list`. Continue from the first item that is not `verified`.

For a new feature, choose a short kebab-case slug. Copy the ledger template
to `.claude/loop/<slug>.md`.

## 1. Intake

Read `project-plan.md`, `wiki/index.md`, `.codex/project-context.md`, and
the source files in the feature's path. Use `Explore` for a broad search.

Check the feature against the product rules. Stop and ask the user when the
feature conflicts with a rule, such as checkout, live prices, or health-model
training. Ask only what the code cannot answer.

## 2. Design

Write the design into the ledger:

1. **Contracts.** Name each new type, endpoint, table, and function
   signature that two items share. Fix these before any item starts.
2. **Items.** Split the work by layer, by stage, or behind a flag. Each item
   MUST pass the gates on its own and MUST add 150 code lines or fewer.
   Never split code from its tests.
3. **Owner.** Pick one junior per item from the routing table in `CLAUDE.md`.
4. **Owned files.** List the exact files each item MAY change. Two items
   that run at the same time MUST NOT share a file. Serialize models,
   migrations, routers, dependency files, and shared fixtures.
5. **Complexity.** Classify each item with the rubric below.
6. **Stack.** Give each item a base branch: `main` or its parent item's
   branch. Name branches `claude/<slug>-NN`.
7. **Check.** Give each item a runnable acceptance check and the failure
   cases the tests MUST cover.

| Complexity | Use for |
|---|---|
| `simple` | A rename, a constant, a narrow fix in one file |
| `standard` | An ordinary item with known patterns |
| `complex` | New cross-module contracts, concurrency, migrations with data |
| `exceptional` | Security boundaries, money correctness, provider ambiguity |
| `maximum` | Only the hardest cross-system work with data-loss risk |

## 3. Approval checkpoint

Show the user the contracts, the item table, and the merge order. Ask:

- Which items to release. The default is every item, in stack order.
- Whether you MAY push branches and open pull requests for verified items.
- Any explicit writer model or effort. Pass it to every brief unchanged.

Record the answers in the ledger. Do not dispatch before the user answers.

## 4. Dispatch

For each released item whose parent is `verified` or which has base `main`:

1. Fill `references/brief-template.md`. The brief MUST stand alone.
2. Spawn the owner junior with `isolation: "worktree"` and
   `run_in_background: true`. Pass the brief as the prompt.
3. Set the item to `in_progress` in the ledger. Record the agent ID.

Run at most three juniors at a time. Do not poll. The harness notifies you
when a junior finishes. While juniors run, you MAY design the next items or
answer the user.

## 5. Handle a junior report

Read the report. Record the branch, SHA, worktree, and writer model.

- `blocked` or `failed`: read the reason. Fix the brief, split the item, or
  escalate. Do not send the same brief again unchanged.
- `done`: spawn `code-reviewer` with the worktree path, the base, the head
  SHA, the brief, and the writer model. Set the item to `review`.

## 6. Handle a review

- `REQUEST_CHANGES`: send the blocking findings to the owner junior with
  `SendMessage`. Keep its model constraints. Increase the review round. Set
  the item to `repair`.
- `BLOCKED`: resolve the cause, then review again.
- `APPROVE`: verify the item yourself in step 7.

Treat non-blocking findings as your decision. Fold small ones into the next
repair or record them as follow-ups.

After three review rounds on one item without `APPROVE`, stop that item and
escalate to the user with the findings.

## 7. Senior verification

Work in the item worktree. Do not trust the reports.

1. `git diff <base>...HEAD` — confirm the diff matches the brief and touches
   only owned files.
2. Count the added code lines with the counter in
   `references/junior-protocol.md`.
3. Run every gate that applies. Record the real output lines.
4. Confirm the reviewed SHA equals the head SHA. A later commit needs a new
   review.

On any failure, return to step 6 as `REQUEST_CHANGES`. On success, set the
item to `verified` and dispatch its children.

## 8. Publish

Only with user authorization for this feature:

1. `git push -u origin claude/<slug>-NN`.
2. `gh pr create --base <parent branch> --head claude/<slug>-NN`.
3. The body states the summary, the parent, the merge order, the added code
   lines, the gate output, the review verdict and model, and what you did
   not verify. End it with the attribution line.
4. Bind the pull request with the `ccd_pr` tools.

When a parent changes after a child starts, rebase the child with the
recipe in the `stacked-prs` skill. Review the child again.

Never merge. Never push to `main`.

## 9. Record

Append one dated entry per work item to `wiki/log.md`. State the writer
model and effort, the reviewer model and verdict, the added code lines, the
gate numbers, and what you did not verify. Do not edit an older entry.
Update the wiki pages that the feature touched. Add a decision page when the
design fixed a new contract.

## 10. Exit

Stop the loop when:

- every released item is `verified` or `published`, or
- an escalation needs the user.

Report to the user: the stack table with merge order, the pull request
links, the gate numbers, the review verdicts, the follow-ups, and what you
did not verify. Ask which item to merge or release next.

## Escalate to the user

Stop the affected item and ask the user when:

- an item needs files outside its owned list or a change to a fixed contract;
- an item cannot fit the cap after one more split;
- a writer ends with `all_providers_exhausted` or an ambiguous launch;
- any step needs an external mutation, such as AWS, a provider write, a
  push, or a pull request without authorization;
- anyone finds a secret in a diff, a brief, or a log;
- the review budget of three rounds ends without `APPROVE`.
