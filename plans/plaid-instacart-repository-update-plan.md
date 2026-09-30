# Plaid and Instacart Repository Update Plan

**Status:** Superseded. See `.codex/project-context.md` and
`wiki/decisions/`. Plaid work is paused, and decision 0010 parks Instacart.

**Date:** 2026-09-03

**Repository:** `fewia`

**Course track:** CAP 6938 System Implementation Track

## 1. Decision

The project will become a budget-aware grocery planning agent.

The agent will use Plaid for verified grocery-spending context. It will
use Instacart for product discovery and a shopping-list or cart handoff.
Amazon Bedrock will provide the language model and tool-use loop.

The project title will be:

> **Budget-Aware Grocery Planning Agent Using Plaid and Instacart**

The repository name MAY remain `fewia`. A repository rename does not
improve the course evaluation and creates avoidable configuration work.

This plan does not authorize implementation. The user releases each work
item or stack separately.

## 2. Problem statement

People often know how much they want to spend on groceries. They do not
always know how to convert that limit into a complete shopping list.

The agent will combine two knowledge sources:

1. Plaid Sandbox transaction data for grocery-spending context.
2. Instacart product data for product selection and shopping-list creation.

The agent will answer one narrow question:

> Given my explicit grocery limit, recent grocery spending, household size,
> requested meal, and dietary constraints, can you build an Instacart
> shopping list that stays within my effective remaining budget?

The project will test whether an LLM can select the correct tools, use their
results, recover from failures, and return a grounded shopping plan.

## 3. User value

The system will help a user:

- Understand how much of a declared grocery limit remains.
- Convert a meal request into a structured ingredient list.
- Match ingredients to available Instacart products.
- Keep the estimated list total within a firm budget.
- Replace unavailable or expensive products.
- Understand why the final list satisfies the request.

The system will provide budgeting assistance. It will not provide financial,
nutrition, or medical advice.

## 4. Product boundaries

### 4.1 Included in the MVP

The MVP includes:

- Plaid Sandbox only.
- One preconfigured synthetic Plaid user.
- One supported Instacart market or retailer path.
- A small versioned recipe corpus.
- One explicit monthly grocery limit per user.
- Grocery-spending aggregation.
- Product search and normalization.
- Shopping-list construction.
- Budget and dietary validation.
- Product substitution.
- A bounded Bedrock tool-use loop.
- Evidence IDs for every factual result.
- A versioned evaluation set.
- Latency, cost, reliability, and failure measurements.
- A recorded API-based demonstration.

### 4.2 Excluded from the MVP

The MVP excludes:

- Real bank accounts.
- Plaid Production access.
- Real Instacart checkout.
- Payment submission.
- Order placement.
- Personalized financial advice.
- Nutrition scoring.
- Medical advice.
- Health or activity prediction.
- Garmin and Withings.
- Location tracking.
- A vector database.
- GraphRAG.
- A knowledge graph runtime.
- Fine-tuning or training an LLM.
- A custom predictive model.
- A mobile application.
- A production AWS deployment.
- A frontend before the backend checkpoint.

### 4.3 Purchase boundary

The application MUST stop at a shopping-list or cart handoff.

The application MUST NOT submit an order or payment.

The application MUST NOT store a payment method.

The application MUST NOT describe an estimated price as a final checkout
price.

## 5. Budget policy

Plaid reports spending. Plaid does not define the user's budget.

The user MUST provide a monthly grocery limit. The application stores that
limit in a budget profile.

A deterministic tool calculates the remaining monthly budget:

```text
remaining monthly budget =
    user-defined monthly grocery limit
    - verified grocery spending in the budget period
```

The user MAY provide a meal-level limit. The application then calculates:

```text
effective shopping budget =
    minimum of the meal-level limit and the remaining monthly budget
```

The application MUST use fixed-precision arithmetic for money.

The LLM MUST NOT perform budget arithmetic.

The LLM MUST NOT infer income, affordability, or an appropriate grocery
limit.

If Plaid data is stale or incomplete, the application MUST mark the result as
provisional. The application MAY ask the user for a temporary budget override.

