# Conversation evaluation

- catalog_hash: 048564e14f4858ec205c9df6e0df36f3f30e723e3e922b19c98f1a5581c1acf4
- corpus_sha256: a38a185faaa708c8bfe7ec99a6ea4ab82ad7ae78257d254757ab244e13b275ef
- evidence_class: real_bedrock
- manifest_hash: aa620f1a8c97e56d3925e2209853dd5db9f49bba40be9e02a0e55a7e35c3e0a5
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: b5032245b8d2fc112b1da768c3e256478febd3bc
- suite_version: conversation-eval-v1.3
- system_prompt_hash: eed09e8832cc3f5d9ab3ec3ea1c2fb52774bc279924150b95e0542d785eb9a22
- version: conversation-manifest-v1

## Counts

- scenarios: 18
- repeats: 3
- turns_expected: 93
- turns_recorded: 93

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 79 | 93 | 0.8495 |
| outcome | 91 | 93 | 0.9785 |
| gold | 67 | 93 | 0.7204 |

## Scenario pass (every turn has every gold fact)

- passed: 35
- total: 54
- rate: 0.6481

## Grounding

- prose_attempts: 39
- grounded_replies: 9
- grounded_rate: 0.2308
- unsupported_numbers: 91
- fallbacks: {'discovery_terminal': 24, 'no_tools': 6, 'not_final': 3, 'planned_terminal': 11, 'proposal': 5, 'refusal': 3, 'tool_failed': 2, 'validator': 30}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.2308 | FAIL |
| unsupported_numbers | 0 | 91 | FAIL |
| latency_p50_ms | < 5000 | 3145 | PASS |
| latency_p95_ms | < 12000 | 8227 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004677 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1, 2.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.1, 1.7, 2.1, 2.7, 2.8, 3.1, 3.3, 3.6, 3.7, 3.8 |
| C12 | 1 | PASS | - |
| C13 | 1 | PASS | - |
| C14 | 1 | FAIL | 2.1 |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C18 | 1 | PASS | - |
