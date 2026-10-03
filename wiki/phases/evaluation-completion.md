# Evaluation completion checkpoint

## Snapshot

This page records the local-only integration at snapshot `a9a9a4f51b34b05b10a00aa6e9399e2f15a3d8bb`, captured at `2026-10-03T03:43:02.320249+00:00`. It records 36 approved components. The complete batch/CLI, full benchmark, and four feature groups remain incomplete.

The integrated snapshot contains 4,159 added application lines across reviewed slices. Each accepted source slice stayed within 150 added application lines. The 4,159 lines are a collection of slices, not one compliant pull request. This loop created no remote pull requests, pushed no branches, and merged nothing to `main`.

## Integrated gates

The integrated gate run finished at `2026-10-03T03:39:32.466703+00:00` for the snapshot above:

| Gate | Recorded result |
|---|---|
| Ruff check | PASS — All checks passed! |
| Ruff format | PASS — 262 files already formatted |
| Mypy | PASS — Success: no issues found in 130 source files |
| Pytest | PASS — 6055 passed, 1 warning in 12.11s |

## Approved components

The record includes 36 approved component IDs and their source SHAs. These are local reviewed slices in the integrated snapshot.

### Inputs, fixtures, references, and provider paths

| ID | Component | SHA |
|---|---|---|
| 01 | Bound evaluation meal inputs | `72c7c15d12c6f7660e78e4255a33d5d691d95c70` |
| 02a | Validate evaluation result shapes | `922d2fd20cd5ce3f25fcf8e7e11303461c4a0d3b` |
| 03 | Add reproducible evaluation manifest | `0e84ea50e3196fffc8c574f95460f2196827d124` |
| 05 | Fix evaluation evidence table typing | `b7f14d0ebe9836b93f68ad7f365d1aa4b648309e` |
| 06a | Use aware datetime in schema test | `0ca7d4768c6547e6334e83a770ffbdbd60798fb0` |
| 06 | Use strict plan observation parser | `77e4e740a3e264f7e7d996c568b8f18137ad5f3e` |
| 08a | Wrap outcome proposition pattern | `c784f23a9e97a57e207379cef88644da8159a982` |
| 09 | Reject undeclared nested result fields | `ff6af2c89921e2274a46367fb9e47491dee7e1be` |
| 10 | Reject blank evaluation case identities | `b14218bb169e6d139705d1e4b788a273fa3d5ba5` |
| 12a | Add controlled evaluation fault provider | `aad209c98eac753b4a0446b40d4f3752aab4098e` |
| 12 | Use approved provider for protocol evaluation | `24eb4f4d1e2d1bcf913773f36ba7432cb406d682` |
| 13 | Handle fixture database cleanup errors | `6ad9a159a9e25a12c31539687771fb9a366cae40` |
| 14 | Mark refresh evaluation redaction boundary | `0499568f23bb6ebaee041b03d33a9565061321ed` |
| 14a | Add isolated Plaid refresh evaluation fixture | `2460154c34546d5482cf84f477c0ffd02472ff4b` |
| 15 | Mark handoff evaluation redaction boundary | `9c66687508735bc9172246bf7fbcf117ade18f33` |
| 16 | Evaluate duplicate worker delivery | `31a0bed32c8f2e1f2231c96e604007401bd4d156` |
| 16a | Count only validated duplicate handler calls | `1dcde961dfc98d465f5b722b86e21698aaf0844a` |
| 17 | Skip reasoning values during sanitization | `051b8860b93f067195f4434aa76fce9c1175b10e` |
| 19 | Fix deterministic reference evidence paths | `96d56255eb275928c03e2db423f728ef1e58cf94` |
| 20 | Make frozen matrix mutation test lint clean | `33c8bb707364fd627662fdda7267bc3d1a718d55` |

### Claims, tasks, and metrics

| ID | Component | SHA |
|---|---|---|
| 18 | Require plan integrity for over-budget claims | `e1863b0253e2c7a4098037577412d0d9eed50b79` |
| 18a | Use direct frozen claim test assignments | `88d5a6203211469be53e7ecf79184e56a2d590ad` |
| 23a | Validate evaluation assessment scopes | `8bcb36a6af7ebbaad0869515e3e2ec1f603e77ae` |
| 23a_counts | Add strict evaluation metric count helpers | `fb188743bdd6deb099daafc6c14ff87905994255` |
| 23a_checks | Validate safe summary check records | `a89ad21401d3fb852824235f3357d3c1e7def2f9` |
| 23b | Summarize classified evaluation tasks | `29acb00ce9a59b01efd3f025f93d8c5e7dff795c` |
| 23b_validation | Require applicable task assessments | `8d81ae45f4ea398f624691b3e140929ec5ab3bad` |
| 23b_assessments | Add evaluation assessment classification | `f250d25e5093cfbaa113e18effaf7b76483907d9` |
| 23 | Enforce fixture observation metadata | `b710c398074f14feb4744367d59d4978aee42b73` |
| 24 | Add evaluation telemetry aggregation | `ab6997dc53893a5e81fa466fe377f94bbfdae0e2` |