## 6. First demonstration

The first demo request will be:

> I have a monthly grocery limit of $450. Based on my Plaid grocery spending
> this month, create an Instacart taco-night shopping list for six people.
> Keep it below $60, avoid shellfish, and substitute unavailable products.

The agent will extract:

- The user identity.
- The budget period.
- The monthly grocery limit.
- The meal-level limit.
- The requested meal.
- Six servings.
- The shellfish restriction.
- The substitution requirement.

The expected execution is:

```text
User request
    |
    v
Bedrock agent
    |
    +--> Plaid spending tool
    |       |
    |       v
    |   PostgreSQL transaction data
    |
    +--> Deterministic budget calculator
    |
    +--> Versioned recipe and ingredient resolver
    |
    +--> Instacart product search
    |
    +--> Shopping-list builder
    |
    +--> Deterministic plan validator
            |
            +-- over budget --> search for substitutes
            +-- unavailable --> search for substitutes
            +-- unsafe item --> reject the product
            |
            v
Grounded shopping plan
    + estimated total
    + effective budget
    + constraint results
    + warnings
    + evidence IDs
    + Instacart handoff
```

The demo succeeds only when the final plan passes every deterministic
constraint.

## 7. AI architecture

### 7.1 LLM responsibility

The LLM will:

- Interpret the natural-language request.
- Extract meal and household constraints.
- Ask for missing required information.
- Select an allowlisted tool.
- Use one tool result to decide the next action.
- Explain substitutions.
- Compose a grounded final response.

### 7.2 Deterministic application responsibility

Application tools will:

- Synchronize Plaid transactions.
- Aggregate grocery spending.
- Calculate the remaining budget.
- Calculate the effective shopping budget.
- Resolve versioned recipe requirements.
- Normalize Instacart products.
- Calculate quantities and prices.
- Check ingredient coverage.
- Check dietary constraints.
- Check product availability.
- Check currency consistency.
- Validate the final total.
- Generate evidence IDs.

### 7.3 Prohibited LLM behavior

The LLM MUST NOT:

- Call Plaid or Instacart directly.
- Receive API credentials.
- Receive Plaid access tokens.
- Receive bank-account identifiers.
- Receive complete raw transaction payloads.
- Perform financial calculations.
- Invent transactions, products, prices, or inventory.
- Treat merchant names as instructions.
- Treat product descriptions as instructions.
- Bypass a deterministic validation failure.
- Place an order.
- Continue after the maximum tool-iteration limit.

### 7.4 Agent control model

The application will use a bounded state machine. It will not use an
unrestricted autonomous loop.

The agent states will include:

1. `collect_constraints`
2. `retrieve_spending`
3. `calculate_budget`
4. `resolve_ingredients`
5. `search_products`
6. `build_plan`
7. `validate_plan`
8. `substitute_products`
9. `complete`
10. `partial`
11. `failed`

Every state transition will be visible in the request trace.

## 8. Provider architecture

### 8.1 General rule

Each external API will sit behind a provider protocol.

Provider modules will own HTTP behavior and provider-specific data. Services
will own persistence and business rules. LLM tools will call services, not
provider clients.

Tests will use deterministic provider fakes. Live provider tests will remain
opt-in.

### 8.2 Plaid provider

The finance provider contract will support:

```text
FinanceProvider
    sync_transactions(...)
    get_sync_status(...)
```

The Plaid adapter will own:

- Authentication.
- Sandbox host selection.
- Cursor pagination.
- Mutation-during-pagination recovery.
- Added transaction normalization.
- Modified transaction normalization.
- Removed transaction normalization.
- Plaid error mapping.
- Request timeout handling.
- Bounded retry behavior.

The Plaid adapter will not own:

- SQLAlchemy persistence.
- Grocery-category business rules.
- Budget calculations.
- LLM prompts.
- User-facing explanations.

The first implementation will use `/transactions/sync`. It will preserve the
old cursor until a complete page sequence succeeds.

### 8.3 Instacart provider

