# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: d884237cd6374302bc65f9a2dcde2597f0bf13b3189ef08dbabdaaf684e37be5
- evidence_class: real_bedrock
- manifest_hash: e64c45c64dfdbb058bbf9fc9a12d1b4b81ed69d235b447f0eaa837bf46478a7b
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: a0f2ae81acc36ba33fa6c1c888fefda458d94d4c
- selected_turn_count: 22
- selection: {'scenarios': [{'scenario_id': 'C01', 'repeats': [1, 2, 3]}, {'scenario_id': 'C08', 'repeats': [1, 2, 3]}, {'scenario_id': 'C09', 'repeats': [1, 2, 3]}, {'scenario_id': 'C11', 'repeats': [1]}, {'scenario_id': 'C16', 'repeats': [1]}]}
- selection_hash: 171209bdb5235c82b4d9f8c050317f2e54622d4118dad5262e61cbe71c309ab4
- suite_version: conversation-eval-v1.4
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 5
- repeats: 3
- turns_expected: 22
- turns_recorded: 22

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 21 | 22 | 0.9545 |
| outcome | 22 | 22 | 1.0 |
| gold | 18 | 22 | 0.8182 |

## Scenario pass (every turn has every gold fact)

- passed: 7
- total: 11
- rate: 0.6364

## Grounding

- prose_attempts: 14
- grounded_replies: 3
- grounded_rate: 0.2143
- unsupported_numbers: 27
- fallbacks: {'discovery_terminal': 3, 'no_tools': 3, 'planned_terminal': 1, 'tool_failed': 1, 'validator': 11}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.2143 | FAIL |
| unsupported_numbers | 0 | 27 | FAIL |
| latency_p50_ms | < 5000 | 4208 | PASS |
| latency_p95_ms | < 12000 | 11380 | PASS |
| cost_per_turn_usd | < 0.006 | 0.005142 | PASS |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C08 | 1 | 1, 2, 3 | 3 | PASS | - |
| C09 | 1 | 1, 2, 3 | 3 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | 1 | 9 | FAIL | 1.7 |
| C16 | 4 | 1 | 4 | PASS | - |
