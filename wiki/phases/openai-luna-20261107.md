# OpenAI provider and benchmark evidence

Issue [#482](https://github.com/emanuelGitCodes/fewia/issues/482) adds direct GPT-6 Luna through the OpenAI Responses API. Bedrock remains an available provider. Both providers use the existing worker, grocery tools, and proposal flow.

The [archive index](../../eval/results/artifacts/openai-luna-20261107/README.md) links the frozen cases, original journals, comparison copies, reports, and test output. The [runbook](../../docs/EVALUATION.md#matched-nova-and-luna-runs) describes setup and reproduction.

| Study | Revision | Results |
|---|---|---|
| Tool-enabled live conversation | `2295a0ed` | Nova passed 62 of 75 repeats. Luna passed 63 of 75. Both recorded 123 turns. Estimated cost per passing repeat was USD 0.008103 for Nova and USD 0.000299 for Luna. |
| Luna planning tool access | `3f0fcf1f` | Tools passed 36 of 36 trials. No tools passed 9 of 36. Both arms returned a valid answer on every trial. The shared schema and cases remain in the archive. |

The adapter and checksum revisions passed the local gates and independent review. The final backend gate on `229be439` reported 18,426 passed and one skipped. A clean source ZIP ran all 123 fixture turns. A live local API test confirmed the worker and Apply flow.

The journal attestation adds hashes to separate comparison copies. The original live records remain unchanged. Future conversation completion markers include the journal checksum.

The model comparison covers one matched batch with different supported reasoning settings and caching behavior. The planning comparison covers twelve curated cases with fixed requested meals. The results do not establish general model superiority or live retailer behavior.