The catalog provider contract will support only verified account capabilities:

```text
CatalogProvider
    search_products(...)
    create_shopping_handoff(...)
```

The exact contract will follow the endpoints enabled for the user's Instacart
account.

The Instacart adapter will normalize available fields into an internal product
candidate. Possible fields include:

- Provider product reference.
- Product display name.
- Price.
- Currency.
- Unit or package description.
- Retailer.
- Availability state.
- Handoff reference or URL.
- Provider timestamp.

The project MUST NOT claim support for a field until the API access gate proves
that the account returns it.

### 8.4 Provider failure model

Both adapters will map provider errors into stable internal categories:

- `authentication_failed`
- `permission_denied`
- `rate_limited`
- `timeout`
- `provider_unavailable`
- `invalid_response`
- `incomplete_data`
- `stale_data`
- `product_unavailable`
- `price_unavailable`

The agent will reason over these categories. It will not parse provider error
text.

## 9. Data model

### 9.1 Existing tables to keep

Keep `users`.

Keep `daily_finance` as the derived daily aggregation table. Do not use it as
the authoritative Plaid sync ledger.

### 9.2 `budget_profiles`

This table will store the user's declared grocery limit.

Suggested fields:

- `user_id`
- `monthly_grocery_limit`
- `currency`
- `timezone`
- `effective_from`
- `updated_at`

The currency will use an ISO currency code. The MVP will support one currency
per request.

### 9.3 `plaid_items`

This table will store Plaid connection and synchronization state.

Suggested fields:

- Internal primary key.
- `user_id`.
- Opaque Plaid Item reference.
- Current sync cursor.
- Connection status.
- Last attempted sync time.
- Last successful sync time.
- Last stable error code.
- Secret reference.

The table MUST NOT store a plaintext Plaid access token.

### 9.4 `plaid_transactions`

This table will provide an idempotent transaction ledger.

Suggested minimum fields:

- Opaque Plaid transaction ID.
- `user_id`.
- Transaction date.
- Amount.
- Currency.
- Primary category.
- Detailed category.
- Pending state.
- Last synchronized time.
- Removal time when applicable.

The MVP does not need merchant descriptions, account numbers, balances, or
complete provider payloads.

The amount-sign convention MUST be documented and tested.

### 9.5 `shopping_plans`

This table will store one validated planning result.

Suggested fields:

- Plan ID.
- `user_id`.
- Budget period.
- Effective budget.
- Estimated total.
- Currency.
- Household size.
- Servings.
- Structured dietary constraints.
- Plan status.
- Evidence ID.
- Provider timestamp.
- Creation time.

The table SHOULD store structured request fields instead of the complete raw
prompt. A raw prompt MAY be retained when a documented evaluation requirement
needs it and the prompt contains no restricted data.

### 9.6 `shopping_plan_items`

This table will store normalized plan items.

Suggested fields:

- Plan ID.
- Ingredient ID.
- Provider product reference.
- Product display name.
- Unit price.
- Quantity.
- Estimated item total.
- Availability state.
- Substitution source.
- Provider timestamp.

### 9.7 `agent_runs`

This table will store one agent execution.

Suggested fields:

- Trace ID.
- `user_id`.
- Sanitized request metadata.
- Start time.
- End time.
- Completion state.
- Input token count.
- Output token count.
- Estimated model cost.
- Final evidence IDs.

### 9.8 `tool_traces`

This table will store individual tool operations.

Suggested fields:

- Trace ID.
- Sequence number.
- Tool name.
- Sanitized arguments.
- Start time.
- End time.
- Duration.
- Retry count.
- Result status.
- Stable error code.
- Evidence IDs.

The trace MUST NOT contain secrets or complete provider payloads.

## 10. Evidence model

The existing date-range evidence format remains valid for finance results:

```text
finance:user-1:2026-09
```

The pivot will add these evidence domains:

```text
budget:user-1:2026-09
catalog:request-<opaque-id>
shopping-plan:<opaque-id>
agent-run:<opaque-id>
```

The final response will cite:

