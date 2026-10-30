# 0023 — Retire the Instacart adapter and keep the frozen suite

- Date: 2026-10-30
- Status: accepted
- Amends: [0010](0010-usda-spoonacular-overlay.md) (the Instacart part)

## Decision

The Kroger cart replaces the Instacart development handoff. Remove the
Instacart user surface and its HTTP client:

- the `/grocery/handoffs` routes and their request and response models;
- the frontend handoff controls, the consent dialog, and their hooks;
- the `instacart_key_file` setting and the `build_instacart` factory;
- the `instacart_configured` capability flag;
- the `InstacartDevelopmentProvider` HTTP client.

Keep the code that the frozen `grocery-eval-v1` suite runs: the
`InstacartRejected` and `InstacartUncertain` exceptions,
`validate_link_url`, the handoff dispatch, intent, and contract services,
and the shopping payload builder. Scenario P02 and the duplicate-handoff
check inject a fake provider through these modules.

Keep the `shopping_handoffs` table under decision
[0018](0018-retain-legacy-data.md). Add no migration.

Keep the estimate notice that names Instacart. A later item changes the
notice, the claim parser `_ATOMIC`, the baseline system prompt, the
frontend constant, and the docs together, after the owner approves new
wording (design decision D13).

## Rules

- No file in `backend/app/evaluation_*.py` or `backend/tests/evaluation/`
  changes.
- Production code MUST NOT call an Instacart API.

## Basis

- Owner decision D12 in
  [docs/design/chat-architecture-proposal.md](../../docs/design/chat-architecture-proposal.md):
  remove the adapter after the Kroger cart ships.
- Owner decision, 2026-10-30: the conversation suite is separate, and
  `grocery-eval-v1` keeps its 30 scenarios and 138 slots.
- Owner decision, 2026-10-30: retire the adapter, keep the suite, and
  change the notice in a later item.

## Consequences

- The handoff services stay in the repository with the frozen suite as
  their only caller.
- A test in `backend/tests/test_evaluation_duplicate_handler.py` that
  forbids a call to the removed HTTP client loses its target. The guard
  changes; the evaluation code does not.
- `.claude/agents/provider-dev.md` still names the Instacart handoff. A
  change to that file MUST ship as its own pull request.
