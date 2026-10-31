# Grounding redesign: server-rendered numbers

- Date: 2026-10-30
- Status: proposed
- Context: [chat-architecture-proposal.md](chat-architecture-proposal.md)
  section 4.5, decision
  [0022](../../wiki/decisions/0022-grounded-model-prose.md)

## Problem

Two live Nova 2 Lite batches on `conversation-eval-v1` grounded 9 of 36 and
8 of 33 prose replies (target 99%). Most rejections are `unmatched_number`
(24 and 20), then `number_word` (4 and 5) and `forbidden_claim` (2 and 3).
A rejected reply falls back to the server template, so users see correct
numbers, but model prose almost never reaches them.

A diagnostic classified 7 rejections: 3 model errors (numbers reused from an
earlier reply, a number the model computed), 1 validator gap (fixed in
p6-01), 2 rejections by design (an arrow, the word "half"), and 1 echo of
the user's words ("type 2"). Seven of about 50 rejections is a hint, not a
distribution.

A prompt with six plain rules (p6-02) changed nothing, and it moved one
tool choice. Nova ignored the prohibitions. A design that only asks Nova
to avoid numbers will fail the same way.

## Proposal

Build the typed fact list that section 4.5 specifies, and let the server
write every number.

1. **Fact list.** After the tools return, the server builds a numbered list
   for this turn only: `f1 = 474 kcal per serving (what_if_substitute,
   after.per_serving.energy_kcal)`, `f2 = $17.03 (plan total)`, and so on.
   Each entry has an ID, a kind, a value, and a display string. The built
   `FactSet` today is seven unnamed sets plus `deltas`; the list replaces
   it as the validator input.
2. **Final turn.** The final model turn receives the list and writes `{f1}`
   where a number belongs: "The swap brings the meal to {f1}."
3. **Validator.** The reply MUST hold no raw digit and no number word
   outside a placeholder, and every placeholder MUST resolve to this turn's
   list. The character, forbidden-claim, and length checks stay.
4. **Renderer.** The server replaces each placeholder with its display
   string, appends the notice when money appears, and stores the result.
   A failed reply falls back to the template, as today.

This fits decision 0022 as written: tools own every number, and the
validator stays the trust boundary. Records stay hash-only.

What it catches by structure:

- A number reused from an earlier reply is a raw digit, so it fails.
- A computed number has no fact ID, so the model cannot write it.
- Format drift (arrows, "half") stays a by-design rejection.

## Risk: format compliance

Every variant depends on Nova emitting a specific output shape. The tools
check (74 to 82%) says Nova follows tool schemas. Nothing yet says it
follows a placeholder syntax inside prose. Two variants:

- **A. Placeholders in prose.** The final turn writes text with `{fN}`.
- **B. Final-answer tool.** The final turn calls `final_answer` with
  `sentences` and `fact_refs`. Tool schemas may suit Nova better.

A probe decides between them before any code: 5 to 8 failed turns, each
variant once, count replies with a raw digit or number word. A variant that
holds at 90% or more is viable. If neither does, the limit is the model.
Then check whether Nova 2 Pro is enabled before more design work.

## Step 0: full diagnostic

Run the diagnostic on all 12 scenarios, repeat 1 (22 turns). Classify every
rejection. The classes decide whether history reuse, computation, or format
dominates. The output holds reply text, so it stays in the terminal and is
deleted after classification.

## Cost

Average input is about 10,500 tokens per turn; cost is USD 0.0052 per turn
against a 0.006 target. A fact list adds about 10 tokens per fact. The
largest turn (C11) has about 60 values, so about 600 tokens. Variant B adds
a tool schema. Both fit under the target if output stays near 635 tokens.

## Owner decisions (2026-10-30)

- Step 0 and the probe are approved (about USD 0.25).
- User-echoed number words stay rejected.

## Decisions for the owner

1. **User-echoed number words** ("half the rice", "type 2 diabetes").
   Reject them, as today, or allow a word that appears verbatim in the
   user's message. Allowing it opens a grounding hole: a user can plant a
   number the model then repeats.
2. **Repair round** (not recommended). Send a rejected reply back for one
   revision. Decision 0022 says the loop MUST NOT send unvalidated model
   text back, so this needs an amendment. It adds a model call to about 75%
   of turns, which moves p95 latency the wrong way.
3. **Order.** Step 0 and the probe first (paid, about USD 0.25 together),
   then a brief for the winning variant.

## Out of scope

- The guardrail (3.4). C09 gave diabetes diet advice that passed the
  validator. `forbidden_claim` caught 2 or 3 replies per batch. This design
  does not change that class.
- Section 4.6 says the context block carries the last two turns' facts.
  The built context carries `previous_request` and text history only. This
  design keeps it that way: only this turn's facts are numbered.
