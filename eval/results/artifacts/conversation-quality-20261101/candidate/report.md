# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: d884237cd6374302bc65f9a2dcde2597f0bf13b3189ef08dbabdaaf684e37be5
- evidence_class: real_bedrock
- manifest_hash: e76372e586562df9d8d9d9baad2262182f910ce79cc3b0c5eef8d1e579ae1c24
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: ecf8c5a3e6183c44dfbaedfd7b799fb73b4fd232
- selected_turn_count: 22
- selection: {'scenarios': [{'scenario_id': 'C01', 'repeats': [1, 2, 3]}, {'scenario_id': 'C08', 'repeats': [1, 2, 3]}, {'scenario_id': 'C09', 'repeats': [1, 2, 3]}, {'scenario_id': 'C11', 'repeats': [1]}, {'scenario_id': 'C16', 'repeats': [1]}]}
- selection_hash: 171209bdb5235c82b4d9f8c050317f2e54622d4118dad5262e61cbe71c309ab4
- suite_version: conversation-eval-v1.4
- system_prompt_hash: c7aefb41797c2d180782fe01cea9ac014401a4349f9a1ac9ab7797bd2f9b658c
- version: conversation-manifest-v1

## Counts

- scenarios: 5
- repeats: 3
- turns_expected: 22
- turns_recorded: 22

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 19 | 22 | 0.8636 |
| outcome | 21 | 22 | 0.9545 |
| gold | 16 | 22 | 0.7273 |

## Scenario pass (every turn has every gold fact)

- passed: 7
- total: 11
- rate: 0.6364

## Grounding

- prose_attempts: 14
- grounded_replies: 1
- grounded_rate: 0.0714
- unsupported_numbers: 26
- fallbacks: {'discovery_terminal': 3, 'no_tools': 4, 'planned_terminal': 1, 'validator': 13}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.0714 | FAIL |
| unsupported_numbers | 0 | 26 | FAIL |
| latency_p50_ms | < 5000 | 3050 | PASS |
| latency_p95_ms | < 12000 | 5983 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004649 | PASS |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C08 | 1 | 1, 2, 3 | 3 | PASS | - |
| C09 | 1 | 1, 2, 3 | 3 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | 1 | 9 | FAIL | 1.6, 1.7, 1.8 |
| C16 | 4 | 1 | 4 | PASS | - |
