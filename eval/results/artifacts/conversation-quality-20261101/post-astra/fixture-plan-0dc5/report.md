# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: d884237cd6374302bc65f9a2dcde2597f0bf13b3189ef08dbabdaaf684e37be5
- evidence_class: deterministic_fake_provider
- manifest_hash: b1919ab62cfade2d00d5cf061e769423f315b9e446c629aa8cae32c749809b71
- model_config: {'max_tokens': 4096, 'temperature': 0, 'reasoning_effort': 'low'}
- model_id: us.amazon.nova-2-lite-v1:0
- profile: nova-2-lite
- region: us-east-1
- revision: 0dc50a6facf4d62350b6bf3492409cc9ba61c53a
- suite_version: conversation-eval-v1.4
- system_prompt_hash: 06a3f92a4240a8ad9f6c402c0b66ce18e8b6900b64c50b7d59681bc53bd6760a
- version: conversation-manifest-v1

## Counts

- scenarios: 19
- repeats: 3
- turns_expected: 96
- turns_recorded: 96

## Checks

| check | passed | total | rate |
|---|---|---|---|
| tools | 96 | 96 | 1.0 |
| outcome | 96 | 96 | 1.0 |
| gold | 96 | 96 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 57
- total: 57
- rate: 1.0

## Grounding

- prose_attempts: 57
- grounded_replies: 57
- grounded_rate: 1.0
- unsupported_numbers: 0
- fallbacks: {'discovery_terminal': 27, 'no_tools': 6, 'not_final': 3, 'proposal': 3}

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 1.0 | PASS |
| unsupported_numbers | 0 | 0 | PASS |
| latency_p50_ms | < 5000 | 1 | not_applicable |
| latency_p95_ms | < 12000 | 2 | not_applicable |
| cost_per_turn_usd | < 0.006 | None | not_applicable |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | PASS | - |
| C05 | 1 | PASS | - |
| C06 | 1 | PASS | - |
| C07 | 2 | PASS | - |
| C08 | 1 | PASS | - |
| C09 | 1 | PASS | - |
| C10 | 1 | PASS | - |
| C11 | 9 | PASS | - |
| C12 | 1 | PASS | - |
| C13 | 1 | PASS | - |
| C14 | 1 | PASS | - |
| C15 | 1 | PASS | - |
| C16 | 4 | PASS | - |
| C17 | 1 | PASS | - |
| C18 | 1 | PASS | - |
| C19 | 1 | PASS | - |