- The finance evidence used for grocery spending.
- The budget calculation evidence.
- The product retrieval evidence.
- The validated shopping plan.
- The agent run.

The application will create evidence IDs. The LLM will only repeat returned
IDs.

## 11. API surface

### 11.1 Deterministic endpoints

The backend will expose deterministic paths before the LLM path:

- `POST /providers/plaid/sync`
- `GET /context/grocery-spending`
- `GET /context/grocery-budget`
- `POST /shopping/plan`
- `POST /shopping/validate`

These endpoints will prove provider, database, and calculation behavior without
model variability.

### 11.2 Agent endpoint

The agent endpoint will be:

- `POST /agent/plan-groceries`

The request will include:

- `user_id`
- Budget period.
- Meal or recipe request.
- Household size or servings.
- Dietary constraints.
- Optional meal-level maximum.
- Postal code or coarse market location when Instacart requires it.
- Natural-language question.

The response will include:

- Structured meal summary.
- Shopping items.
- Effective budget.
- Estimated total.
- Remaining amount.
- Substitutions.
- Constraint results.
- Provider timestamps.
- Warnings.
- Evidence IDs.
- Trace ID.
- Instacart handoff when supported.

## 12. Target repository structure

```text
backend/app/
├── agent/
│   ├── provider.py
│   ├── bedrock.py
│   ├── loop.py
│   └── policy.py
├── api/
│   ├── finance.py
│   ├── shopping.py
│   ├── agent.py
│   └── webhooks.py
├── domain/
│   ├── budget.py
│   ├── catalog.py
│   ├── recipe.py
│   └── shopping.py
├── providers/
│   ├── finance.py
│   ├── plaid.py
│   ├── catalog.py
│   └── instacart.py
├── services/
│   ├── plaid_sync.py
│   ├── finance_aggregation.py
│   └── grocery_planner.py
├── tools/
│   ├── base.py
│   ├── finance.py
│   ├── budget.py
│   ├── catalog.py
│   └── shopping.py
└── synth/
    ├── finance.py
    ├── catalog.py
    └── scenarios.py

eval/
├── cases.yaml
├── recipes.yaml
├── runner.py
├── scoring.py
├── failures/
└── results/
```

The implementation MAY adjust file names. It MUST preserve the provider,
service, deterministic-tool, and agent boundaries.

## 13. Existing code disposition

### 13.1 Keep and adapt

Keep and adapt:

- FastAPI application startup and error handlers.
- PostgreSQL and Docker Compose.
- SQLAlchemy and Alembic.
- The `User` model.
- The `DailyFinance` model.
- Financial aggregation.
- Tool response models.
- Stable tool errors.
- Date-range validation.
- Evidence-ID helpers.
- Synthetic-data reproducibility patterns.
- Strict typing and Ruff configuration.
- The pytest and CI structure.
- The planned `LLMProvider` boundary.

### 13.2 Freeze

Freeze these unfinished items:

- Linear-regression training.
- Random-forest training.
- Finance/environment/combined feature sets.
- Step-count prediction.
- Model artifact generation.
- Activity-prediction endpoint work.

### 13.3 Retain until the new checkpoint

Retain these items until the new path passes:

- `DailyEnvironment`.
- `DailyHealth`.
- `ModelRun`.
- `Prediction`.
- Environment tools and routes.
- Health tools and routes.
- Period comparison.
- Activity-prediction stub.
- Existing tests.
- Alembic revisions `0001`, `0002`, and `0003`.

### 13.4 Remove after the checkpoint

After the new checkpoint passes, a cleanup stack will:

1. Remove legacy routes.
2. Remove legacy tools.
3. Replace legacy test coverage with new domain coverage.
4. Add a forward-only migration for unused tables.
5. Remove unused ML dependencies.
6. Rename the FastAPI application title.
7. Update the plan and wiki.

The implementation MUST NOT rewrite old migrations.

## 14. Security and privacy requirements

### 14.1 Secret handling

The application MUST keep these values out of source control:

