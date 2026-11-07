# FEWIA planning tool ablation

Model GPT-6 Luna through the OpenAI US endpoint. Source revision: `3f0fcf1ff24a6515064fab8a5ade2ba70a1e3247`.

Twelve curated cases, three repeats per case, and 36 trials per condition. Both conditions receive the same requests, sample catalog, instructions, and strict response schema. The only experimental change is access to FEWIA's deterministic planning tool. The runner alternates condition order within randomized scenario-repeat pairs.

Each trial must preserve the requested meals and servings, choose the correct plan or rejection, and report the exact basket cost where applicable. An independently calculated reference agreed with FEWIA's planner for all 12 cases before the live run.

| Measure | Tools available | No tools |
|---|---:|---:|
| Passed all checks | 36 | 9 |
| Valid final format | 36 | 36 |
| Correct decision | 36 | 33 |
| Correct meals and servings | 36 | 36 |
| Correct basket cost or expected null | 36 | 9 |
| Tool calls | 36 | 0 |
| Provider requests | 72 | 36 |
| Trials with known price | 36 | 36 |
| Estimated model cost in USD | 0.008341278 | 0.004983154 |
| Estimated USD per passing trial | 0.000231702 | 0.000553684 |
| p50 end-to-end latency in ms | 2391 | 1044 |
| p95 end-to-end latency in ms | 3020 | 1390 |

Paired repeats: tools alone passed 27, no tools alone passed 0, both passed 9, and both failed 0. The descriptive 95% scenario-resampled interval for the tools-minus-no-tools pass difference is +50.0 to +100.0 percentage points. Resampling uses 20,000 draws over the 12 fixed scenarios and keeps repeats together.

| Case | Capability | Tools passes | No-tools passes |
|---|---|---:|---:|
| P01 | basic estimate | 3/3 | 0/3 |
| P02 | package rounding | 3/3 | 0/3 |
| P03 | shared ingredients | 3/3 | 0/3 |
| P04 | pantry credit | 3/3 | 0/3 |
| P05 | pantry and multiple meals | 3/3 | 0/3 |
| P06 | over budget | 3/3 | 0/3 |
| P07 | exact budget boundary | 3/3 | 3/3 |
| P08 | one cent over budget | 3/3 | 0/3 |
| P09 | diet conflict | 3/3 | 3/3 |
| P10 | diet and pantry | 3/3 | 0/3 |
| P11 | ingredient conflict | 3/3 | 3/3 |
| P12 | allowed exclusion | 3/3 | 0/3 |

## Representative errors

- tools: no failed trial in these cases.
- no_tools, P01 repeat 1 (price): expected plan and 1703 cents. Got plan and 2015 cents.
- no_tools, P02 repeat 1 (price): expected plan and 2249 cents. Got plan and 1602 cents.
- no_tools, P03 repeat 2 (price): expected plan and 2310 cents. Got plan and 1687 cents.
- no_tools, P04 repeat 2 (price): expected plan and 417 cents. Got plan and 616 cents.

The one-cent budget boundary shows why a wrong total matters. The actual basket cost was $17.03 and the cap was $17.02. The tool condition rejected the plan in all three repeats. The no-tools condition returned a plan in all three.

This ablation covers the planning core and fixed requested meals. It does not measure arbitrary meal discovery, browser performance, retailer behavior, or model intelligence outside these cases. The separate Nova–Luna comparison measures the full conversation suite with tools enabled in both arms. Do not combine their denominators.

[Frozen experiment](live/manifest.json) · [Sanitized trials](live/trials.jsonl) · [Structured results](report.json) · [Reproducer](run_ablation.py)
