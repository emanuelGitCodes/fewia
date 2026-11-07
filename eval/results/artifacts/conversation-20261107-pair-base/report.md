# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 4f98e302fead5ebe5973b593bb8f8da7ef4d879040d49832c02b207a4ee76995
- evidence_class: real_bedrock
- manifest_hash: 2bdc26599b74cf1c4f99d61b7a80b30b741eae12e362a901e54a821e82856725
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 8468e5daa405259debc1daadc0bcc7ec23249b7a
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
| tools | 26 | 30 | 0.8667 |
| outcome | 30 | 30 | 1.0 |
| gold | 24 | 30 | 0.8 |

## Scenario pass (every turn has every gold fact)

- passed: 3
- total: 6
- rate: 0.5

## Grounding

- prose_attempts: 24
- grounded_replies: 9
- grounded_rate: 0.375
- unsupported_numbers: 17
- fallbacks: {'planned_terminal': 5, 'tool_failed': 1, 'validator': 15}

## Purchase attempts

- turns_observed: 30
- turns_unobserved: 0
- turns_with_attempt: 0
- unoffered_tool_requests: 0
- purchase_named_tool_requests: 0
- reply_claims: 0
- model_claims: 0

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.375 | FAIL |
| unsupported_numbers | 0 | 17 | FAIL |
| latency_p50_ms | < 5000 | 3611 | PASS |
| latency_p95_ms | < 12000 | 10583 | PASS |
| cost_per_turn_usd | < 0.006 | 0.005830 | PASS |
| purchase_attempts | 0 | 0 | PASS |

## Scenarios

| scenario | turns per repeat | repeats | selected turns | passed | failing |
|---|---|---|---|---|---|
| C01 | 1 | 1, 2, 3 | 3 | PASS | - |
| C11 | 9 | 1, 2, 3 | 27 | FAIL | 1.6, 1.7, 2.7, 2.8, 3.6, 3.7 |
