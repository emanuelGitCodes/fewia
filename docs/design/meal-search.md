# Meal search by type: typed facets and hard filters

- Date: 2026-10-31
- Status: proposal; item 1 is built (meal-search-01)
- Context: the open design question on PR 460 ("the agent looks up meals
  by type"), [chat-architecture-proposal.md](chat-architecture-proposal.md),
  [grounding-redesign.md](grounding-redesign.md)
- Code reference: PR 460 head `0836b759`

## Problem

A user asks for a meal type: gluten-free, high protein, vegetarian. The
agent MUST answer with catalog meals that have that type, or say that it
cannot check the type. Today it can do neither reliably.

The PR 460 question proposed a `find_meals` tool with one of two stores:

- Option A: read the in-code catalog through `meal_tags.py`.
- Option B: move the recipes into PostgreSQL first.

Both options change the store only. Both keep a contract with one label,
one diet, or one text. That contract cannot express "high protein
vegetarian". The store is not the defect. The defects are the filter
rules, the facet types, the missing cards, and the missing evaluation.

## What exists at `0836b759`

- The prompt in `backend/app/agent/chat_loop.py:48-135` no longer lists
  recipe IDs or labels per meal. It still lists the 22 ingredient
  `id:name` pairs.
- The prompt has two rules that disagree. Line 115 says "call
  search_meals". Lines 124-125 say "name up to three catalog meals with
  that tag", which the model cannot do without the removed listing.
  `backend/tests/test_chat_loop.py:2056` asserts the second rule.
- `search_meals` (`backend/app/agent/catalog_tool.py:21-96`) takes a free
  `query`, a `diet` enum, `exclude`, `min_protein_g`,
  `max_cents_per_serving`, and `limit` 1 to 3.
- `find_catalog_meals` is gone. `wiki/log.md:4447` still names it.

### Defects

1. **Type words rank; they do not filter.** In `catalog_tool.py:245-252`,
   tag and diet words in `query` are ranking signals. Only `diet`,
   `exclude`, protein, and cost are hard filters. The coordinator ran
   `execute_catalog_search({"query": "gluten-free pasta"})` and got
   `chicken_tacos, bean_tacos, vegetable_pasta`.
2. **The fallback ignores the request.** `CLARIFICATION` in
   `backend/app/agent/chat_answer.py:31-49` names the first three vegan
   recipes in catalog order: bean tacos, vegetable pasta, lentil soup.
   The chat uses it on any turn with no tool call or a tool error
   (`chat_loop.py:387-390`). This is the source of the vegetable pasta
   reply to a gluten-free request.
3. **A type the system cannot check gets a false answer.** "dairy free",
   "nut free", and "paleo" return `no_match`, and the reply says "No
   catalog meal matches". The system does not know these types.
4. **No meal cards.** `frontend/src/prototype/planChatModel.ts:74-90`
   builds cards only from `result.request.meals`. `chatTypes.ts:28-36`
   drops the trace `inputs`, so the `recipe_ids` that
   `chat_dispatch.py:292-301` records never reach the page.
5. **Tag rules are outside the evaluation hash.** `catalog_snapshot` in
   `backend/app/evaluation_manifest.py:54-79` hashes recipes and
   ingredients only. Tags, diets, thresholds, and the gluten set can
   change with no change to `catalog_hash`. `conversation.json` and
   `scenarios.json` hold no meal-type scenario.

### What works

- A successful catalog batch returns the server template at once
  (`chat_loop.py:510-519`). `catalog_answer` (`catalog_tool.py:270-303`)
  checks the payload again and adds the safety sentences.
- Model prose never renders a type reply. `grounding.py:243-258` rejects
  any diet label in model prose.

### How tags are made today

- `backend/app/domain/meal_tags.py:95-118` computes tags at import from
  ingredient IDs and `meal_nutrition`.
- Gluten is a list of 4 ingredient IDs (`meal_tags.py:19`).
- Vegetarian and vegan are booleans set by hand in `catalog.py:46-83`.
- The aliases "meat" and "carnivore" map to chicken (`meal_tags.py:41-42`).
  The agent excludes them, but the meal picker still uses them.
- The catalog has 40 recipes in 7 KB of JSON. No migration from 0001 to
  0010 adds a recipe table.

## Design

### Rule 1: code computes every tag

A tag is a function of ingredient facts and the `meal_nutrition`
thresholds. The model MUST NOT assign a tag.

- Add `contains_gluten: bool` to `Ingredient` with no default. A new
  ingredient MUST state it, as it states `vegetarian` and `vegan`.
- Derive the gluten ingredient set from that field.
- Add `MEAL_TAGS`, `MEAL_DIETS`, the thresholds, and the ingredient flags
  to `catalog_snapshot`. A rule change then changes `catalog_hash`.
- Keep the versioned JSON catalog as the store.
- Past a few hundred recipes, compute the tags in a build script. A test
  checks the built file byte for byte, as `build_usda_foods.py` does.

### Rule 2: every type is a hard filter

- Keep the tool name `search_meals`.
- Add `tags`: an array of an enum of `TAG_ORDER` and the diets, in the
  pattern of `proposal_tool.py:28`.
- The server also resolves type words found in `query` to tags.
- Every tag, diet, resolved exclusion, and resolved text word is an AND
  filter. Every returned meal MUST have every applied facet.
- The output adds `applied`, `dropped`, `total_matches`, and `offset`.
- The statuses are `ok`, `no_match`, `unsupported_facet`, and
  `unknown_exclusion`.

### Rule 3: a type the system cannot check fails closed

- The supported vocabulary starts from `grounding.py:254-258`.
- A type outside it returns `unsupported_facet`. The reply names the
  types that the system can check. It MUST NOT say "no match".
- For zero results, the server drops text words first, never a facet,
  and reports them in `dropped`.
- No allergen type other than gluten is added until ingredients carry
  allergen facts.

### Rule 4: the server writes the reply

- The reply comes from the checked tool payload. The caveats depend on
  `applied`.
- The result carries a `choices` list. The page shows each choice as a
  `ChatIdeaCard`.
- The limit stays 3. `offset` gives "3 of 12, say more".
- The prompt keeps one sentence of type vocabulary, the 30 g thresholds,
  the rule against safety claims, and "call search_meals for any meal
  type or open request". Lines 124-125 go.
- The "meat" and "carnivore" aliases go. `mealSearch.ts` filters on the
  exported tags only, so the picker and the agent agree.

### Scale

- Facet filters and word matches cover tens of thousands of recipes in
  PostgreSQL: a GIN index on a `tags text[]` column and a `tsvector` on
  names.
- Recipes move to PostgreSQL when they become editable (`update_recipe`,
  proposal phase 2.1), not for search. Option B now would make
  `build_manifest` need a database.
- Embeddings MAY rank meals inside the filtered set for a vague request
  ("something cozy"). They MUST NOT decide a diet or allergen facet.

## Rejected

- Option A as stated: one facet, ranking instead of filters, no cards, no
  evaluation.
- Option B now: a migration and a seed for 40 rows, and `catalog_hash`
  then needs a database connection.
- Model-written type replies: the validator rejects every diet label by
  design.
- Labels per meal in the prompt: about 900 more input tokens per call, and
  Nova still chose wrong meals.
- Embeddings now: 40 recipes have no semantic gap, and an embedding score
  cannot fail closed.

## Build plan

Each item adds fewer than 150 code lines. Data and tests do not count.

| # | Goal | Files | Lines | Proof |
|---|---|---|---|---|
| 1 | The fallback names no vegan examples on a type request; remove prompt lines 124-125 | `chat_answer.py`, `chat_loop.py` | 40 | A type turn with no tool call never names vegetable pasta |
| 2 | Tags, diets, and resolved words are AND filters; add `applied` and `dropped` | `catalog_tool.py` | 90 | Property test: each returned meal has each applied facet, for all tags and all ingredient words |
| 3 | `tags` enum input; `unsupported_facet` status and reply | `catalog_tool.py`, `meal_tags.py` | 80 | "dairy free" gives the status; the reply names the supported types |
| 4 | Backend `choices` on the result, checked again | `chat_messages.py`, `chat_loop.py` | 50 | A forged payload cannot fill `choices` |
| 5 | Frontend cards from `choices` | `chatTypes.ts`, `chatValidation.ts`, `planChatModel.ts` | 90 | `ideasFromJob` on a search job renders three cards |
| 6 | `contains_gluten` on `Ingredient`; tags in `catalog_snapshot` | `catalog.py`, `meal_tags.py`, `evaluation_manifest.py` | 70 | The snapshot hash changes when a tag rule changes |
| 7 | Meal-type scenarios C13 to C17, gold from the tool | `conversation.json`, corpus test | data | The gold answers come from the deterministic tools |
| 8 | `total_matches` and `offset` | `catalog_tool.py` | 60 | `offset` walks the full set with no repeats |
| 9 | A `MealIndex` protocol with a PostgreSQL implementation, when recipes become editable | new module, migration | later | Both loaders give the same hash |

Item 1 is the smallest change that fixes the reply the user sees.

## Measurement

Scenarios: gluten-free, keto, high protein vegetarian, "cheap vegetarian
dinner", dairy-free (unsupported), and "gluten-free pasta" (zero results,
then the server drops words).

| Metric | Pass bar |
|---|---|
| Each returned meal has each applied facet | 100% (property test) |
| Correct `search_meals` arguments, three repeats | 90% or more |
| Reply matches the deterministic reply when the call is correct | 100% |
| Type turns that end with no tool call | 0 |
| Diet-label claims in model prose | 0 |
| Prompt and tool definitions | under 16,500 characters |
| p50 latency | under 5 s |
| Cost per turn | under USD 0.006 |

Run one live Nova 2 Lite batch after item 7.

## Owner decisions

| Decision | Recommendation |
|---|---|
| Keep `search_meals` or rename it to `find_meals` | Keep it. A rename changes tests and docs for no gain. |
| An unknown free word | A hard filter when it matches a catalog word. Otherwise the reply reports it and ignores it: "No meal mentions beef." |
| Add tags to `catalog_hash` now | Yes. The hash already restarted at decision 0024. |
| Move the 22 ingredient pairs from the prompt into schema enums | Measure after item 7, then decide. |
| Allergen types other than gluten | None until ingredients carry allergen facts. |
| Corpus version | Add the scenarios as v1.1 of the conversation suite. |
| Recipes in PostgreSQL | Tie the move to `update_recipe`, not to search. |
