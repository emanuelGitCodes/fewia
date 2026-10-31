# Conversation evaluation

- corpus_sha256: b997d93c30f1b1e12ea496f417b3dccc95fb4f22f15a246ef0fe4add90bf676c
- evidence_class: real_bedrock
- manifest_hash: a9676ae7f6dee03ea71a825e641258149b82aeb0761a501e824fd8005666fe4a
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 95cfbea3a48a9a2a0bc6a6c0fb2ce83e24c12eb8
- version: conversation-manifest-v1

## Counts

- scenarios: 12
- repeats: 3
- turns_expected: 66
- turns_recorded: 66

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 54 | 66 | 0.8182 |
| outcome | 64 | 66 | 0.9697 |
| gold | 44 | 66 | 0.6667 |

## Grounding

- prose_attempts: 36
- grounded_replies: 9
- grounded_rate: 0.25
- unsupported_numbers: 59
- fallbacks: {'no_tools': 4, 'not_final': 3, 'planned_terminal': 10, 'proposal': 5, 'refusal': 5, 'tool_failed': 3, 'validator': 27}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.25 | FAIL |
| unsupported_numbers | 0 | 59 | FAIL |
| latency_p50_ms | < 5000 | 4647 | PASS |
| latency_p95_ms | < 12000 | 16362 | FAIL |
| cost_per_turn_usd | < 0.006 | 0.005688 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 2.1, 3.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | FAIL | 1.2, 3.2 |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.6, 1.7, 1.8, 2.6, 2.7, 2.8, 3.7, 3.8 |
| C12 | 1 | PASS | - |
