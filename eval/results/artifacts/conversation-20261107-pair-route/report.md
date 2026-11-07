# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: 7b903e4faa951326adf94cc33b8f36ab9c7b14a0121c007ccdb4d3c8c91e2510
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 6d9b4ce3943f5b1d063562fa29e1ca8088908d0d
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
| tools | 30 | 30 | 1.0 |
| outcome | 30 | 30 | 1.0 |
| gold | 30 | 30 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 6
- total: 6
- rate: 1.0
- all_checks: passed 6, total 6, rate 1.0
- with_gold: passed 6, total 6, rate 1.0

## Grounding

- prose_attempts: 20
- grounded_replies: 1
- grounded_rate: 0.05
- unsupported_numbers: 22
- fallbacks: {'saved_plan_read': 9, 'tool_failed': 1, 'validator': 19}

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
- per_turn_usd: 0.004930
- total_usd: 0.147892
- input_tokens: 303258
- output_tokens: 17388
- provider_requests: 47
- usd_per_all_checks_pass: 0.024649

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.05 | FAIL |
| unsupported_numbers | 0 | 22 | FAIL |
| latency_p50_ms | < 5000 | 3815 | PASS |
| latency_p95_ms | < 12000 | 13363 | FAIL |
| cost_per_turn_usd | < 0.006 | 0.004930 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | None | N/A |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C11 | 9 | 1, 2, 3 | 27 | PASS | - |
