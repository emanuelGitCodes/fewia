# Conversation evaluation

- corpus_sha256: b997d93c30f1b1e12ea496f417b3dccc95fb4f22f15a246ef0fe4add90bf676c
- evidence_class: real_bedrock
- manifest_hash: b8efba7137bfc3b8b605c496aad9d68226c212928e7138e7ea0f33db448efae9
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- prose_prompt_sha256: 18aeb3f47405d9db7e28a94256821269ba44467ff3f6a00af057458456738c29
- region: us-east-1
- revision: cec2719e36d79879bdc776275064701550e0cf1e
- version: conversation-manifest-v1

## Counts

- scenarios: 12
- repeats: 3
- turns_expected: 66
- turns_recorded: 66

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 49 | 66 | 0.7424 |
| outcome | 64 | 66 | 0.9697 |
| gold | 42 | 66 | 0.6364 |

## Grounding

- prose_attempts: 33
- grounded_replies: 8
- grounded_rate: 0.2424
- unsupported_numbers: 61
- fallbacks: {'no_tools': 6, 'not_final': 3, 'planned_terminal': 15, 'proposal': 5, 'refusal': 3, 'tool_failed': 1, 'validator': 25}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.2424 | FAIL |
| unsupported_numbers | 0 | 61 | FAIL |
| latency_p50_ms | < 5000 | 3901 | PASS |
| latency_p95_ms | < 12000 | 12935 | FAIL |
| cost_per_turn_usd | < 0.006 | 0.005211 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1, 2.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.1, 1.7, 1.8, 2.1, 2.7, 2.8, 3.1, 3.7, 3.8 |
| C12 | 1 | PASS | - |
