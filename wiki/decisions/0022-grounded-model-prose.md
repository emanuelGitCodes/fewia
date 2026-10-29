# 0022 — Grounded model prose in the chat

- Date: 2026-10-29
- Status: accepted

## Decision

The chat model writes the reply that the user reads. Deterministic tools
own every number. A server validator checks the reply before the server
stores it or shows it. A reply that fails the check never reaches the
user. The server stores a fallback sentence built from the same tool facts.

This decision replaces the template-only answer rule from commit
`5cbc77ae` ("Ground final answers in validated plans", 2026-10-02). That
rule made `render_public_answer` the only source of user-facing text. It
was a design choice for the 95 percent supported-claims target. It was not
a course or owner contract.

The design is in
[docs/design/chat-architecture-proposal.md](../../docs/design/chat-architecture-proposal.md),
sections 4.4 and 4.5.

## Rules

- Every money, mass, energy, count, and percent token in a reply MUST
  match a fact that a tool returned in the same turn.
- A reply MUST NOT claim that a meal is gluten-free, allergy-safe,
  celiac-safe, or medically suitable.
- A money total MUST carry the estimate notice.
- The evaluation record MUST NOT hold model prose. It holds the
  propositions, the validator verdict, the trace, and a SHA-256 hash of the
  reply. The 2026-10-04 owner contract stays in force.
- Hidden model reasoning MUST NOT be stored.

## Basis

- `.codex/project-context.md:62`: "The LLM interprets requests, asks
  questions, and selects typed tools."
- `.codex/project-context.md:65`: the system stores tool traces and
  user-facing explanations, not hidden model reasoning. Provider text is
  untrusted. The validator is the trust boundary for that text.
- [0012](0012-tool-calling-orchestration.md): the model MUST NOT calculate
  the remaining grocery budget. Tools still calculate every number.

## Consequences

- The claims target becomes a grounding target: the share of replies that
  pass the validator, and the fallback rate.
- An evaluation batch after this change does not compare with one before
  it.
- Phase 3 of the design adds the validator, the final prose turn, and the
  `decline` tool. Until phase 3 ships, the server templates stay.
