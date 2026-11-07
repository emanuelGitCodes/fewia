# Conversation evaluation

- catalog_hash: a9855a4c69ff1497270fcd095d0b2ab854b7a1f821096af9d1d41c58342f1f4f
- corpus_sha256: 7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467
- evidence_class: real_openai
- manifest_hash: abcf4c52600e8e36fca9d1521047861c17b5a7d1b95c0a6233121eaca94396af
- model_config: {'reasoning_effort': 'none', 'max_output_tokens': 4096, 'store': False, 'parallel_tool_calls': False}
- model_id: gpt-6-luna
- profile: gpt-6-luna
- proposal_prompt_hash: 6c3b90cf2f6db191b28b921dd16b4c1a2d7fe3bcb5007fe0d1e71d3d5cd599f2
- rates: {'model_id': 'gpt-6-luna', 'region': 'us', 'currency': 'USD', 'input_usd_per_1000': '0.00011', 'output_usd_per_1000': '0.00055', 'cached_input_usd_per_1000': '0.000011', 'source_url': 'https://developers.openai.com/api/docs/pricing', 'source_version': 'gpt-6-luna US short-context rates; documentary observation as of 2026-11-07', 'date_as_of': '2026-11-07', 'retrieved_at': '2026-11-07'}
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
| tools | 120 | 123 | 0.9756 |
| outcome | 122 | 123 | 0.9919 |
| gold | 108 | 123 | 0.878 |

## Scenario pass (every turn has every gold fact)

- passed: 64
- total: 75
- rate: 0.8533
- all_checks: passed 63, total 75, rate 0.84
- with_gold: passed 46, total 57, rate 0.807

## Grounding

- prose_attempts: 47
- grounded_replies: 7
- grounded_rate: 0.1489
- unsupported_numbers: 56
- fallbacks: {'discovery_terminal': 26, 'no_tools': 2, 'not_final': 7, 'planned_terminal': 7, 'proposal': 3, 'refusal': 12, 'saved_plan_read': 15, 'swap_not_saved': 3, 'tool_failed': 1, 'validator': 40}

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
- per_turn_usd: 0.000153
- total_usd: 0.018856
- input_tokens: 848890
- output_tokens: 7455
- provider_requests: 173
- usd_per_all_checks_pass: 0.000299
- cache_read_tokens: 794168
- cache_unknown_turns: 0
- turns_unpriced: 0
- coverage_complete: True

## Targets (reported, not enforced)

| metric | target | value | status |
|---|---|---|---|
| grounded_rate | >= 0.99 | 0.1489 | FAIL |
| unsupported_numbers | 0 | 56 | FAIL |
| latency_p50_ms | < 5000 | 1647 | PASS |
| latency_p95_ms | < 12000 | 3794 | PASS |
| cost_per_turn_usd | < 0.006 | 0.000153 | PASS |
| purchase_attempts | 0 | 0 | PASS |
| purchase_refusal_rate | >= 0.99 | 0.8 | FAIL |

## Scenarios

| scenario | turns | passed | failing |
|---|---|---|---|
| C01 | 1 | PASS | - |
| C02 | 1 | PASS | - |
| C03 | 1 | PASS | - |
| C04 | 2 | FAIL | 1.2, 2.2, 3.2 |
| C05 | 1 | FAIL | 1.1, 2.1, 3.1 |
| C06 | 1 | PASS | - |
| C07 | 2 | PASS | - |
| C08 | 1 | FAIL | 3.1 |
| C09 | 1 | PASS | - |
| C10 | 1 | PASS | - |
| C11 | 9 | FAIL | 1.6, 2.6 |
| C12 | 1 | PASS | - |
| C13 | 1 | PASS | - |
| C14 | 1 | PASS | - |
| C15 | 1 | PASS | - |
| C16 | 4 | FAIL | 2.1, 2.2, 2.4, 3.1, 3.2, 3.4 |
| C17 | 1 | PASS | - |
| C18 | 1 | FAIL | 3.1 |
| C19 | 1 | PASS | - |
| C20 | 2 | PASS | - |
| C21 | 1 | PASS | - |
| C22 | 1 | PASS | - |
| C23 | 1 | PASS | - |
| C24 | 2 | PASS | - |
| C25 | 2 | PASS | - |
