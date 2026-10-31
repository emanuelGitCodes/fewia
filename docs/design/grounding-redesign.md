# Grounding redesign: server-rendered numbers

- Date: 2026-10-30
- Status: proposed; probe result: placeholders not viable on Nova 2 Lite
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

## Probe result (2026-10-30)

Step 0 ran all 12 scenarios once (22 turns) at revision `f50aa95`. The
reply text stayed in the terminal and was deleted after classification.
The validator rejected 9 prose replies and accepted 3:

| Class | Count | Example |
|---|---|---|
| Validator gap: a verb gives the direction | 3 | "gains about 2.5 g fat and 38 kcal", "drops by 2.8 g", "adds about 38 kcal and 2.5 g of fat" |
| Model computed a number | 2 | per-meal prices that no tool returned; "increases by about 69 g total" |
| Model reused an earlier reply | 2 | a template from history with another meal's numbers |
| User echo, rejected by owner decision | 2 | "type 2", "half the rice" |

The probe resent each rejected final turn twice:

- **A. Placeholders in prose:** 1 of 9 replies held no raw number.
- **B. Final-answer tool:** Nova called `final_answer` in 1 of 9 turns,
  and that reply still held a digit and a number word.

Neither variant clears 90%. Nova 2 Lite does not follow either output
shape, so server-rendered numbers are not viable on this model. The probe
used an unlabeled path list (`f7 = 28.4 g (tool: after.per_serving...)`);
clearer labels MAY help, but a 1-in-9 result leaves little room.

Revised recommendation:

1. Extend the direction rule from p6-01 to a direction verb before the
   number (gain, add, lose, drop, rise, increase, decrease, fall, reduce,
   with optional "by" and "about"), carried across "and" until the clause
   ends. The value still MUST match a signed delta from this turn. This
   covers 3 of 9 rejections in the sample.
2. Keep rejecting computed numbers, reused numbers, and user echoes. The
   validator is right about those 6 of 9.
3. Test Nova 2 Pro on the same probe if the account has it. The model, not
   the architecture, limits format compliance.

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
