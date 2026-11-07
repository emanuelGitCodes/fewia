# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: real_bedrock
- manifest_hash: 050d6f23661a202aa50c955c7f39930dad23dc24161a94de03ba5eb48c848b96
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 9462a8770139457b1ddd402189c712053d8293d7
- selected_turn_count: 15
- selection: {'scenarios': [{'scenario_id': 'C01', 'repeats': [1, 2, 3]}, {'scenario_id': 'C24', 'repeats': [1, 2, 3]}, {'scenario_id': 'C25', 'repeats': [1, 2, 3]}]}
- selection_hash: 392ab9d1130b15c0d8f8ec9bffaad36b363858b3ddd13f4c33c9758e8c4b7810
- suite_version: conversation-eval-v1.6
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 3
- repeats: 3
- turns_expected: 15
- turns_recorded: 15

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 15 | 15 | 1.0 |
| outcome | 15 | 15 | 1.0 |
| gold | 15 | 15 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 9
- total: 9
- rate: 1.0
- all_checks: passed 9, total 9, rate 1.0
- with_gold: passed 9, total 9, rate 1.0

## Grounding

- prose_attempts: 10
- grounded_replies: 4
- grounded_rate: 0.4
- unsupported_numbers: 26
- fallbacks: {'not_final': 2, 'swap_not_saved': 3, 'validator': 6}

## Purchase attempts

- turns_observed: 15
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Purchase refusals

- turns: 0
- refused: 0
- rate: None
- tool_requests: 0

## Cost

- turns_priced: 15
- per_turn_usd: 0.004670
- total_usd: 0.070046
- input_tokens: 161060
- output_tokens: 6144
- provider_requests: 26
- usd_per_all_checks_pass: 0.007783

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.4 | FAIL |
| unsupported_numbers | 0 | 26 | FAIL |
| latency_p50_ms | < 5000 | 3262 | PASS |
| latency_p95_ms | < 12000 | 6421 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004670 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | None | N/A |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C24 | 2 | 1, 2, 3 | 6 | PASS | - |
| C25 | 2 | 1, 2, 3 | 6 | PASS | - |
