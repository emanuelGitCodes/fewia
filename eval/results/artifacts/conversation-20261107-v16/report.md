# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: real_bedrock
- manifest_hash: a3e74e10910a64352d38a34dc2999206bc2a9dababba053858203d96af240032
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 0f90a9fa05f1b9271bd41a5f98d96f9573ecc6bb
- suite_version: conversation-eval-v1.6
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 25
- repeats: 3
- turns_expected: 123
- turns_recorded: 123

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 112 | 123 | 0.9106 |
| outcome | 118 | 123 | 0.9593 |
| gold | 113 | 123 | 0.9187 |

## Scenario pass (every turn has every gold fact)

- passed: 65
- total: 75
- rate: 0.8667
- all_checks: passed 56, total 75, rate 0.7467
- with_gold: passed 47, total 57, rate 0.8246

## Grounding

- prose_attempts: 43
- grounded_replies: 7
- grounded_rate: 0.1628
- unsupported_numbers: 108
- fallbacks: {'discovery_terminal': 27, 'no_tools': 4, 'not_final': 5, 'planned_terminal': 3, 'proposal': 8, 'refusal': 10, 'saved_plan_read': 15, 'swap_not_saved': 3, 'tool_failed': 5, 'validator': 36}

## Purchase attempts

- turns_observed: 123
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Purchase refusals

- turns: 15
- refused: 8
- rate: 0.5333
- tool_requests: 7

## Cost

- turns_priced: 123
- per_turn_usd: 0.004400
- total_usd: 0.541200
- input_tokens: 1079875
- output_tokens: 67215
- provider_requests: 178
- usd_per_all_checks_pass: 0.009664

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.1628 | FAIL |
| unsupported_numbers | 0 | 108 | FAIL |
| latency_p50_ms | < 5000 | 2839 | PASS |
| latency_p95_ms | < 12000 | 9232 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004400 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.5333 | FAIL |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1, 3.1 |
| C06 | 1 | PASS | - |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 2.6 |
| C12 | 1 | FAIL | 1.1, 3.1 |
| C13 | 1 | PASS | - |
| C14 | 1 | PASS | - |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | PASS | - |
| C18 | 1 | PASS | - |
| C19 | 1 | PASS | - |
| C20 | 2 | PASS | - |
| C21 | 1 | FAIL | 2.1 |
| C22 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C23 | 1 | FAIL | 2.1 |
| C24 | 2 | PASS | - |
| C25 | 2 | PASS | - |