- Plaid client ID.
- Plaid secret.
- Plaid access token.
- Instacart API key.
- AWS credentials.
- Bedrock configuration that contains private account data.

Tests MUST use fake credentials or injected provider fakes.

Logs MUST redact secrets before output.

### 14.2 Minimum-data rule

The application will collect only the data required for grocery-spending
aggregation and shopping-list construction.

The model will receive:

- Aggregated grocery spending.
- The calculated effective budget.
- Structured user constraints.
- A bounded product candidate list.
- Validation results.

The model will not receive:

- Plaid credentials.
- Access tokens.
- Account numbers.
- Institution identifiers.
- Full transaction histories.
- Raw provider responses.
- Exact home addresses.

### 14.3 Prompt-injection defense

All provider text is untrusted data.

The application MUST delimit merchant and product text as data.

The application MUST validate every tool call against an allowlist.

The application MUST reject unknown tool names and arguments.

The application MUST test product names that contain malicious instructions.

### 14.4 Dietary constraints

The LLM MAY extract dietary constraints from the request.

A deterministic validator MUST enforce the normalized constraints.

The application MUST fail safely when product information cannot prove that an
item satisfies a required restriction.

The project will not claim clinical allergy safety.

## 15. Evaluation strategy

### 15.1 Evaluation case set

The first complete evaluation will contain 24 cases:

| Case class | Count | Purpose |
|---|---:|---|
| Normal requests | 6 | Test ordinary budgets, meals, and household sizes |
| Missing constraints | 4 | Test clarification and refusal behavior |
| Budget conflicts | 4 | Test recalculation and substitutions |
| Product failures | 4 | Test unavailable items and missing prices |
| Plaid failures | 3 | Test stale data, login errors, and incomplete syncs |
| Adversarial data | 3 | Test prompt injection and malformed provider text |

The case set will contain expected tool calls, expected arguments, required
evidence, and allowed completion states.

### 15.2 Metrics

Measure:

- Tool-selection accuracy.
- Tool-argument accuracy.
- Ingredient coverage.
- Budget compliance.
- Dietary-constraint violation rate.
- Valid substitution rate.
- Unsupported-claim rate.
- End-to-end completion rate.
- Partial-result rate.
- Recovery rate.
- External API calls per answer.
- LLM tool turns per answer.
- P50 latency.
- P95 latency.
- Input tokens.
- Output tokens.
- Estimated cost per answer.

### 15.3 Proposed acceptance targets

These targets are project decisions. They are not professor-defined grades.

- Deterministic money calculations: 100% correct.
- Dietary-constraint violations in the controlled set: zero.
- Real order attempts: zero.
- Credential exposure: zero.
- Tool-selection accuracy: at least 90%.
- Supported factual claims: at least 95%.
- Every failure class: at least one preserved example.

Set latency and cost targets only after the first measured baseline.

### 15.4 Evidence classes

Evaluation reports will label each result as one of these evidence classes:

- Deterministic fake-provider evidence.
- Plaid Sandbox evidence.
- Live Instacart development evidence.
- Real Bedrock evidence.
- Local PostgreSQL integration evidence.
- Deployed AWS evidence, when deployment exists.

One class MUST NOT stand in for another.

## 16. Implementation stages

### Stage 0: Prove API access

This stage makes no repository changes.

#### Plaid access gate

Prove:

1. Sandbox credentials work.
2. The application can create a Transactions test Item.
3. The application can exchange the public token.
4. `/transactions/sync` returns a valid response.
5. The cursor behavior is understood.
6. A simulated transaction update works.
7. `ITEM_LOGIN_REQUIRED` can be reproduced.

#### Instacart access gate

Prove:

1. The API key is active.
2. One authenticated request succeeds.
3. Enabled product, recipe, list, or cart capabilities are known.
4. Available price and inventory fields are known.
5. The handoff capability is known.
6. Rate limits are known.
7. One safe failure response is recorded.

#### Stage 0 stop conditions

Do not implement a provider until its access gate passes.

If Instacart does not return usable prices, the project MUST NOT claim budget
compliance from live Instacart data.