### Telemetry, rates, output, and CI

| ID | Component | SHA |
|---|---|---|
| 25 | Add evidence-aware evaluation cost | `e544b9a642c37a06e559c3d157b83f0afb1040ee` |
| 25a | Add immutable evaluation rates | `7bbf47e3330c1ebceeec4a34b7f3ff0e51274266` |
| 26 | Fix evaluation IO import order | `d7698872e32928e112b7b363931c1540f473200b` |
| 26a | Add evaluation JSON helpers | `61ffa0cb27cae2c03aa9cc10d133e2ab2bc277ae` |
| 27a | Bound Markdown integer cells | `d37f69e86fd1a03194f08277df2a19c69184b739` |
| 30 | Test the required evaluation database guard | `8d6beab5b9039fd2e6d3bacff45e6b88629aa208` |

## Component evidence

The component smoke at revision `64bf3b87efa48b73b7782194f5a898abbc46db92` recorded five deterministic reference outputs and four controlled provider cases. All nine observations passed. It recorded 42 scored legacy-runner slots and 48 unassessed slots. It made zero live model benchmark calls. Its completion marker checked the report hashes.

The [component smoke report](../../backend/artifacts/evaluation-component-smoke-20261003T004316Z/report.md) and [completion marker](../../backend/artifacts/evaluation-component-smoke-20261003T004316Z/completion.json) are ignored local artifacts. The marker records 9 slots, `report.json` SHA-256 `7084ae1faf9651be45fe8a4662448f549f9e59fbae5a464c1ce5ad141ae4ee80`, and `report.md` SHA-256 `57bd9b0a466f384983a99b022ec08e4fb8550bdc88afee54d44c33c599a18242`.

At source revision `b710c398074f14feb4744367d59d4978aee42b73`, the summary smoke recorded five current structured-reference outputs and four controlled-provider cases: nine observations across two separate quality scopes. It made zero live model calls, and its completion record verified the output hashes. The [summary report](../../backend/artifacts/evaluation-summary-smoke-20261003T033738Z/report.md), [summary JSON](../../backend/artifacts/evaluation-summary-smoke-20261003T033738Z/report.json), and [completion record](../../backend/artifacts/evaluation-summary-smoke-20261003T033738Z/completion.json) are ignored local artifacts. The verification archive [manifest](../../backend/artifacts/evaluation-checkpoint-20261003T034302Z/manifest.json) preserves 36 approved gate/review pairs and 72 checked hashes.

The duplicate-delivery smoke used isolated PostgreSQL, the production worker, and the Floci SQS/S3 path. Eighteen checks passed. Two deliveries produced one execution, evidence revision, handoff, and artifact write. S3 readback matched its hash, and the private schema was removed. The link provider was a deterministic fake. No live model or Instacart call ran.

The [duplicate-delivery report](../../backend/artifacts/evaluation-duplicate-smoke-20261003T011315Z/report.md) and [completion marker](../../backend/artifacts/evaluation-duplicate-smoke-20261003T011315Z/completion.json) are ignored local artifacts. The marker records 1 slot, `report.json` SHA-256 `3a6300a1bf278656a6952e836057a77bead28c3fbf563653ec3ee84b02709c94`, and `report.md` SHA-256 `c1b886378c418a5b235437936f53f1ebd90ca1f5f42a451cde672381166830f4`.

These ignored outputs are local records present in the recorded primary worktree. Clean checkouts do not include them. They are not published files.

## Evidence limits and open work

This checkpoint has no live Plaid or Instacart evidence and no checkout evidence. The product uses a manual budget and sample prices. Keep deterministic, sandbox, live-provider, and deployed evidence separate. Do not pool fake and live success. Do not treat the planned matrix as execution. No full 30-scenario, three-repeat run or 138-slot benchmark ran. The 90% task-success and 95% supported-claim targets are not certified. These components do not establish general hallucination guarantees.

Items 02, 04, and 08 each completed three independent review rounds and await human approval for an extra round. They are not integrated:

- Item 02, held SHA `9c42c41`: tool-call arguments need maximum one-to-one matching so an incorrect early call cannot consume the expected call.
- Item 04, held SHA `1b35e88`: an incomplete leak scan must not certify that no leak occurred.
- Item 08, held SHA `0f72c3d`: refusal semantics must allow harmless registered reads; the tool scorer grades unnecessary calls separately.

Observers 07 and 11, dispatch 21, batch 22, renderer 27, and CLI 28 remain unbuilt or dependent. Core item 23 is approved and integrated. Approved metrics and task helpers are integrated. The complete batch/CLI, full benchmark, and four feature groups remain incomplete.

Read the [evaluation guide](../../docs/EVALUATION.md) for the current API boundary, validation command, and evidence-table rules.
