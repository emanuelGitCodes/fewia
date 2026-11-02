# Local conversation study: 2026-11-01

The prompt candidate is rejected. Keep the baseline prompt and strict validators.
The [phase record](../../../../wiki/phases/conversation-quality-20261101.md) records the repairs,
verification, live comparison, failures, and publication limits.

| Evidence | Source | Scope |
|---|---|---|
| `baseline/` | `a0f2ae81acc36ba33fa6c1c888fefda458d94d4c` | 22 live Nova turns |
| `candidate/` | `ecf8c5a3e6183c44dfbaedfd7b799fb73b4fd232` | 22 live Nova turns; rejected |
| `fixture/` | `155d1dc999bbf59f2ce962c4b8f8d82bdb84fc62` | Earlier 96-turn deterministic fixture |
| `live-smokes.json` | `155d1dc999bbf59f2ce962c4b8f8d82bdb84fc62` | Four real Nova turns with fixture plan, budget, and pending-proposal callback |
| `post-astra/fixture-plan-0dc5/` | `0dc50a6facf4d62350b6bf3492409cc9ba61c53a` | Repaired plan parser; full 96-turn deterministic fixture |

The baseline and candidate differ only in the ordinary-reply prompt paragraph.
`prompt-only-audit-v2.json` records the independent AST and prompt-boundary checks.
Its raw UTF-8 prompt hash uses a different encoding from the evaluation manifest's canonical JSON hash.
`paired-comparison.json` checks the fixed manifest fields and records the metric limits.
The proposal-warning repair is integrated after both frozen study arms. It is not a prompt-study variable.
Both fixture snapshots retain the baseline prompt hash.
The live smokes predate the later Astra parser repairs. The later repairs have local fixture coverage only.

Each completed arm retains `report.json`, `report.md`, `slots.jsonl`, and `completion.json`.
Completion hashes MUST match the copied report bytes. The records MUST remain immutable.
They contain hashes, counts, tool names, validated catalog inputs, and fact flags.
They MUST NOT contain raw replies, hidden reasoning, unmatched tokens, credentials, or bank records.
Probe answers are stored as hashes. The original local rejected-candidate branch remains available.
It is not part of the final implementation branch.

The live model is Nova 2 Lite in `us-east-1`, with temperature 0 and low reasoning effort.
The existing runtime has AWS guardrails and prompt caching off. No live guardrail claim is made.
The allowance is 48 logical chat turns. All 48 are used: 22 baseline, 22 candidate, and four checks.
The ledger records 82 top-level provider attempts. Those attempts are not additional logical chat turns.
`historical-nova2-rates.json` is the 2026-10-03 snapshot used for the paired cost estimates.
Those estimates are not a current bill. The four final checks do not have a priced-cost report.

`gates-main.log` retains the required command's actual output. Checks pass, but the aggregate
source count was 1,520 of 1,000 before the later parser repairs.
The work MUST remain a stack with the documented parents.
The proper item counts are 167, 242, and 193. Hosted CI has not run for these local branches.
The owner approved the private Astra transfers. Recovery and the earlier evaluation leaf have Astra approval.
The repaired plan source `0dc50a6f` has Astra approval after the fourth review.
The `post-astra/` directory retains subsequent findings, failed matrices, and repaired checks.
The repaired plan parser passes 233 independent cases and 17,139 backend tests, with one skipped test.
The final integration uses the unchanged evaluation patch after the repaired plan parser.
Its ignored supervisor records name the exact final gate and review SHA. No push or merge has run.
`post-astra/cli-usage-through-plan-review.json` records the usage cutoff before the final integration review.
