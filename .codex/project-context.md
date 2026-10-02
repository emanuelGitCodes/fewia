# Grocery bot project context

The user approved real Bedrock, local web chat, a 40-meal catalog, and
labeled sample prices. Floci runs in the default local stack with SQS jobs
and S3 evaluation exports. The default spending source is `manual`. The
monthly limit that the user enters is the whole budget. Fixture spending
stays optional. Plaid work is last. Decision 0010 parks the Instacart
handoff and adds USDA nutrition and an optional Spoonacular cost overlay.
Decision 0016 keeps sample-catalog cents as the budget figure. Newer
decisions in `wiki/decisions/` override this file.

Read root `AGENTS.md` and `.codex/TEAM.md` before task actions. Read the root
plan, wiki index, and course sources as required. Their health-prediction
scope predates this pivot. The earlier plan under `plans/` also predates the
web-chat, estimate, and Floci decisions. Do not resume its live-price
prerequisite, frontend deferral, or health-model training.
This brief records accepted scope, not authority for unrelated changes.

## First release

- React/TypeScript chat, FastAPI, PostgreSQL, worker, and Floci in Compose.
- Loopback access and one server-selected demo user. Public hosting follows later.
- Direct REST adapters; MCP is not a prerequisite.
- Real Bedrock through `LLMProvider` in `backend/app/agent/`.
- Explicit endpoints and separate Floci dummy credentials and Bedrock credentials.
- Instacart `POST /idp/v1/products/products_link` with `line_item_measurements`.
- No real bank accounts, checkout, orders, or payment submission.

## Planning rules

Support 40 meals. The authoritative list is
`backend/app/domain/catalog_recipes.json`. Support one to three meals and
one to eight servings per meal. Offer supported alternatives for other
requests. `POST /grocery/templates` holds a library of six preset combinations.
The planner keeps a preset only when it fits the available budget, diet,
pantry, and exclusions. The endpoint returns up to six eligible
suggestions. An empty list is possible. Suggestions use labeled sample
prices. They do not reserve money.

The user declares the monthly limit. Subtract net posted grocery spending,
then clamp the remainder to zero. Apply the smaller explicit plan cap when
provided. Show pending spending separately. Plans do not reserve money.
`get_budget_summary` returns read-only facts for available cents, pending
cents, source, and stale warnings.
Use USD, integer cents, and America/New_York budget dates. Aggregate shared
ingredients before package rounding. Remove pantry items only on user input.
Never lower servings or omit ingredients to claim budget compliance.

Use versioned sample prices. Always label estimates:

> Estimated from the demo price catalog. Instacart prices, availability,
> taxes, delivery fees, and tips are not verified.

Missing prices produce incomplete estimates. Instacart links prove handoff,
not pricing or inventory. Validate vegetarian/vegan preferences and ingredient
exclusions against catalog facts. Clarify unknown restrictions. Do not certify
retailer products or cross-contact safety. Spending older than 24 hours requires
refresh or an explicit temporary cap before finalization.

## Runtime and evidence

The LLM interprets requests, asks questions, and selects typed tools.
Application tools own arithmetic and validation. Limit each job to eight model
turns and three planner revisions. Store tool traces and user-facing explanations,
not hidden model reasoning. Provider text is untrusted. Never send credentials
or raw bank records to the model. Validate handoff URLs before navigation.

PostgreSQL owns jobs and outbox state. Handle duplicate SQS delivery, leases,
crashes, visibility extension, retries, and dead letters. Serialize Plaid Item
syncs. Apply changes and the final cursor atomically. An uncertain Instacart
write needs a visible retry choice, not blind replay. Cache unchanged-plan links.
Evidence snapshots need immutable revisions.

Use 30 scenarios repeated three times: spending/budget 5, meal planning 7,
follow-up/pantry 5, missing/impossible requests 4, provider failures 5, and
adversarial text 4. Freeze the model, prompts, and catalog per evaluation.
Compare with the deterministic planner. Report task success, valid tools,
supported claims, clarification, latency, and estimated model cost.
Targets: 90% task success and 95% supported claims; zero tested constraint
violations in accepted plans, secret leaks, or purchase attempts.
Separate fixture, Sandbox, live provider, emulator, and deployed evidence.

Provider fakes permit development while access is pending. Release requires
real Plaid Sandbox, Instacart development, and Bedrock evidence.
Preserve old migrations and user changes. Retire legacy routes after the new
path works. Table deletion needs a separate retention decision.
