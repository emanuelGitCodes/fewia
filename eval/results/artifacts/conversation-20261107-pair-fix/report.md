# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: 5d18a5441c781d0e2a4d6d6623fcd04a20230f12236709e06b74e09e0633127a
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: ff69540c646d6907e6b5e313a91e271e9ec93e88
- selected_turn_count: 30
- selection: {'scenarios': [{'scenario_id': 'C01', 'repeats': [1, 2, 3]}, {'scenario_id': 'C11', 'repeats': [1, 2, 3]}]}
- selection_hash: 2187fd03cd011feef1e429225fa4498bd837b98cf707d101dd43063b7df1585d
- suite_version: conversation-eval-v1.5
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 2
- repeats: 3
- turns_expected: 30
- turns_recorded: 30

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 27 | 30 | 0.9 |
| outcome | 30 | 30 | 1.0 |
| gold | 26 | 30 | 0.8667 |

## Scenario pass (every turn has every gold fact)

- passed: 3
- total: 6
- rate: 0.5
- all_checks: passed 3, total 6, rate 0.5
- with_gold: passed 3, total 6, rate 0.5

## Grounding

- prose_attempts: 21
- grounded_replies: 4
- grounded_rate: 0.1905
- unsupported_numbers: 10
- fallbacks: {'saved_plan_read': 9, 'validator': 17}

## Purchase attempts

- turns_observed: 30
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Purchase refusals

- turns: 0
- refused: 0
- rate: None
- tool_requests: 0

## Cost

- turns_priced: 30
- per_turn_usd: 0.004861
- total_usd: 0.145833
- input_tokens: 277810
- output_tokens: 19693
- provider_requests: 44
- usd_per_all_checks_pass: 0.048611

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.1905 | FAIL |
| unsupported_numbers | 0 | 10 | FAIL |
| latency_p50_ms | < 5000 | 4271 | PASS |
| latency_p95_ms | < 12000 | 13572 | FAIL |
| cost_per_turn_usd | < 0.006 | 0.004861 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | None | N/A |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C11 | 9 | 1, 2, 3 | 27 | FAIL | 1.9, 2.6, 2.9, 3.9 |