If the account supports shopping lists but not prices, narrow the product to
list generation or reconsider the second API.

### Stage 1: Record the pivot

Create one documentation-only pull request:

`codex/docs-plaid-instacart-pivot`

Base: `main`

Deliverables:

- Add a numbered pivot decision to the wiki.
- Replace Phase 4 and later work in `project-plan.md`.
- Mark the old model path as stopped by decision.
- Extend the evidence-ID decision.
- Update `wiki/index.md`.
- Append one entry to `wiki/log.md`.
- Add stable provider and safety rules to the agent instructions.
- Preserve the existing course sources under `docs/`.

The pull request must contain one consistent objective, one demo request,
explicit exclusions, and measurable completion conditions.

### Stage 2: Add domain and schema foundations

Use one serial stack because the models, migrations, and test fixtures are
shared.

| Merge order | Branch | Deliverable |
|---:|---|---|
| 1 | `codex/grocery-domain-contracts` | Request, product, budget, and plan contracts |
| 2 | `codex/budget-plaid-schema` | Budget profile and Plaid connection state |
| 3 | `codex/plaid-transaction-schema` | Idempotent normalized transaction ledger |
| 4 | `codex/shopping-plan-schema` | Shopping plans and shopping-plan items |
| 5 | `codex/agent-trace-schema` | Agent runs and tool traces |

Each child branch will use the preceding branch as its base. Merge the stack
bottom-up.

Every migration will run upgrade and downgrade tests in an isolated PostgreSQL
database.

The schema stack succeeds when:

- A new database upgrades from zero to head.
- A database at revision `0003` upgrades to the new head.
- Each downgrade restores the preceding schema.
- The test fixtures support every new table.
- The shared development database remains unchanged.

### Stage 3: Add provider implementations

Start both provider stacks only after the schema foundation merges.

#### Plaid stack

| Merge order | Branch | Deliverable |
|---:|---|---|
| 1 | `codex/finance-provider-contract` | Protocol, result types, and deterministic fake |
| 2 | `codex/plaid-sandbox-client` | Authentication and stable error mapping |
| 3 | `codex/plaid-sync-pagination` | Cursor and pagination behavior |
| 4 | `codex/plaid-sync-persistence` | Added, modified, and removed transactions |
| 5 | `codex/grocery-spending-context` | Daily aggregation and grocery-spending tool |
| 6 | `codex/plaid-webhook-refresh` | Idempotent update trigger and failure cases |

#### Instacart stack

| Merge order | Branch | Deliverable |
|---:|---|---|
| 1 | `codex/catalog-provider-contract` | Protocol, product type, and deterministic fake |
| 2 | `codex/instacart-client` | Authentication, timeout, retry, and error mapping |
| 3 | `codex/instacart-product-search` | Product discovery and normalization |
| 4 | `codex/instacart-shopping-handoff` | Verified list or cart handoff |
| 5 | `codex/instacart-failure-cases` | Missing price, unavailable item, and rate limit behavior |

The stacks MAY run at the same time. They MUST NOT edit a shared router or
`main.py`.

The provider stage succeeds when:

- CI uses provider fakes.
- Opt-in tests use real development accounts.
- Provider failures map to stable internal errors.
- Provider-generated text remains untrusted.
- Logs reveal no secret or private provider identifier.

### Stage 4: Add the deterministic planner

Merge both provider stacks before this stage.

| Merge order | Branch | Deliverable |
|---:|---|---|
| 1 | `codex/recipe-requirements` | Versioned recipe and ingredient corpus |
| 2 | `codex/grocery-budget-calculator` | User-limit and Plaid-spending calculation |
| 3 | `codex/shopping-list-builder` | Quantity and product-candidate selection |
| 4 | `codex/shopping-list-validator` | Budget, coverage, dietary, currency, and availability checks |
| 5 | `codex/product-substitution` | Bounded substitute selection |
| 6 | `codex/deterministic-shopping-api` | Shopping plan and validation endpoints |

The deterministic stage succeeds when the same fixed inputs produce the same
validated shopping plan without Bedrock.

