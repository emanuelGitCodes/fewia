# 0015 — Writer routing by difficulty

- Date: 2026-09-30
- Status: accepted

## Decision

The coordinator picks one writer model per work item from the difficulty of
the item. Three models write code: `gpt-6-luna`, `grok-4.6`, and
`gpt-6.1-sol`. No other model writes code.

| Difficulty | Writer | Effort |
|---|---|---|
| Simple: configuration, one narrow change, no new contract | `gpt-6-luna` | `low` |
| Harder, fully specified, follows a known pattern | `grok-4.6` | `low` or `medium` |
| Harder, ambiguous, cross-cutting, security, or test-gate work | `gpt-6.1-sol` | `medium` or `high` |

Every writer run uses `--only --model MODEL --effort LEVEL`. Grok never
receives an effort above `medium`. Sol never receives an effort below
`medium` or above `high`.

The loop does not change. The writer edits files. The coordinator commits,
runs the gates and the review command, reads the diff, and decides. When the
work is not good, the coordinator writes a repair brief with its findings and
sends the work back to the writer.

This decision replaces the writer order in
[0011](0011-dynamic-delegated-effort.md). It keeps the tiers from
[0014](0014-tiered-delegation.md).

## Options considered

- One fixed writer order for every item. Sol then Luna spent a high-effort
  model on one-line changes.
- Complexity class alone picks the effort. The class does not say which
  model fits the item.

## Reason

The user asked for a cheap writer on simple items and a strong writer on hard
items, with the coordinator free to choose between Grok and Sol.

## Consequences

- The brief and the loop ledger name the writer model and the effort.
- `gpt-5.3-codex-spark` and Sonnet do not write code.
- The review command still picks a review model other than the writer.
