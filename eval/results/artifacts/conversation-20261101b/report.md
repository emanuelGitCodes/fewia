# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: d884237cd6374302bc65f9a2dcde2597f0bf13b3189ef08dbabdaaf684e37be5
- evidence_class: real_bedrock
- manifest_hash: 7bd012d4121e6ab2c93ba625b0dc526cd49d09e8e9024e973aa92eccf7789493
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: f21f8980b46b5ca3ae8b9816521fd13b108f5bb3
- suite_version: conversation-eval-v1.4
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 19
- repeats: 3
- turns_expected: 96
- turns_recorded: 96

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 86 | 96 | 0.8958 |
| outcome | 93 | 96 | 0.9688 |
| gold | 78 | 96 | 0.8125 |

## Scenario pass (every turn has every gold fact)

- passed: 40
- total: 57
- rate: 0.7018

## Grounding

- prose_attempts: 43
- grounded_replies: 13
- grounded_rate: 0.3023
- unsupported_numbers: 77
- fallbacks: {'discovery_terminal': 27, 'no_tools': 3, 'not_final': 4, 'planned_terminal': 7, 'proposal': 6, 'refusal': 5, 'tool_failed': 1, 'validator': 30}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.3023 | FAIL |
| unsupported_numbers | 0 | 77 | FAIL |
| latency_p50_ms | < 5000 | 3151 | PASS |
| latency_p95_ms | < 12000 | 11425 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004760 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 3.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | FAIL | 3.2 |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.7, 2.6, 2.7, 3.7 |
| C12 | 1 | FAIL | 1.1 |
| C13 | 1 | PASS | - |
| C14 | 1 | FAIL | 2.1 |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | PASS | - |
| C18 | 1 | PASS | - |
| C19 | 1 | PASS | - |
