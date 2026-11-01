# PR 469 repair record

Scope: the six original findings, cursor-state follow-ups, and three findings on `6cd6554e`.
The first repairs start at `fddb358c`. The latest follow-up starts at `6cd6554e`.

| Finding | Repair contract | Regression proof |
|---|---|---|
| F1: skipped page | Explicit continuation uses the complete checked cursor. Model offsets and filters cannot replace it. | Wrong offset, omitted filters, repeated pages, and frontend prefix cases. |
| F2: lost cursor | Ordinary replies retain the checked cursor. New type requests clear it even without a tool call. Completed searches replace it; exhaustion clears it. | Search, more, budget, more; chicken, vegan request, no tool, more; ordinary reads; final page. |
| F3: unrelated fallback | A continuation without a search uses neutral text. A cursorless search cannot restart an old page. | No-tool and attempted-search cases before and after exhaustion. |
| F4: omnivore regression | Explicit omnivore queries search the unrestricted catalog while preserving explicit filters. | Both query forms, filtered second page, and all forty recipes without repeats. |
| F5: wrong cards | Checked choices supply cards for clarification, planned, and needs-revision replies. | Model and component tests; desktop and mobile browser checks. |
| F6: false-positive gold | C18 requires the gluten ingredient constraint. The runner carries checked search cursors. | Both wrong-query counterexamples, repeated/skipped page checks, and cursor propagation. |
| R1: ignored restart | Explicit restart reuses the active filters and limit at offset zero. Named saved facets preserve those restrictions after cursor normalization. A no-tool reply retains that first page as pending. | Restart phrases, named facets and aliases, omitted model filters, wrong offsets, prefixes, no-tool restart and more. |
| R2: repeated first page | Search identity treats equivalent conjunctive words as a set. Unsupported and unknown-only searches cannot reuse a cursor. | Reordered, duplicate and stemmed words; filter distinctions; unknown query after omnivore. |
| R3: dairy prose aliases | Recognized dairy-absence claims use authoritative fallback. Exact server caveats and benign ingredient text remain allowed. | Aliases, negated preparation, formatting, exact public budget fallback, partial quantifiers, and milk-free versus milk-freezing distinctions. |

The conversation corpus is `conversation-eval-v1.4`, with nineteen scenarios and thirty-two turns.
It holds literal `total_matches` golds, pinned reference pages, and manifest identity fields.
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
Archived live evidence keeps its recorded revisions. These three follow-up fixes use deterministic verification.

This work does not change provider credentials, retailer writes, deployment, or budget arithmetic.
The remaining parser limitations and local stack revision mismatch stay separate from these fixes.
