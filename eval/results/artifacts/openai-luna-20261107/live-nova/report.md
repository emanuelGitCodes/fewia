# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: real_bedrock
- manifest_hash: 744dbe8787823c8a42c0ed70b5b3f4992cba9681a3f42175f7a25c9cd3f473a7
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- proposal_prompt_hash: 6c3b90cf2f6db191b28b921dd16b4c1a2d7fe3bcb5007fe0d1e71d3d5cd599f2
- rates: {'model_id': 'us.amazon.nova-2-lite-v1:0', 'region': 'us-east-1', 'currency': 'USD', 'input_usd_per_1000': '0.0003300000', 'output_usd_per_1000': '0.0027500000', 'source_url': 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/20261106184538/us-east-1/index.json', 'source_version': '20261106184538', 'published_at': '2026-11-06T18:45:38Z', 'effective_date': '2026-11-01', 'retrieved_at': '2026-11-07'}
- region: us-east-1
- revision: 2295a0edb06ba290188f9f9573243bdca4eed573
- suite_version: conversation-eval-v1.6
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- tool_specs_hash: 5302e30f77f13bfe8fff2838563bc00adf90eed2b0f54eb5fb3aac09fe7c1c96
- version: conversation-manifest-v1

## Counts

- scenarios: 25
- repeats: 3
- turns_expected: 123
- turns_recorded: 123

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 120 | 123 | 0.9756 |
| outcome | 123 | 123 | 1.0 |
| gold | 113 | 123 | 0.9187 |

## Scenario pass (every turn has every gold fact)

- passed: 65
- total: 75
- rate: 0.8667
- all_checks: passed 62, total 75, rate 0.8267
- with_gold: passed 47, total 57, rate 0.8246

## Grounding

- prose_attempts: 45
- grounded_replies: 11
- grounded_rate: 0.2444
- unsupported_numbers: 91
- fallbacks: {'discovery_terminal': 27, 'no_tools': 6, 'not_final': 6, 'planned_terminal': 3, 'proposal': 3, 'refusal': 12, 'saved_plan_read': 15, 'swap_not_saved': 3, 'tool_failed': 3, 'validator': 34}

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
- refused: 12
- rate: 0.8
- tool_requests: 3

## Cost

- turns_priced: 123
- per_turn_usd: 0.004084
- total_usd: 0.502393
- input_tokens: 1024344
- output_tokens: 59767
- provider_requests: 170
- usd_per_all_checks_pass: 0.008103

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.2444 | FAIL |
| unsupported_numbers | 0 | 91 | FAIL |
| latency_p50_ms | < 5000 | 3130 | PASS |
| latency_p95_ms | < 12000 | 8317 | PASS |
| cost_per_turn_usd | < 0.006 | 0.004084 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.8 | FAIL |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | PASS | - |
| C06 | 1 | PASS | - |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C10 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C11 | 9 | FAIL | 2.6 |
| C12 | 1 | PASS | - |
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
| C24 | 2 | PASS | - |
| C25 | 2 | PASS | - |