Tests will prove:

- Money calculations are exact.
- Over-budget lists cannot succeed.
- Missing prices follow the written policy.
- Dietary violations cannot succeed.
- Unavailable products require substitution or a partial result.
- Every accepted plan covers the required ingredients.

### Stage 5: Add the Bedrock agent

| Merge order | Branch | Deliverable |
|---:|---|---|
| 1 | `codex/llm-provider-contract` | `LLMProvider` protocol and deterministic fake |
| 2 | `codex/agent-tool-registry` | Tool schemas from typed request models |
| 3 | `codex/bounded-agent-loop` | Explicit state machine and terminal conditions |
| 4 | `codex/bedrock-converse-provider` | Real Bedrock Converse implementation |
| 5 | `codex/grocery-agent-policy` | Budget, dietary, privacy, and injection rules |
| 6 | `codex/grocery-agent-endpoint` | Agent endpoint and trace persistence |

Only the Bedrock provider and infrastructure modules MAY import `boto3`.

The agent stage succeeds when:

- Fake-provider tests remain free and deterministic.
- One real Bedrock request selects the correct tools.
- Unknown tool calls fail closed.
- Invalid arguments fail before tool execution.
- Product text cannot override system policy.
- The final response cites valid evidence IDs.
- The loop terminates within its configured bound.

### Stage 6: Add the evaluation harness

Use this stack:

1. `codex/eval-case-corpus`
2. `codex/eval-scoring`
3. `codex/eval-runner`
4. `codex/eval-live-sandbox`
5. `codex/eval-results-and-failures`

The evaluation stage succeeds when:

- The runner emits inspectable result tables.
- Every case records expected and observed tool behavior.
- Every factual claim can be traced to evidence.
- Every failure class has a preserved example.
- Results identify the evidence class.
- Cost and latency come from recorded runs.

### Stage 7: Reach the MVP checkpoint

The MVP is complete only when:

```text
- One narrow request runs from user question to validated shopping plan.
- Plaid Sandbox supplies the spending evidence.
- Instacart supplies verified product information.
- The user supplies the governing grocery limit.
- Deterministic tools calculate every monetary value.
- The list satisfies ingredient and dietary constraints.
- The agent selects valid tools and cites evidence.
- Missing data and provider failures produce safe outcomes.
- Latency, cost, reliability, and failures are recorded.
- No real purchase or payment occurs.
```

Do not build a frontend, deploy to AWS, or remove legacy tables before this
checkpoint.

### Stage 8: Remove the legacy domain

Start this stage only after the MVP checkpoint passes.

The cleanup stack will:

1. Remove health and environment routes.
2. Remove the activity-prediction route.
3. Remove the old comparison tool.
4. Remove unused tests after replacement coverage exists.
5. Add a forward-only migration for unused tables.
6. Remove unused ML dependencies.
7. Rename the FastAPI application title.
8. Update the plan and wiki.
9. Refresh Graphify after the documentation merges.

Applying the table-removal migration to an existing database is destructive.
The executor MUST identify the exact database and obtain approval before it
applies the migration outside an isolated test database.

Git history preserves the old implementation. Do not create a second code
archive.

### Stage 9: Prepare the course demonstration

The recorded demo will show three scenarios:

1. A successful budget-aware shopping plan.
2. Recovery from an over-budget or unavailable product.
3. A safe result when Plaid is unavailable or stale.

The paper will include:

- The system objective.
- The architecture.
- Provider and privacy boundaries.
- Tool definitions.
- The evaluation-case composition.
- Accuracy and completion tables.
- Cost and latency results.
- The failure taxonomy.
- Representative traces.
- Limitations.
- The estimated-price caveat.
- The no-purchase boundary.
- The non-advice statement.

The first demo MAY use FastAPI's API documentation or a controlled client. A
frontend is not required for the first checkpoint.

## 17. Pull-request policy

Each pull request MUST add no more than 150 application-code lines.

Each pull request SHOULD target 100 to 120 added application-code lines. It MAY
use more when the change remains at or below the hard limit.

