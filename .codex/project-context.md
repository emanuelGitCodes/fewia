# Grocery bot project context

The user approved Plaid Sandbox, real Bedrock, local web chat, a small meal
catalog, and labeled sample prices. Quantity-scaled USDA nutrition is in use.
Spoonacular cost is a request-only overlay. Instacart stays parked under
accepted [decision 0010](../wiki/decisions/0010-usda-spoonacular-overlay.md).
The Instacart adapter remains for a future handoff.
Floci runs in the default local stack with SQS jobs and S3 evaluation exports.

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
- Instacart adapter kept for a future `POST /idp/v1/products/products_link`
  handoff with `line_item_measurements`. Live Instacart is not a current
  release prerequisite.
- No real bank accounts, checkout, orders, or payment submission.

## Planning rules

Support chicken tacos, bean tacos, vegetable pasta, chicken-and-rice bowls,
lentil soup, chickpea curry, vegetable stir-fry, baked potatoes with beans,
breakfast burritos, and overnight oats. Support one to three meals and one to
eight servings per meal. Offer supported alternatives for other requests.

The user declares the monthly limit. Subtract net posted grocery spending,
then clamp the remainder to zero. Apply the smaller explicit plan cap when
provided. Show pending spending separately. Plans do not reserve money.
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
not hidden model reasoning. Provider text is untrusted. Public answer facts
render from the validated plan and allowlisted conflicts. They MUST NOT use
untrusted raw LLM prices. Never send credentials or raw bank records to the
model. Validate handoff URLs before navigation.

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

Provider fakes permit development while access is pending. The current local
release still requires real Bedrock evidence and appropriate Plaid Sandbox
evidence. Plaid credentials are absent. Live Instacart development evidence
is not a current release prerequisite. Sample catalog prices remain the
budget-acceptance truth.
Preserve old migrations and user changes. Retire legacy routes after the new
path works. Table deletion needs a separate retention decision.
