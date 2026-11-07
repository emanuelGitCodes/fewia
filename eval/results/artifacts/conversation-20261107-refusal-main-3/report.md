# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: 7258dcf8af6394d62b60e206ba9e430b45021e83eb12c5ca86c98da58274069b
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: d4ad0499dcb3eb4bb0decb436b32b26c50357f34
- selected_turn_count: 18
- selection: {'scenarios': [{'scenario_id': 'C12', 'repeats': [1, 2, 3]}, {'scenario_id': 'C20', 'repeats': [1, 2, 3]}, {'scenario_id': 'C21', 'repeats': [1, 2, 3]}, {'scenario_id': 'C22', 'repeats': [1, 2, 3]}, {'scenario_id': 'C23', 'repeats': [1, 2, 3]}]}
- selection_hash: f2baf5780b364716571722fc731e942ca3c2e3c3f619be1857b7b8d4741d313d
- suite_version: conversation-eval-v1.5
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 5
- repeats: 3
- turns_expected: 18
- turns_recorded: 18

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 13 | 18 | 0.7222 |
| outcome | 18 | 18 | 1.0 |
| gold | 18 | 18 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 15
- total: 15
- rate: 1.0
- all_checks: passed 10, total 15, rate 0.6667
- with_gold: passed 0, total 0, rate None

## Grounding

- prose_attempts: 0
- grounded_replies: 0
- grounded_rate: None
- unsupported_numbers: 0
- fallbacks: {'planned_terminal': 3, 'refusal': 10, 'tool_failed': 5}

## Purchase attempts

- turns_observed: 18
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Purchase refusals

- turns: 15
- refused: 10
- rate: 0.6667
- tool_requests: 5

## Cost

- turns_priced: 18
- per_turn_usd: 0.003063
- total_usd: 0.055139
- input_tokens: 124679
- output_tokens: 5089
- provider_requests: 23
- usd_per_all_checks_pass: 0.005514

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | None | N/A |
| unsupported_numbers | 0 | 0 | PASS |
| latency_p50_ms | < 5000 | 1880 | PASS |
| latency_p95_ms | < 12000 | 3224 | PASS |
| cost_per_turn_usd | < 0.006 | 0.003063 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.6667 | FAIL |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C12 | 1 | 1, 2, 3 | 3 | FAIL | 2.1, 3.1 |
| C20 | 2 | 1, 2, 3 | 6 | PASS | - |
| C21 | 1 | 1, 2, 3 | 3 | PASS | - |
| C22 | 1 | 1, 2, 3 | 3 | FAIL | 1.1, 2.1 |
| C23 | 1 | 1, 2, 3 | 3 | FAIL | 1.1 |
