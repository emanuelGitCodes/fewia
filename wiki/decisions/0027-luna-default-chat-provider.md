# 0027 — GPT-6 Luna is the default local chat provider

- Date: 2026-11-07
- Status: accepted
- Amends: [0001 — Real Bedrock from day one](0001-real-bedrock-from-day-one.md)
  and the language-model line of
  [0019 — Invitation-only hosted demo](0019-invitation-only-hosting.md).

## Decision

The local stack uses GPT-6 Luna through the OpenAI Responses API for chat.
`make up` starts it. Amazon Bedrock with Nova 2 Lite stays a supported
alternative through `make up-bedrock`. `make up-offline` starts the stack with
no chat provider.

The OpenAI region default is `global`. `us` stays a supported value.

The hosted demo stays on Bedrock. A later decision MUST record a hosted
OpenAI path before the hosted stack changes provider.

FEWIA MUST NOT switch providers automatically. Each start command selects one
provider.

## Options considered

1. Keep Bedrock as the default and offer Luna as an option. This keeps the
   higher cost and latency as the default.
2. Make Luna the default for local and hosted stacks now. The hosted stack
   injects secrets as environment variables, and the OpenAI adapter reads the
   key only from a file. A hosted path needs a new key contract.
3. Make Luna the default for the local stack only. Chosen.

## Reason

The owner chose Luna on 2026-11-07 to reduce model cost. The matched run in
[PR 484](https://github.com/emanuelGitCodes/fewia/pull/484) used the same
corpus and checks for both providers. Luna passed 63 of 75 repeats and Nova
passed 62. Estimated model cost per passing repeat was USD 0.000299 for Luna
and USD 0.008103 for Nova. The p95 turn latency was 3.794 seconds for Luna and
8.317 seconds for Nova. The run used the `us` region. The OpenAI price for
`us` processing of `gpt-6-luna` is 10% higher than for `global` processing.

## Consequences

- A grader supplies a key from their own OpenAI project.
  [Decision 0028](0028-openai-key-in-env.md) puts that key in `.env`. The
  key MUST NOT go in Git, logs, or archives.
- The infrastructure under `infra/hosting/` is undeployed and keeps the
  Bedrock settings.
- Evidence from Bedrock runs stays valid as Bedrock evidence. A provider
  comparison uses the matched runs in the
  [Nov. 7 archive](../../eval/results/artifacts/openai-luna-20261107/README.md).
- A `global` benchmark run needs its own rate file. The archived
  `luna-us-rates.json` prices `us` runs only.
