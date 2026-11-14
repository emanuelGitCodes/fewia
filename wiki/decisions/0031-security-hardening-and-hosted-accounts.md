# 0031 — Security hardening and hosted accounts

- Date: 2026-11-12.
- Status: accepted; resumed implementation is saved. Hosted release remains
  blocked by image findings. Publication and final-head verification use the
  [handoff](../security-hardening-handoff.md).
- Amends: [0019](0019-invitation-only-hosting.md) and
  [0022](0022-grounded-model-prose.md).

## Decision

Hosted Cognito users receive separate application accounts and data.
Public signup stays disabled. The local fixture remains a loopback demo.
The application MUST verify signed ALB identity before accepting hosted requests.
The application MUST derive each job owner from authenticated server state.
Workers MUST derive the owner from the durable job row.

Existing records keep their current owner. The first hosted login MUST NOT
claim the legacy demo account. No automatic purge runs.
An operator can preview retention work before an explicit purge.

Live local Kroger requires owner-browser pairing. Cart confirmation binds to
the owner, the connection version, and a signed preview.
An uncertain external write stays uncertain. The application MUST NOT replay
that write automatically.

The model interprets requests and selects typed tools. The server renders
factual replies from validated tool results. Runtime model prose does not
establish an action, purchase, delivery, or payment.

Estimated model exposure defaults to USD 1 per user per UTC day.
The global default is USD 10 per UTC day. These limits use versioned rates.
They do not guarantee a provider invoice limit.

## Delivery

The owner requested one pull request for this work. The owner explicitly
approved a one-time exception to the 1,000 added-source-line cap.
The exception applies only to `codex/security-hardening` and its final pull request.
Normal publication guards remain active. The work retains focused commits,
isolated tests, and independent review of the final head.

Writers use `gpt-6.1-sol` at `high` through `dev_supervisor`.
Independent review uses `gpt-6.1-terra` at `high`.
The coordinator uses at most three concurrent native workstream agents.

Implementation authorization does not establish deployed security evidence.
AWS deployment, invitations, live provider validation, and merge remain separate steps.
