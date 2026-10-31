# 0025 — Medical claims check and an optional Bedrock guardrail

- Date: 2026-10-30
- Status: accepted
- Implements: the "medically suitable" rule of
  [0022](0022-grounded-model-prose.md)

## Decision

Two layers guard model prose against medical advice.

1. **Validator.** A model reply that names a health condition fails with
   the reason code `medical_claim` and falls back to the server template.
   The words match from a word start on the folded text: diabetes,
   diabetic, prediabetes, glycemic, insulin, glucose, blood sugar, blood
   pressure, hypertension, cholesterol, pregnancy, pregnant. "Kidney" is
   not in the list, because the catalog has kidney beans. The server
   sentences stay exempt.
2. **Bedrock guardrail.** An optional guardrail with four denied topics:
   medical advice, allergy safety assurance, financial transactions, and
   non-food tasks. The medical topic checks model output only, because
   nutrition questions sit next to it. A content filter checks input and
   output. When Bedrock stops with `guardrail_intervened`, the user gets
   one fixed decline sentence. The guardrail is off until the owner
   deploys it and sets its ID and version.

## Rules

- The validator check runs on every model-prose reply. It does not depend
  on the guardrail.
- With no guardrail ID set, the Converse request MUST NOT change.
- The CDK stack defines the guardrail and grants `bedrock:ApplyGuardrail`
  on it to the development role. The owner deploys the stack; agents MUST
  NOT deploy it.
- Only the latest user text goes in a `guardContent` block, so each call
  assesses one or two text units.

## Basis

- Owner choice, 2026-10-30: build both layers now, and fail any condition
  word whatever the phrasing.
- Design section 4.9 in
  [docs/design/chat-architecture-proposal.md](../../docs/design/chat-architecture-proposal.md).
- C09 in `conversation-eval-v1`: Nova called overnight oats "a good
  low-glycemic-index choice for type 2 diabetes", and the validator passed
  it.

## Consequences

- A reply that only repeats the user's condition ("You asked about
  diabetes") also falls back to the template.
- The guardrail adds an AWS resource and a per-text-unit charge. False
  blocks on nutrition questions MUST be measured before the guardrail is
  on by default.
