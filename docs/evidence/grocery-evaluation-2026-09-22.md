# FEWIA evaluation record

Revision: a473bb1a6b7691a479365f9061daedfac792ce46
Model: `us.amazon.nova-2-lite-v1:0`
Source region: `us-east-1`

Global quality: UNASSESSED

## Execution counts

| scored | observed | failed | unassessed | invalid |
| --- | --- | --- | --- | --- |
| 51 | 30 | 0 | 9 | 0 |

## Check groups

| group | assessed | passed | failed | invalid | outside_scope |
| --- | --- | --- | --- | --- | --- |
| fixture | 51 | 51 | 0 | 0 | 39 |
| control | 3 | 3 | 0 | 0 | 87 |
| final-plan | 15 | 15 | 0 | 0 | 75 |
| structured-reference | 15 | 15 | 0 | 0 | 75 |

## Observation evidence

| deterministic_fake_provider | real_bedrock | unknown |
| --- | --- | --- |
| 0 | 30 | 0 |

## Latency

Sample count: 30
Method: nearest-rank
p50: 8.536 s
p95: 16.497 s

Latency sums user-turn elapsed times for each observation.

## Tokens

known_usage_slots: 30
unknown_usage_slots: 0
known_input_tokens: 195499
known_output_tokens: 40205
input_tokens: 195499
output_tokens: 40205

Final-plan checks cover the last structured plan only. Fake evidence and live evidence are not interchangeable.

Structured-reference checks use structured inputs. They compare the final result only. They do not measure language understanding or earlier-turn quality.
Prompt hash: ce6955c6b8dcbe26c1f41cbc66a5e27d000da80107ac47795b3b3f7501f6f8f9
Catalog version: `sample-prices-v1`
## Estimated model cost

estimated_usd: 0.17507842
known_subset_estimated_usd: 0.17507842
currency: `USD`
input_usd_per_million: 0.33
output_usd_per_million: 2.75
model_id: `us.amazon.nova-2-lite-v1:0`
source_region: `us-east-1`
routing: `geographic`
service_tier: `standard`
effective_date: `2026-09-01`
retrieved_date: `2026-09-22`
source_url: [source](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json)

Text input/output token estimate only. Excludes cache, other charges, and account adjustments. Not an AWS invoice or observed billing.
