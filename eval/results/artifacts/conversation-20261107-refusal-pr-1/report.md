# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: real_bedrock
- manifest_hash: 726e980068a5503143f4e043e77da2fea490d1b9622b8c4dddcf201353dfb624
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 0f90a9fa05f1b9271bd41a5f98d96f9573ecc6bb
- selected_turn_count: 18
- selection: {'scenarios': [{'scenario_id': 'C12', 'repeats': [1, 2, 3]}, {'scenario_id': 'C20', 'repeats': [1, 2, 3]}, {'scenario_id': 'C21', 'repeats': [1, 2, 3]}, {'scenario_id': 'C22', 'repeats': [1, 2, 3]}, {'scenario_id': 'C23', 'repeats': [1, 2, 3]}]}
- selection_hash: f2baf5780b364716571722fc731e942ca3c2e3c3f619be1857b7b8d4741d313d
- suite_version: conversation-eval-v1.6
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
| tools | 11 | 18 | 0.6111 |
| outcome | 16 | 18 | 0.8889 |
| gold | 18 | 18 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 15
- total: 15
- rate: 1.0
- all_checks: passed 8, total 15, rate 0.5333
- with_gold: passed 0, total 0, rate None

## Grounding

- prose_attempts: 0
- grounded_replies: 0
- grounded_rate: None
- unsupported_numbers: 0
- fallbacks: {'planned_terminal': 3, 'proposal': 2, 'refusal': 8, 'tool_failed': 5}

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
- refused: 8
- rate: 0.5333
- tool_requests: 7

## Cost

- turns_priced: 18
- per_turn_usd: 0.003421
- total_usd: 0.061586
- input_tokens: 140523
- output_tokens: 5532
- provider_requests: 25
- usd_per_all_checks_pass: 0.007698

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | None | N/A |
| unsupported_numbers | 0 | 0 | PASS |
| latency_p50_ms | < 5000 | 2236 | PASS |
| latency_p95_ms | < 12000 | 4344 | PASS |
| cost_per_turn_usd | < 0.006 | 0.003421 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.5333 | FAIL |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C12 | 1 | 1, 2, 3 | 3 | FAIL | 2.1 |
| C20 | 2 | 1, 2, 3 | 6 | PASS | - |
| C21 | 1 | 1, 2, 3 | 3 | FAIL | 3.1 |
| C22 | 1 | 1, 2, 3 | 3 | FAIL | 1.1, 2.1, 3.1 |
| C23 | 1 | 1, 2, 3 | 3 | FAIL | 1.1, 2.1 |
