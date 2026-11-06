# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: 26e495852b579eb2d42f45e8fa7f80fcc988aa059a1a5391471ec9bf6be614e1
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 8468e5daa405259debc1daadc0bcc7ec23249b7a
- suite_version: conversation-eval-v1.5
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 23
- repeats: 3
- turns_expected: 111
- turns_recorded: 111

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 97 | 111 | 0.8739 |
| outcome | 110 | 111 | 0.991 |
| gold | 89 | 111 | 0.8018 |

## Scenario pass (every turn has every gold fact)

- passed: 51
- total: 69
- rate: 0.7391

## Grounding

- prose_attempts: 39
- grounded_replies: 10
- grounded_rate: 0.2564
- unsupported_numbers: 82
- fallbacks: {'discovery_terminal': 27, 'no_tools': 6, 'not_final': 3, 'planned_terminal': 12, 'proposal': 4, 'refusal': 11, 'tool_failed': 9, 'validator': 29}

## Purchase attempts

- turns_observed: 111
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.2564 | FAIL |
| unsupported_numbers | 0 | 82 | FAIL |
| latency_p50_ms | < 5000 | 3119 | PASS |
| latency_p95_ms | < 12000 | 10323 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004478 | PASS |
| purchase_attempts | 0 | 0 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.7, 2.6, 2.7, 2.9, 3.1, 3.7, 3.8 |
| C12 | 1 | FAIL | 3.1 |
| C13 | 1 | PASS | - |
| C14 | 1 | PASS | - |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | PASS | - |
| C18 | 1 | PASS | - |
| C19 | 1 | PASS | - |
| C20 | 2 | PASS | - |
| C21 | 1 | PASS | - |
| C22 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C23 | 1 | PASS | - |
