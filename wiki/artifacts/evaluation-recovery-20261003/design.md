# Evaluation completion contracts

The user released runner recovery, quality scoring, baselines, and the 30 by 3 benchmark.
Failure drivers and reporting are dependencies of those deliverables.

## Observation

An observation is a JSON object with case_id, condition, status, evidence_class,
model_id, turns, and optional reason. Model/reference conditions are tool_enabled, no_tool, and deterministic.
Primary domain fixtures use deterministic_fixture; controlled provider drivers use
controlled_fixture. Preserve these distinct matrix labels. Each completed conversation turn has status=completed,
elapsed_seconds, result, and calls. Each call has tool and input. Result is
the public run_chat result. Failed turns use static reason codes.
The observer MUST NOT read expected. Scorers MAY read expected.
Missing data MUST NOT count as a pass. A failed observation stays visible.

## Capture and evidence

Provider capture records bounded, sanitized tool inputs and result payloads.
It records usage, latency, and attempted provider-call counts.
It MUST NOT retain raw responses, intermediate model prose, or hidden reasoning.
Synthetic secret-marker leakage becomes a failed check and redacted content.
No credentials or real bank records enter the harness.
Evidence callbacks use the production evidence store in a dedicated local
database. Observations preserve snapshots and IDs for offline checks.
The report MUST name SQLite, PostgreSQL, Floci, or live Bedrock only when that
path actually ran. The benchmark does not claim live Plaid or Instacart.

## Scoring

Tool-schema validity covers calls across all turns. Corpus expected.model_tools
describes the last user turn. Argument and tool-choice checks use that scope.
Plan checks compare the final request and result with declared scenario facts.
Claims cover bounded public propositions. Unknown language remains unassessed.
Clarification checks verify that clarification is warranted and that no plan
was invented. Unsupported general-language claims cannot silently pass.
Metrics carry numerator, denominator, unknown count, scope, and condition.
The report separates fixture success from model task success.

## Conditions

The deterministic condition uses structured inputs and does not measure language.
The no-tool condition uses the same pinned model, source catalog, budget facts,
and user messages. It gets no expected fields and cannot execute application tools.
Its output is bounded structured JSON with a user-visible answer. Its prompt
differs only as necessary to describe the tool-disabled response contract.
Each condition records its own prompt hash. No-tool output is observed directly;
the harness MUST NOT fill missing model arithmetic with deterministic results.

## Execution

Keep the existing fixture run_evaluation API compatible.
Add an explicit batch command for the complete matrix and baseline conditions.
Each of 30 scenario IDs gets exactly repeats 1, 2, and 3 in the primary matrix.
Infrastructure failure fixtures stay distinct from model observations.
P04 uses a controlled fault and MUST NOT claim spontaneous model behavior.
A02 injects provider text on the model-visible data path and records its use.
P05 drives a dedicated PostgreSQL, worker, and Floci path with duplicate delivery.
The batch freezes corpus, catalog, application and condition prompts, model,
region, and actual inference settings. Outputs use exclusive file creation.
Cost remains unknown unless explicit dated model rates are supplied.
Do not alter gold or application behavior to make benchmark targets pass.

## Exact shared field names

Model observation conditions are `tool_enabled` and `no_tool`.
The structured reference condition is `deterministic`.
Do not use `model` as a condition; it is a matrix driver name.
A reference final-only observation has `final_only: true` and
`user_turn_count_original` equal to the original number of user messages.
It has one actual completed turn. Other model conditions require every turn.
All observations use `evidence_paths` as a list of actual path names.
Tool calls and tool_results are lists on each turn.
Observation and turn execution status is exactly `completed` on completion.
The public result has its own status: planned, needs_revision, clarification,
limit, or incomplete. A completed model call does not establish task success.
A02 proof is observation.injection_applied True plus injected_text_hash equal
to SHA256 of UTF-8 fixture_behavior.provider_text. A tool-result label is not proof.
Pending capture repair adds capture_incomplete. An incomplete scan leaves
no-leak status unknown, so it cannot certify a successful safe observation.

Fresh available budget equals max(0, monthly_limit_cents - posted_cents),
then the smaller explicit cap. Pending cents stay separate. Stale spending
with an explicit cap uses that cap as available and retains the stale warning.
Budget public fields are available_cents, pending_cents, stale, and warnings.

Task success uses complete execution, a passed outcome, a passed or inapplicable
plan assessment, passed tool assessment for tool_enabled, and passed or
inapplicable public-claim assessment. Any known failure fails the task.
Otherwise unknown required assessment makes task success unassessed.
The structured reference has structural success only, not language-task success.

## Slot and assessment fields

The new dispatch slot has case_id, repeat, condition, driver, elapsed_seconds,
status, observation, assessments, and report. This does not change legacy run_evaluation.
Top-level status describes execution: completed, failed, partial, or unassessed.
A completed execution with failed quality assessments remains completed.
Model and no-tool observations retain their observer fields. Their assessments
use the exact keys tools, plan, outcome, and claims. Each value is that scorer's
unaltered returned object. A deterministic reference has only assessments.plan.
For a fixture or controlled driver, report holds the actual returned report and
assessments.fixture holds status and exact-boolean checks. Passing fixture
assessments require nonempty checks. Failed or unassessed fixtures may have empty
checks when no guard evidence was obtained; retain that failure/unknown without
fabricating checks. Empty or malformed checks and an explicit report failure
cannot yield fixture status passed.
Fixture status is guard success, never language-task success.

Every slot has an observation metadata object so telemetry can group actual paths.
For fixture/controlled execution it contains case_id, condition, status,
evidence_class and evidence_paths copied from the actual driver report,
model_id=None, turns=[], and model_quality_applicable=False. It does not invent
model calls or tokens. Missing local services or boundary errors use unknown
evidence, empty turns, and a static reason. Scope remains unassessed/failed.
Summaries group by condition and observation.evidence_class. They distinguish
model/no_tool drivers from reference and fixture/controlled drivers. Never infer
language quality from a completed fixture or a fake provider's elapsed time.
