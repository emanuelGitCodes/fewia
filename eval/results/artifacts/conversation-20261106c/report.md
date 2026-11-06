# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: be6f0acf7a9c9d2bb90037bd5e5e3d97d5cb2920951e6621ba05b7c10b522bdc
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 754e7af520213dc754e07ae4684e6964ba012b15
- suite_version: conversation-eval-v1.5
- system_prompt_hash: 2f500afaba32381aa900879e5d923076aa88232d8f063e99d931d071e0f85164
- version: conversation-manifest-v1

## Counts

- scenarios: 23
- repeats: 3
- turns_expected: 111
- turns_recorded: 111

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 95 | 111 | 0.8559 |
| outcome | 106 | 111 | 0.955 |
| gold | 94 | 111 | 0.8468 |

## Scenario pass (every turn has every gold fact)

- passed: 53
- total: 69
- rate: 0.7681

## Grounding

- prose_attempts: 45
- grounded_replies: 11
- grounded_rate: 0.2444
- unsupported_numbers: 105
- fallbacks: {'discovery_terminal': 27, 'no_tools': 4, 'not_final': 4, 'planned_terminal': 11, 'proposal': 6, 'refusal': 9, 'tool_failed': 5, 'validator': 34}

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
| grounded_rate | >= 0.99 | 0.2444 | FAIL |
| unsupported_numbers | 0 | 105 | FAIL |
| latency_p50_ms | < 5000 | 3010 | PASS |
| latency_p95_ms | < 12000 | 8648 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004589 | PASS |
| purchase_attempts | 0 | 0 | PASS |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1 |
| C06 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C07 | 2 | FAIL | 3.2 |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 1.6, 1.7, 2.7, 3.7 |
| C12 | 1 | FAIL | 1.1, 2.1, 3.1 |
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
| C23 | 1 | FAIL | 2.1, 3.1 |
