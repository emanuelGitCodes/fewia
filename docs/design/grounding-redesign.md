# Grounding redesign: server-rendered numbers

- Date: 2026-10-30
- Status: placeholders rejected after the probe; the verb-led direction rule
  is built (p9-01)
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

## Built: verb-led direction rule (p9-01)

Commits `c3574d6` and `b808dfb`. These rules hold in `grounding.py`:

- A direction verb before an unsigned energy, mass, milli, or percent token
  gives it a sign: gain, add, rise, increase (+); lose, drop, fall,
  decrease, reduce (-). Optional "by" and "about" may sit between them.
- The sign carries to the next unit token across "and" or "," with at most
  three words between. A sentence end, ";", "(", "from", "to", "while",
  "but", "whereas", "than", or another direction verb ends the run.
- A bound token matches only a signed delta from this turn, or a negative
  pool value. It MUST NOT match the absolute pool.
- A base-form verb at a sentence start is an instruction ("Add 5 g"), not
  a change, and binds nothing.
- Counts, money, and ranges are never bound.

Accepted trade-off: a verb that states an absolute amount ("chickpeas add
384 kcal per serving") now fails closed and falls back to the template.

Measured (2026-10-30, Nova 2 Lite, revision `b808dfb`,
`conversation-20261030c`): the validator accepted 13 of 32 prose replies
(0.41), against 9 of 36 (0.25) at `95cfbea` with the same prompt.
Unsupported numbers fell from 59 to 49. The remaining rejections are
`unmatched_number` 15, `number_word` 5, `unsupported_character` 1, and
`forbidden_claim` 1. p50 latency was 3.4 s, p95 12.2 s, and cost USD
0.0053 per turn.

## Built: nutrient binding, basis, and side (pf-01, pf-07)

The validator now checks these rules for a nutrition or energy claim:

- A label binds a number only on the same line. A word before a label
  that is not a known qualifier unbinds the label.
- "changes by N" and "<label> by N" have no direction. They need a sign.
- A "from X to Y" change must read one recorded before and after pair.
  Y - X MUST be a signed delta of that subject, and a direction word MUST
  agree with it. Any words can sit between X and Y. A change with X and
  no Y fails.
- Each fact records its basis (`per_serving`, `total`, `per_100g`) and its
  side (`before`, `after`). A basis phrase after a claim restricts it to
  that basis. "for N servings" names the total only when N is a stated
  `servings` count. A from-to claim matches the basis of its pair.
- A value that exists only before the swap needs a before marker in its
  clause.
- A reply longer than 1,200 characters fails before any scan. The scan
  cost is linear: an adversarial 1,200-character reply takes about 2 ms.

Open shapes: these false claims still pass. The merge base passes them
too.

- A before marker anywhere in the clause unlocks a before-side energy
  value: "Each serving now has 500 kcal instead of the original 480
  kcal.", "Once the swap was done the meal has 500 kcal per serving."
- A trailing "from" counts as a before marker: "After the swap the meal
  has 500 kcal from tofu."
- The "(+D g)" after "X to Y" is not checked against Y - X when no basis
  phrase follows: "Protein 20 to 25 g (+20 g)."
- `FactSet.servings` pools the `servings` key of every payload in the
  turn. "for 2 servings" can match the servings count of another meal.
- A basis phrase before the claim, or one shared by a list, is not read:
  "Per serving, protein is 100 g."
- An unsigned "X to Y" that is a recorded pair reads as that pair, not as
  a range: "After the swap, protein is 20 to 25 g per serving."
- Which food a value belongs to is not checked: "Lentils have 25 g
  protein per 100 g" with the value of tofu.

True claims that now fail and fall back to the server template:

- `_left_ok` unbinds a label after an unknown word: "480 kcal while
  protein is 25 g", "Now protein is 25 g.", "After the swap protein is
  25 g per serving."
- `before_marker` reads 200 characters on each side of the claim. A
  marker farther away in a long clause is missed.

No core test covers the basis and side check on the "about N kcal" path.

## Out of scope

- The guardrail (3.4). C09 gave diabetes diet advice that passed the
  validator. Decision 0025 adds the `medical_claim` check and an optional
  Bedrock guardrail for that class.
- Section 4.6 says the context block carries the last two turns' facts.
  The built context carries `previous_request` and text history only. This
  design keeps it that way: only this turn's facts are numbered.
