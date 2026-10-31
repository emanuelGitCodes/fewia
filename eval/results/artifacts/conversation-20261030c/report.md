# Conversation evaluation

- corpus_sha256: b997d93c30f1b1e12ea496f417b3dccc95fb4f22f15a246ef0fe4add90bf676c
- evidence_class: real_bedrock
- manifest_hash: f4ab37e8830593b0ed6e4b2482d1097485ea969bac1857cda9530d15ed4c2428
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: b808dfb73c97e75dc75dfdc1d86ef3c99cccefb8
- version: conversation-manifest-v1

## Counts

- scenarios: 12
- repeats: 3
- turns_expected: 66
- turns_recorded: 66

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 51 | 66 | 0.7727 |
| outcome | 65 | 66 | 0.9848 |
| gold | 42 | 66 | 0.6364 |

## Grounding

- prose_attempts: 32
- grounded_replies: 13
- grounded_rate: 0.4062
- unsupported_numbers: 49
- fallbacks: {'no_tools': 6, 'not_final': 3, 'planned_terminal': 14, 'proposal': 4, 'refusal': 3, 'tool_failed': 4, 'validator': 19}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.4062 | FAIL |
| unsupported_numbers | 0 | 49 | FAIL |
| latency_p50_ms | < 5000 | 3406 | PASS |
| latency_p95_ms | < 12000 | 12226 | FAIL |
| cost_per_turn_usd | < 0.006 | 0.005301 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | PASS | - |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.1, 1.6, 1.7, 1.8, 2.7, 2.8, 3.3, 3.7, 3.8 |
| C12 | 1 | PASS | - |
