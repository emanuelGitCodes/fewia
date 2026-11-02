# Conversation quality follow-up

This is a local work record for 2026-11-01. The follow-up is not published.
PR [469](https://github.com/emanuelGitCodes/fewia/pull/469) remains open and unmerged
at `8cee7e1a`. Its base is `34642bf1`. Its hosted checks do not cover these new branches.

## Conversation repairs

- Checked search exhaustion now returns `There are no more matching meals.`
  A changed restriction starts a fresh search. An explicit restart retains the saved filters.
- A guardrail decline retains the incoming checked search state. It returns no proposal card.
  Stored-job history and evaluation history omit the blocked exchange.
- Clear dietary questions about saved meals use the selected plan and catalog facts.
  An ambiguous meal or unsupported characteristic gets a clarification.
  Dairy-free ingredients remain distinct from vegan. Ingredient checks do not certify medical,
  allergy, or cross-contact safety.
- A visible proposal has the matching server explanation. A failed later proposal retains one
  warning across successful reads. A new successful proposal replaces the old proposal and warning.
  A refusal, guardrail decline, or incomplete reply returns no proposal card.

| Item | Local source | Stack parent | Added source lines | Backend tests |
|---|---|---|---|---|
| Recovery and exhaustion | `6f86836b` | `8cee7e1a` | 167 | 15,622 passed; 1 skipped |
| Plan facts and proposal replies | `0dc50a6f` | `6f86836b` | 242 | 17,139 passed; 1 skipped |
| Selected evaluation support, earlier leaf | `e10dd583` | `ccaf7c20` | 193 | 15,708 passed; 1 skipped |

The repair gates also pass Ruff and strict mypy. Each reports one existing warning.
Coordinator checks pass 10/10. The first nine fail on the original parent.
The added proposal-warning check fails before `ccaf7c20` and passes after it.
The latest current-plan repair passes all 233 independent question cases at `0dc50a6f`.
They cover clarification, preserved named-meal facts, budget routing, and three review regression classes.
The full fixture at that source passes 96/96 tool, outcome, and gold checks,
plus 57/57 scenario repeats. The earlier selected fixture passes 22/22 and 11/11 repeats.
The final branch `codex/conversation-quality-final` adds the unchanged 193-line evaluation patch after `0dc50a6f`.
Its final gate and review records use its exact committed SHA.

The earlier `--base main` gates pass backend and frontend checks at `155d1dc9`.
They print `LINES 1520/1000` and `RESULT PASS`. The later parser repairs increase that count.
That result does not make the aggregate
range fit the PR limit. The work MUST remain a follow-up stack. It MUST NOT become one PR on main.
The proper item ranges are 167, 242, and 193 added source lines.

Browser checks use responses from the revised backend with a fixture model.
They cover selected-plan facts, matching proposal cards, search exhaustion, and guardrail declines.
Desktop and 390-pixel mobile views show no horizontal overflow. The final browser console has no errors.
These checks do not prove a deployed backend or live AWS guardrail behavior.
Additional desktop and mobile checks at `ff51cf20` show clarification replies with no search or proposal cards.
The 390-pixel view has no overflow. The browser console has no errors or warnings.
These fixture-rendering checks predate the last two parser repairs. The new regression matrices test those repairs locally.

## Answer-quality experiment

The owner approved at most 48 additional live Nova chat turns. The selected cohort uses
22 turns per arm, with four turns reserved for focused behavior checks. Selection and turn-cap
validation run before the live provider is created. The normal evaluation still uses all 96 slots.

The baseline completed 22 turns at `a0f2ae81`. The candidate completed 22 at `ecf8c5a3`.
Only the ordinary-reply prompt paragraph differs. An independent AST check confirms that
the remaining code and prompt text match. Corpus, selection, catalog, model, and runtime settings match.
The later proposal-warning repair stays outside both frozen study arms.
Four additional live checks at source `155d1dc9` pass: selected-meal vegan facts,
selected-meal dairy ingredient facts, exhausted continuation, and matching proposal text/operations.
They use a fixture plan, budget, and pending-proposal callback with the real Nova provider.
They do not apply a proposal or make retailer writes. All 48 approved chat turns are used.
These checks predate the later Astra parser repairs. Those repairs use local provider fixtures.
They have no additional live Nova evidence.

| Measure | Baseline | Candidate |
|---|---|---|
| Validated prose / prose attempts | 3/14 | 1/14 |
| Tool checks | 21/22 | 19/22 |
| Outcome checks | 22/22 | 21/22 |
| Retrieved gold facts | 18/22 | 16/22 |
| Scenario repeats with all gold facts | 7/11 | 7/11 |
| Unsupported numeric tokens rejected | 27 | 26 |
| Validator fallbacks | 11 | 13 |
| Median / p95 latency | 4,208 / 11,380 ms | 3,050 / 5,983 ms |
| Estimated USD per turn, historical rates | 0.005142 | 0.004649 |

The candidate is rejected. The final stack keeps the baseline prompt and strict validators.
The candidate passes local gates, but its live quality is worse. Faster replies do not offset
the lower tool, outcome, gold, and prose results. The 99% grounding target remains unmet.
Strict validation rejected unsupported numbers and used template fallbacks.
Those counts do not mean the rejected tokens reached the user.
Accepted replies contain 49-64 words in the baseline and 60 words in the candidate.
All accepted replies contain digits and money strings. The audit finds no tested generic placeholders.
That audit does not establish complete answer quality.

The baseline misses gold checks on all three medical-question repeats and C11 turn 7.
The candidate misses all three medical repeats and C11 turns 6, 7, and 8.
These gaps remain open. The recorded artifacts MUST remain immutable.

Gold checks measure retrieved tool facts, not complete prose relevance.
Answer-length and numeric-content checks do not prove complete semantic usefulness.
The cohort is a small exploratory comparison. The older 13/43 result used a different cohort.
Cost estimates use the recorded 2026-10-03 price snapshot, not a current invoice.
The existing runtime has prompt caching and AWS guardrails off.
Guardrail recovery has deterministic coverage only.

The [experiment artifacts](../../eval/results/artifacts/conversation-quality-20261101/README.md)
retain both completed arms, their manifests and slot records, the comparison, and the allowance count.

## Verification findings

The recovery checks first found an inconsistent pair of active and exhausted states, then an exact
context-key assertion. Both were repaired. Coordinator probes found the lost proposal-failure warning
after the first integrated gates passed. The additional regression now detects that failure.
Prompt checks caught budget overflow and removed routing wording before any candidate live calls.
The final prompt-only candidate passes 2,986 focused tests and full gates at `ecf8c5a3`.
It uses 16,977 of 17,000 prompt/schema characters. The retained baseline uses 16,537.

The existing `StarletteDeprecationWarning` about httpx and `starlette.testclient` remains.
This work does not change dependencies. Test and browser harness corrections are separate from
application defects. Browser fixtures use the observed complete pantry and the installed component roles.
The first evidence commit placed generated records outside `artifacts/`, so the source counter included
them and reported 2,216 lines for the leaf. The records now use the standard artifact directory.
Their completed report and slot bytes remain unchanged. No application code changed in this correction.

Sol, Terra, and Luna writers all used `xhigh`. The 18 CLI runs record 19,959,655 input tokens,
including 18,981,248 cached tokens, and 296,168 output tokens, including 198,940 reasoning tokens.
Their aggregate CLI time is 2,987.462 seconds. This sum is not end-to-end wall time.
Native coordination and advice are outside these historical writer totals.
The later repair and review usage has a separate snapshot.
Through the approved plan repair, 28 writer runs record 27,946,653 input tokens and 391,930 output tokens.
Input includes 26,457,984 cached tokens. Output includes 243,317 reasoning tokens.
The six reviews add 4,068,434 input tokens and 17,746 output tokens.
All 34 recorded CLI runs total 5,864.277 seconds. This is not end-to-end wall time.
The final integration review follows this cutoff. One blocked launcher has unknown usage outside these totals.

Astra found ambiguous singular meal questions and unsupported compound properties after the first gates passed.
Later rounds found unknown multiword subjects and descriptions containing `in`, `with`, or `without`.
One parser repair also broke the established monthly-budget route in the full fixture.
The writer then escalated from Terra to Sol at `xhigh`.
The coordinator retains the failed and repaired matrices. The checks preserve known named-meal facts and budget routing.
Unsupported descriptions need clarification before any model-requested search or proposal dispatch.
Provider assessment and guardrail checks still run first.

## Review and publication

The owner approved private Astra transfers for all three follow-ups.
Astra approves recovery at `6f86836b` and the earlier evaluation-support leaf at `e10dd583`.
Astra approves the repaired current-plan source at `0dc50a6f` after three blocking reviews.
The owner authorized further repair rounds. The successful fourth review follows the repaired 233-case matrix.
The final integration has separate gate and review records under its exact committed head.
Those records remain in the ignored supervisor directories and the local durable evidence bundle.
The follow-up stack has no hosted CI result. No push or merge has run for this follow-up.
