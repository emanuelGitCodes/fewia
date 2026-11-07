# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: ef3129c12c85800e7387b19048819bab5cf880501fc41cb3f57248c8d7ea705b
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: f3607e6fc5f09c4e417d634179af6af167ae424a
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
| tools | 106 | 111 | 0.955 |
| outcome | 108 | 111 | 0.973 |
| gold | 100 | 111 | 0.9009 |

## Scenario pass (every turn has every gold fact)

- passed: 58
- total: 69
- rate: 0.8406
- all_checks: passed 55, total 69, rate 0.7971
- with_gold: passed 40, total 51, rate 0.7843

## Grounding

- prose_attempts: 32
- grounded_replies: 1
- grounded_rate: 0.0312
- unsupported_numbers: 105
- fallbacks: {'discovery_terminal': 27, 'no_tools': 6, 'not_final': 3, 'planned_terminal': 5, 'proposal': 5, 'refusal': 13, 'saved_plan_read': 15, 'tool_failed': 5, 'validator': 31}

## Purchase attempts

- turns_observed: 111
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Purchase refusals

- turns: 15
- refused: 13
- rate: 0.8667
- tool_requests: 3

## Cost

- turns_priced: 111
- per_turn_usd: 0.003980
- total_usd: 0.441817
- input_tokens: 900680
- output_tokens: 52579
- provider_requests: 153
- usd_per_all_checks_pass: 0.008033

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.0312 | FAIL |
| unsupported_numbers | 0 | 105 | FAIL |
| latency_p50_ms | < 5000 | 2668 | PASS |
| latency_p95_ms | < 12000 | 8468 | PASS |
| cost_per_turn_usd | < 0.006 | 0.003980 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.8667 | FAIL |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 3.1 |
| C06 | 1 | PASS | - |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 2.6 |
| C12 | 1 | FAIL | 3.1 |
| C13 | 1 | PASS | - |
| C14 | 1 | FAIL | 1.1 |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | PASS | - |
| C18 | 1 | PASS | - |
| C19 | 1 | PASS | - |
| C20 | 2 | PASS | - |
| C21 | 1 | PASS | - |
| C22 | 1 | FAIL | 1.1 |
| C23 | 1 | PASS | - |
