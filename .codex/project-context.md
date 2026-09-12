# Grocery bot project context

The user approved Plaid Sandbox, parked Instacart development shopping-list
links, real Bedrock, local web chat, a small meal catalog, labeled sample
prices, stored USDA macros, and a labeled Spoonacular overlay.
Floci runs in the default local stack with SQS jobs and S3 evaluation exports.

Read root `AGENTS.md` and `.codex/TEAM.md` before task actions. Read the root
plan, wiki index, and course sources as required. Their health-prediction
scope predates this pivot. The earlier plan under `plans/` also predates the
web-chat, estimate, and Floci decisions. Do not resume its live-price
prerequisite, frontend deferral, or health-model training.
This brief records accepted scope, not authority for unrelated changes.
Saved local `main` at this snapshot is `0c6d571` (USDA per-100 g overlay, pull request 68).
The coordinator verified that SHA from local `git log main`.
Remote `HEAD` was not queried.
This brief MUST NOT claim current GitHub `main`.
Pull request 42 on 2026-09-07 remains the historical published foundation.
The prior current-build source base is `c0357d6`.
This snapshot is a verified source base, not a live Local HEAD label.

A 2026-09-08 MFA checkpoint called continuity unfinished, handoff UI
unfinished, features paused, and Instacart release proof required.
Those claims are historical. They are not current scope.

## First release

- React/TypeScript chat, FastAPI, PostgreSQL, worker, and Floci in Compose.
- Loopback access and one server-selected demo user. Public hosting follows later.
- Direct REST adapters; MCP is not a prerequisite.
- Real Bedrock through `LLMProvider` in `backend/app/agent/`.
- Unattended runtime IAM user `fewia-bedrock-runtime` for Compose chat.
- Human MFA profile `fewia-bedrock-dev` stays for that separate path.
- Explicit endpoints and separate Floci dummy credentials and Bedrock credentials.
- Instacart adapter retained. `instacart_configured` stays false while IDP is closed.
- Stored USDA nutrition for catalog ingredients. No runtime FoodData Central key.
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

Compute calories, protein, carbs, and fat from consumed recipe quantities.
Include pantry items in nutrition. Do not use package counts for macros.
Cite USDA. Do not state medical, allergy, or safety claims.

Use versioned sample prices. Always label estimates:

> Estimated from the demo price catalog. Instacart prices, availability,
> taxes, delivery fees, and tips are not verified.

Missing prices produce incomplete estimates. Instacart links prove handoff,
not pricing or inventory. Budget acceptance uses sample-catalog integer cents.
Spoonacular average cost MAY appear as a labeled overlay. It MUST NOT change
`accepted` or `total_cents`. It is not a live store price.
Validate vegetarian/vegan preferences and ingredient exclusions against
catalog facts. Clarify unknown restrictions. Do not certify retailer products
or cross-contact safety. Spending older than 24 hours requires refresh or an
explicit temporary cap before finalization.

## Runtime and evidence

The LLM interprets requests, asks questions, and selects typed tools.
Application tools own arithmetic and validation. Limit each job to eight model
turns and three planner revisions. Store tool traces and user-facing explanations,
not hidden model reasoning. Provider text is untrusted. Never send credentials
or raw bank records to the model. Validate handoff URLs before navigation.

Chat and form continuity is complete locally. Handoff controls are complete
locally. Instacart remains unavailable. An uncertain Instacart write needs a
visible retry choice, not blind replay. Cache unchanged-plan links.

Compose chat uses the unattended runtime user. Credentials live outside Git
with file mode `600`. Application containers do not use human MFA.
The human MFA role is unchanged. Do not print account ids or access keys.

PostgreSQL owns jobs and outbox state. Handle duplicate SQS delivery, leases,
crashes, visibility extension, retries, and dead letters. Serialize Plaid Item
syncs. Apply changes and the final cursor atomically. Evidence snapshots need
immutable revisions.

Use 30 scenarios repeated three times: spending/budget 5, meal planning 7,
follow-up/pantry 5, missing/impossible requests 4, provider failures 5, and
adversarial text 4. Freeze the model, prompts, and catalog per evaluation.
Compare with the deterministic planner. Report task success, valid tools,
supported claims, clarification, latency, and estimated model cost.
Targets: 90% task success and 95% supported claims; zero tested constraint
violations in accepted plans, secret leaks, or purchase attempts.
Separate fixture, Sandbox, live provider, emulator, and deployed evidence.

Bedrock live chat evidence exists on local Compose hosts 5173 and 5174.
Plaid Sandbox adapters exist. Live Sandbox evidence remains pending.
Instacart development evidence is blocked while IDP is closed.
That parked adapter is not a current release gate.
Spoonacular overlay is optional and labeled. Job-result retention still
exceeds the one-hour delete rule. In-memory expiry deletes are not proven.
The evaluation runner has 90 slots, 42 scored, and 48 unassessed.
No 90-run model-quality evaluation exists.
The user resumed the build.
Next application work is Spoonacular retention and evaluation after the graph and wiki prerequisite.
This docs refresh does not implement pending features.
Graph artifacts are local and ignored; verify manifest/source hashes before use.
This brief MUST NOT claim a completed graph.

Provider fakes permit development while a vendor stays pending.
This brief does not declare a product release.
Preserve old migrations and user changes. Retire legacy routes after the new
path works. Table deletion needs a separate retention decision.
