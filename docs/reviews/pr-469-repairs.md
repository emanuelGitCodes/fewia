# PR 469 repair record

Scope: the six confirmed review findings and the stale-cursor case found during repair.
The repair branch starts at `fddb358c3aa05c27cb1bdd78aa050c76a6e67ccb`.

| Finding | Repair contract | Regression proof |
|---|---|---|
| F1: skipped page | Explicit continuation uses the complete checked cursor. Model offsets and filters cannot replace it. | Wrong offset, omitted filters, repeated pages, and frontend prefix cases. |
| F2: lost cursor | Ordinary replies retain the checked cursor. New type requests clear it even without a tool call. Completed searches replace it; exhaustion clears it. | Search, more, budget, more; chicken, vegan request, no tool, more; ordinary reads; final page. |
| F3: unrelated fallback | A continuation without a search uses neutral text. A cursorless search cannot restart an old page. | No-tool and attempted-search cases before and after exhaustion. |
| F4: omnivore regression | Explicit omnivore queries search the unrestricted catalog while preserving explicit filters. | Both query forms, filtered second page, and all forty recipes without repeats. |
| F5: wrong cards | Checked choices supply cards for clarification, planned, and needs-revision replies. | Model and component tests; desktop and mobile browser checks. |
| F6: false-positive gold | C18 requires the gluten ingredient constraint. The runner carries checked search cursors. | Both wrong-query counterexamples, repeated/skipped page checks, and cursor propagation. |

The conversation corpus is `conversation-eval-v1.3`, with eighteen scenarios and thirty-one turns.
Repair round 1 moved the corpus from v1.2 to v1.3. It adds literal `total_matches` golds, pinned reference pages, and the manifest identity fields.
C16 checks three vegetarian search pages with a budget question between pages.
The frozen grocery corpus remains unchanged. New conversation results do not compare directly with v1.1.
Reference page identities come from fixed deterministic search inputs, independently of the model's actual call.
Observation records retain hashes and safe tool facts, not model prose or hidden reasoning.

Sol, Terra, and Luna wrote the scoped repairs at `xhigh` by owner request.
Astra supplied bounded advice on prefixes, exhaustion, modifiers, and explicit new type requests.
The writer models and effort override the older automatic ladder for this work only.
Each writer ran through `dev_supervisor`. Coordinators and juniors ran checks and commits.
Every commit ran the gitleaks hook. Independent reviews use a different model from the writer.

Run the required gates with an isolated PostgreSQL database as described by the gates skill.
The final integrated record is keyed by the committed SHA in `.fewia-supervisor-gates/`.
Review reports are keyed by SHA and model in `.fewia-supervisor-reviews/`.
The loop ledger records checks, repair rounds, model usage, and live-call limits.
Six additional live Nova turns used revision `0c18c563`. One continuation needed a retry;
its neutral reply preserved the cursor. The final new-type guard has deterministic verification only.

This work does not change provider credentials, retailer writes, deployment, or budget arithmetic.
The review's remaining parser limitations and local stack revision mismatch stay separate from these six fixes.
The small measured search cost does not justify a cache or a new recipe database.
