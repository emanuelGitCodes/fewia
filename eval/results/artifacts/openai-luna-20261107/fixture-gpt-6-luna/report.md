# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: deterministic_fake_provider
- manifest_hash: c7de60c32d8fbd188d5014ce8c85a894c3017a5cefa42f80951221193f2ab242
- model_config: {'reasoning_effort': 'none', 'max_output_tokens': 4096, 'store': False, 'parallel_tool_calls': False}
- model_id: gpt-6-luna
- profile: gpt-6-luna
- proposal_prompt_hash: 6c3b90cf2f6db191b28b921dd16b4c1a2d7fe3bcb5007fe0d1e71d3d5cd599f2
- region: us
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
| tools | 123 | 123 | 1.0 |
| outcome | 123 | 123 | 1.0 |
| gold | 123 | 123 | 1.0 |

## Scenario pass (every turn has every gold fact)

- passed: 75
- total: 75
- rate: 1.0
- all_checks: passed 75, total 75, rate 1.0
- with_gold: passed 57, total 57, rate 1.0

## Grounding

- prose_attempts: 51
- grounded_replies: 51
- grounded_rate: 1.0
- unsupported_numbers: 0
- fallbacks: {'discovery_terminal': 27, 'no_tools': 21, 'not_final': 3, 'proposal': 3, 'saved_plan_read': 15, 'swap_not_saved': 3}

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
- refused: 0
- rate: 0.0
- tool_requests: 0

## Cost

- turns_priced: 0
- per_turn_usd: None
- total_usd: None
- input_tokens: 16200
- output_tokens: 3240
- provider_requests: 162
- usd_per_all_checks_pass: None
- cache_read_tokens: 0
- cache_unknown_turns: 0
- turns_unpriced: 123
- coverage_complete: False

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 1.0 | PASS |
| unsupported_numbers | 0 | 0 | PASS |
| latency_p50_ms | < 5000 | 1 | not_applicable |
| latency_p95_ms | < 12000 | 4 | not_applicable |
| cost_per_turn_usd | < 0.006 | None | not_applicable |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.0 | not_applicable |

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
| C20 | 2 | PASS | - |
| C21 | 1 | PASS | - |
| C22 | 1 | PASS | - |
| C23 | 1 | PASS | - |
| C24 | 2 | PASS | - |
| C25 | 2 | PASS | - |
