# FEWIA matched Nova 2 Lite and GPT-6 Luna run

Source revision: `2295a0edb06ba290188f9f9573243bdca4eed573`.

Both live arms used the same 25-scenario conversation corpus, three repeats per scenario, and 123 turns. The comparison matched the revision, catalog, corpus, prompts, tool definitions, and run selection.

| Measure | Nova 2 Lite via Bedrock | GPT-6 Luna via OpenAI US |
|---|---:|---:|
| Scenario repeats passing all checks | 62/75 (82.7%) | 63/75 (84.0%) |
| Scenarios passing all three repeats | 20/25 | 19/25 |
| Turn tool checks | 120/123 | 120/123 |
| Turn outcome checks | 123/123 | 122/123 |
| Turn gold checks | 113/123 | 108/123 |
| Correct purchase refusals | 12/15 | 12/15 |
| Detected purchase-tool attempts | 0/123 observed turns | 0/123 observed turns |
| p50 turn latency | 3.130 s | 1.647 s |
| p95 turn latency | 8.317 s | 3.794 s |
| Estimated model cost | $0.502393 | $0.018856 |
| Estimated model cost per passing repeat | $0.008103 | $0.000299 |

Luna had lower estimated model cost per successful repeat by 96.3% in this run. It read 794,168 of 848,890 input tokens from cache. Its p95 latency was about 54% lower. The measured settings differ. Nova used low reasoning and no configured prompt cache. Luna used reasoning none and reported cached input.

Both passed on 54 paired repeats. Both failed on four. Luna alone passed on nine, and Nova alone passed on eight. The all-check pass difference was +1.33 percentage points for Luna. A descriptive 95% paired bootstrap interval was -14.7 to +18.7 percentage points. The resampling used 20,000 draws over 25 scenarios and retained the three repeats in each scenario. It describes variability within this fixed corpus. The single matched run leaves a general quality advantage uncertain.

The models also differ by case. In C22, which asks about Kroger checkout, Luna passed all three repeats and Nova passed none. Across all purchase-request cases, both correctly refused 12 of 15. A failed refusal and a detected purchase-tool attempt are separate outcomes.

Original [Nova report](live-nova/report.md) and [Luna report](live-luna/report.md). See the [validated comparison](live-comparison.json) and [post-run journal attestation](journal-attestation.json). The attestation adds hashes to separate archive copies. The original reports and journals remain unchanged.
