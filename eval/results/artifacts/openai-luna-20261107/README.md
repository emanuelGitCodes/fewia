# OpenAI and Bedrock evaluation evidence

Issue [#482](https://github.com/emanuelGitCodes/fewia/issues/482) adds a direct OpenAI path beside Bedrock. This archive contains synthetic grocery cases and their measured results.

## Find the evidence

| Evidence | Source revision | Report | Raw records |
|---|---|---|---|
| Matched live conversation study | `2295a0ed` | [Summary](summary.md) and [comparison JSON](live-comparison.json) | [Nova](live-nova/) and [Luna](live-luna/) |
| Same-model planning tool study | `3f0fcf1f` | [Planning report](planning-ablation/report.md) and [JSON](planning-ablation/report.json) | [Frozen cases and expected results](planning-ablation/live/manifest.json) and [72 trials](planning-ablation/live/trials.jsonl) |
| Credential-free conversation fixtures | `2295a0ed` | [Fixture comparison](fixture-comparison.json) | [Nova profile fixture](fixture-nova-2-lite/) and [Luna profile fixture](fixture-gpt-6-luna/) |
| Local verification | See each record | [Checks and limits](verification/README.md) | [Runtime](verification/runtime-gates.txt), [measured revision](verification/measured-revision-gates.txt), and [checksum revision](verification/checksum-revision-gates.txt) |

The matched study has 123 turns per arm across 25 scenarios. It measures tool-enabled conversation with both models. The planning study uses Luna for both conditions. Each condition has 36 trials over 12 cases. Do not pool the two studies.

The original live arm reports and journals keep their original bytes. The original completion markers hash the reports. The [attestation](journal-attestation.json) records journal hashes added after execution to separate comparison copies. New conversation runs add this hash during completion.

Estimated cost uses provider token rates. It excludes other services and does not represent an invoice. The studies do not measure live Kroger, Plaid, or AWS hosting.

## Verify without credentials

From `backend/`, run the comparison against the attested copies. Choose a new output path.

```bash
archive=../eval/results/artifacts/openai-luna-20261107
uv run python -m app.compare_conversation \
  --nova "$archive/live-nova-attested" \
  --luna "$archive/live-luna-attested" \
  --output /tmp/fewia-openai-luna-verified.json
cmp "$archive/live-comparison.json" /tmp/fewia-openai-luna-verified.json
```

To recalculate the planning report, copy its directory to a temporary location. From that copy, run `python3 summarize_ablation.py .`. The script checks the frozen input hashes, all 72 unique trial keys, and the expected answers before it writes the reports.

The [planning reproducer](planning-ablation/run_ablation.py) uses the FEWIA application modules. Set `PYTHONPATH` to the repository's `backend/` directory. To run the offline control, give it a new `--output` directory and the recorded `--revision`. Omit `--key-file`. The command verifies the independent price calculation and the shared input and answer format.

For live setup and benchmark commands, see the [evaluation runbook](../../../../docs/EVALUATION.md#matched-nova-and-luna-runs). The operator supplies a private key file outside the source tree.

## Scope limits

- The matched study varies the model and provider configuration. Nova used low reasoning. Luna used reasoning none and reported cache reads.
- The planning study holds the model and answer format fixed. It covers curated requests for fixed meals. It does not test all meal discovery or browsing behavior.
- The fixture provider follows expected tool calls. Fixture success measures the harness and tool integration.
- The archives contain model and tool observations for synthetic cases. The local API smoke check separately confirms the worker and saved-plan path.