Tests, documentation, lockfiles, and generated files do not count toward the
limit. Each pull request still requires tests.

Measure each stacked branch against its direct parent.

Every pull request body will state:

- The parent branch or pull request.
- The merge order.
- The files and behavior it owns.
- What it excludes.
- The added application-code count.
- The verification commands and results.
- Whether live provider behavior was tested.

Agents MUST NOT merge a pull request.

The user will review and merge each stack from the bottom upward.

## 18. Ownership and conflict control

| Shared area | Owner |
|---|---|
| `backend/app/models.py` | One schema owner |
| Alembic migrations | The same schema owner |
| `backend/app/config.py` | One provider-integration owner |
| `backend/pyproject.toml` and `uv.lock` | One dependency owner |
| `backend/app/main.py` | One API-integration owner |
| Router registration | The same API-integration owner |
| `backend/tests/conftest.py` | One test-fixture owner |
| `wiki/index.md` | One documentation owner |
| `wiki/log.md` | The same documentation owner |

The Plaid and Instacart stacks may run in parallel only after shared contracts
and schema work merge.

The agent stack waits for the deterministic planner.

Evaluation-case drafting MAY start early. Evaluation execution waits for the
agent contract.

## 19. Verification requirements

Every code pull request will run:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Behavior-critical changes also require a targeted mutation or equivalent
negative test.

Provider work requires:

- Deterministic fake-provider tests.
- Timeout tests.
- Error-mapping tests.
- Redaction tests.
- Idempotency tests where state changes.
- An opt-in live development test.

Migration work requires isolated PostgreSQL upgrade and downgrade tests.

Completion reports will name the exact commands that produced the evidence.

## 20. Repository housekeeping

The repository contains old worktrees from earlier phases. The pivot MUST NOT
delete them automatically.

Before implementation, the executor will:

1. Inspect each worktree and branch.
2. Inspect each related pull-request base.
3. Preserve unmerged changes.
4. Confirm that no child pull request uses a candidate branch as its base.
5. Request approval before worktree or branch deletion.
6. Start the pivot from the verified current `origin/main`.

The existing untracked `.codex/` directory belongs to the user. The executor
MUST preserve it.

## 21. Stop conditions

Stop and request direction when:

- Plaid Sandbox authentication fails repeatedly.
- Instacart account capabilities do not match the required product claim.
- Instacart does not expose prices but the project still claims budget
  compliance.
- A provider contract requires storing a secret in application data.
- Currency data is missing or inconsistent.
- Dietary constraints cannot be validated.
- A migration would modify the shared development database.
- A pull request exceeds 150 added application-code lines.
- A dependent stack starts before its parent merges.
- A provider term conflicts with the planned AI use.
- A live test would place an order or move money.
- Evaluation results do not distinguish fake, sandbox, live, and deployed
  evidence.

## 22. Recommended release order

Use this order:

1. Prove Plaid and Instacart access.
2. Merge the pivot documentation.
3. Merge the domain and schema stack.
4. Merge the Plaid and Instacart provider stacks.
5. Merge the deterministic planner stack.
6. Merge the Bedrock agent stack.
7. Merge the evaluation stack.
8. Pass the MVP checkpoint.
9. Merge the legacy cleanup stack.
10. Prepare the demo and paper evidence.
11. Add a frontend or AWS deployment only if time remains.

## 23. Immediate next action

Run Stage 0 only.

Do not change the repository until both access gates prove the required API
capabilities.

After Stage 0 passes, release the documentation pivot as the first pull request.

## 24. Reference links

- [Plaid Transactions](https://plaid.com/docs/transactions/)
- [Plaid Sandbox](https://plaid.com/docs/sandbox/)
- [Instacart Developer Platform](https://docs.instacart.com/developer_platform_api/)
- [Current repository plan](../project-plan.md)
- [Evidence-ID decision](../wiki/decisions/0007-evidence-id-format.md)
- [Delegation guide](../docs/DELEGATION.md)
- [Repository rules](../AGENTS.md)
