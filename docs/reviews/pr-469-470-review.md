# Review of PR 469 and PR 470

This review covers PR 469 at `8cee7e1a` and PR 470 at `27a8f73c`. It sets
the merge order and lists the optimizations that the branch
`claude/conversation-polish` carries.

## Merge order

1. Merge PR 469 (`claude/meal-search-stack` into `main`).
2. Merge PR 470 (`codex/conversation-quality-final`).
3. Merge the follow-up pull request from `claude/conversation-polish`.

PR 470 is stacked on PR 469. Its base is `claude/meal-search-stack`. The
gates count 987 lines for PR 469 and 602 lines for PR 470, so the range
against `main` adds 1,589 source lines. The PR 470 body says 1,577, which
was counted against an earlier PR 469 head. That is above the 1,000-line
limit, so PR 470 MUST NOT merge first or alone.

Before you merge PR 469, retarget PR 470 to `main`:

```bash
gh pr edit 470 --repo emanuelGitCodes/fewia --base main
```

After the retarget, the PR 470 size check counts the full 1,589 lines until
PR 469 merges. A red size check in that window is expected.

Do not use `--delete-branch` on PR 469. The repository does not delete head
branches on merge, and a deleted base closes the child pull request.

## Gate results

| PR | Head | Backend tests | Frontend | Lines | Result |
|---|---|---|---|---|---|
| 469 | `8cee7e1a` | 15,442 passed, 1 skipped | lint, test, build pass | 987/1000 | PASS |
| 470 | `27a8f73c` | 17,156 passed, 1 skipped | not changed | 602/1000 | PASS |

Hosted CI passes all nine checks on both heads. PR 469 has 13 lines left
under the limit, so a code repair on PR 469 itself is not practical. The
repairs go into the follow-up branch.

## Findings

Each finding has a concrete input. "Fail closed" means that the server
replaces a model reply with a template. It does not give a wrong fact.

### PR 470

| # | Severity | Location | Input | Result |
|---|---|---|---|---|
| 1 | Should fix | `current_plan_answer.py:7,125` | "Is my plan ready?", "Is my plan healthy?" | Server clarifies. The model reply is discarded. |
| 2 | Should fix | `current_plan_answer.py:88-91,129` | The `planChatPrefix` fallback message, no saved revision, "Is my plan vegan?" | "Your saved plan is unavailable." The user gave the plan in the message. |
| 3 | Should fix | `chat_loop.py:595-605` | Exhausted vegetarian cursor, "Show me those vegetarian meals again" | "There are no more matching meals." The offset 0 search does not run. |
| 4 | Optional | `current_plan_answer.py:134-152` | "Is any meal in my plan vegan?" | Asks which meal. "any" SHOULD answer for every meal. |
| 5 | Optional | `current_plan_answer.py:62-66` | "Does my plan have dairy?", "Is my plan vegan." | Goes to the model. Only `contain` and a question mark are parsed. |
| 6 | Optional | `evaluation_conversation.py` | `--max-chat-turns 48` | Caps user turns, not provider calls. The ledger shows 82 calls for 48 turns. |

### PR 469

| # | Severity | Location | Input | Result |
|---|---|---|---|---|
| 7 | Should fix | `grounding.py:251-257` | "I made no dairy claims.", "It has no dairyman story." | Rejected. `_DAIRY_ALIASES` runs on squashed text with no word boundary. |
| 8 | Should fix | `grounding.py:274-275` | "It wasn't made with dairy.", "It is not prepared using dairy." | Accepted. The negation and preposition lists are incomplete. |
| 9 | Should fix | `grounding.py` | "This meal contains no milk.", "It is made without milk." | Accepted. Milk absence is checked only as `milkfree`. |
| 10 | Optional | `chat_loop.py:285-318` | Cursor `{chicken, high_protein}`, "more high protein" | Starts a new search. "start over with high protein" keeps the cursor. |
| 10a | Should fix | `grounding.py` | "It contains no gluten.", "This is allergy safe." | Accepted. This gap is older than PR 469. |
| 11 | Optional | `catalog_tool.py:436-439` | Model call "chicken pizza" on a chicken cursor | Continues the cursor. The unmatched "pizza" notice is lost. |

Neither PR breaks a product rule. Money stays in integer cents. No reply
calls a meal allergy-safe. Dairy-free does not map to vegan. No evaluation
record stores model reply text.

## Optimizations

### Code

| Item | Location | Change | Estimated saving |
|---|---|---|---|
| O1 | `current_plan_answer.py` | Resolve properties with `meal_tags.resolve_meal_term`. Clarify only for diet words. | about 20 lines |
| O2 | `current_plan_answer.py:135-168` | Merge the two meal-name selection branches. | about 12 lines |
| O3 | `current_plan_answer.py:88-91` | Reuse the prefix parse in `chat_context.py`. | about 4 lines |
| O4 | `chat_loop.py` | Compute `current_plan_answer` once per request. | about 6 lines |
| O5 | `chat_history.py` | Load the previous search and the exhausted search in one query. | about 10 lines, one query |
| O6 | `chat_context.py` | Compute `restart_type_query` once per message. It runs a catalog search three times now. | about 5 lines |
| O7 | `grounding.py` | Merge `_DAIRY_ALIASES` into the `_DAIRY_ABSENCE` phrase table. This also repairs finding 7. | about 8 lines |
| O8 | `catalog_tool.py:436-444` | Build the identity terms in one helper. | about 10 lines |

### Tests

| Item | Location | Change | Estimated saving |
|---|---|---|---|
| T1 | `test_chat_dairy_claims.py` | Parametrize the claim loops. Keep three `run_chat` fallback proofs. The unit cases stay in `test_grounding.py`. | about 400 lines |
| T2 | `test_grounding.py` | Fold `test_formatted_milk_free_claims_fail` and the contracted-alias test into their parametrized neighbors. | about 60 lines |
| T3 | `test_chat_loop.py` | Make the catalog-word restart test a parameter of the no-tool restart test. | about 40 lines |

### Evidence

`eval/results/artifacts/conversation-quality-20261101/` holds 460 KB. These
files are intermediate data, not evidence:

- `final-probes.json` is byte-identical to `proposal-warning-probes.json`.
- `pre-warning-probes.json` and the three `post-astra/astra-*-before-root.json`
  files are pre-repair snapshots.
- `post-astra/review-*.md` (6 files) hold reviewer-model prose. The evidence
  contract forbids model prose in evaluation records. The owner decides
  whether these files stay.

The follow-up branch does not delete evidence files. The PR 470 body links
this folder as immutable evidence.

## Order of the repairs

The follow-up branch merges third, so the fail-open grounding repairs
(findings 8, 9, and 10a) reach `main` after PR 470. A separate pull request
from `claude/meal-search-stack` can carry them earlier. PR 469 has only 13
lines left, so that pull request MUST be its own stack entry.

## Owner decisions

- Finding 1: PR 470 review round 1 asked that unknown properties such as
  "organic" clarify. Narrowing the clarify set reverses that choice.
- Finding 2: The server can answer from the plan that the client states in
  the message when no revision exists. This is a product choice.
- The six `post-astra/review-*.md` files.

## Not verified

- A live Bedrock run on either head.
- The proposal-card explanation claim in PR 470.
- `test_chat_loop.py`, `test_chat_history.py`, and `test_chat_api.py` line by line.
