# CAP 6938 Project Plan: Financial and Environmental Wellness Intelligence Agent

## 1. Project objective

Build a small AI knowledge system that combines financial context, environmental context, and physical-activity data to produce evidence-based wellness insights.

The MVP will answer one narrow question:

> Does financial context, environmental context, or their combination provide useful information for predicting a user's daily step count?

The core experiment compares three feature sets:

```text
Model A: financial features                 -> daily steps
Model B: environmental features             -> daily steps
Model C: financial + environmental features -> daily steps
```

The project measures predictive association. It does not claim that finances or location cause a health outcome.

After the experiment works, a Bedrock-powered agent will retrieve the measured evidence, run approved analysis tools, and explain the result. The LLM will not calculate metrics or inspect raw private records on its own.

## 2. MVP-first philosophy

The first goal is a straight, visible path that works from end to end. The MVP does not need a frontend, GraphRAG, Pinecone, a complex neural model, SageMaker, or a full production AWS architecture.

The MVP uses:

- Docker Compose on the M1 Max
- FastAPI
- PostgreSQL
- synthetic data
- deterministic Python tools
- linear regression and random forest
- Amazon Bedrock for tool selection and grounded explanation

A REST request from `curl`, Postman, or the FastAPI documentation page is enough for the first demo. A small frontend MAY be added after evaluation is stable.

## 3. Local architecture

```text
                         User question
                               |
                               v
                       FastAPI endpoint
                               |
                               v
                    Bedrock agent adapter
                               |
            +------------------+------------------+
            |                  |                  |
            v                  v                  v
     Finance tool       Environment tool      Health tool
            |                  |                  |
            +------------------+------------------+
                               |
                               v
                         PostgreSQL
                               |
                               v
                    Prediction/comparison tool
                               |
                               v
                Grounded answer with evidence IDs
```

For the first version, Docker Compose runs only FastAPI and PostgreSQL. Bedrock is the only AWS dependency. Model training can run as a local command or background process.

The application SHOULD hide Bedrock behind a small provider interface, such as `LLMProvider.respond(...)`. This keeps the application independent of one model family and lets a later version use another Bedrock model or a local model.

## 4. PostgreSQL schema

Keep the data model relational because the MVP uses dated, structured, numerical observations.

```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    display_name    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE daily_finance (
    user_id                 BIGINT NOT NULL REFERENCES users(id),
    observation_date        DATE NOT NULL,
    total_spending          NUMERIC(12, 2) NOT NULL,
    grocery_spending        NUMERIC(12, 2) NOT NULL,
    restaurant_spending     NUMERIC(12, 2) NOT NULL,
    transportation_spending NUMERIC(12, 2) NOT NULL,
    fitness_spending        NUMERIC(12, 2) NOT NULL,
    discretionary_spending  NUMERIC(12, 2) NOT NULL,
    cash_flow               NUMERIC(12, 2) NOT NULL,
    source                  TEXT NOT NULL,
    PRIMARY KEY (user_id, observation_date)
);

CREATE TABLE daily_environment (
    user_id             BIGINT NOT NULL REFERENCES users(id),
    observation_date    DATE NOT NULL,
    park_count           INTEGER NOT NULL,
    gym_count            INTEGER NOT NULL,
    grocery_store_count  INTEGER NOT NULL,
    restaurant_count     INTEGER NOT NULL,
    location_type        TEXT NOT NULL,
    source               TEXT NOT NULL,
    PRIMARY KEY (user_id, observation_date)
);

CREATE TABLE daily_health (
    user_id              BIGINT NOT NULL REFERENCES users(id),
    observation_date     DATE NOT NULL,
    steps                INTEGER NOT NULL CHECK (steps >= 0),
    resting_heart_rate   NUMERIC(5, 2),
    sleep_minutes        INTEGER,
    intensity_minutes    INTEGER,
    stress_score         NUMERIC(5, 2),
    source               TEXT NOT NULL,
    PRIMARY KEY (user_id, observation_date)
);

CREATE TABLE model_runs (
    id                    BIGSERIAL PRIMARY KEY,
    model_name            TEXT NOT NULL,
    feature_set           TEXT NOT NULL,
    data_version          TEXT NOT NULL,
    trained_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    mae                   NUMERIC NOT NULL,
    rmse                  NUMERIC NOT NULL,
    r_squared             NUMERIC NOT NULL,
    artifact_uri          TEXT
);

CREATE TABLE predictions (
    id                    BIGSERIAL PRIMARY KEY,
    model_run_id          BIGINT NOT NULL REFERENCES model_runs(id),
    user_id               BIGINT NOT NULL REFERENCES users(id),
    observation_date      DATE NOT NULL,
    predicted_steps       NUMERIC NOT NULL,
    actual_steps          INTEGER,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The MVP only needs `steps` from the health table. The other health columns reserve a clear extension path.

## 5. Synthetic data strategy

Start with 90 days of synthetic observations for several synthetic users. Use a fixed random seed so every run is reproducible.

Create varied profiles instead of encoding a simple rule such as "more money means more activity":

```text
Profile 1: lower discretionary income, higher activity
Profile 2: higher discretionary income, higher activity
Profile 3: higher discretionary income, lower activity
Profile 4: lower discretionary income, lower activity
```

Include weekday effects, weather or access variation, random noise, missing records, and a few controlled outliers. Keep the generation rules in version control. Record the seed and dataset version with each model run.

Synthetic data can prove the system path and evaluation code. It cannot prove a real-world relationship. The final report MUST label synthetic results as system-validation evidence, not population evidence.

## 6. Deterministic tools

Build and test the tools before adding the agent.

```python
get_financial_context(user_id, start_date, end_date)
get_environment_context(user_id, start_date, end_date)
get_health_context(user_id, start_date, end_date)
run_activity_prediction(user_id, start_date, end_date, feature_set)
compare_periods(user_id, period_a, period_b)
```

Each tool returns validated JSON with:

- the requested date range
- the computed values
- record counts and missing-data warnings
- the data source
- evidence or query IDs
- the model version when a prediction is used

Example:

```json
{
  "user_id": 1,
  "start_date": "2026-08-01",
  "end_date": "2026-08-31",
  "average_steps": 6850,
  "record_count": 31,
  "source": "synthetic-v1",
  "evidence_id": "health:user-1:2026-08"
}
```

FastAPI endpoints should expose these results before the LLM is connected. This proves the database and computation path independently of agent behavior.

## 7. Simple models and metrics

Start with two models:

1. Linear regression as an interpretable baseline.
2. Random forest as a simple nonlinear comparison.

XGBoost MAY be added after the baseline works. Neural networks are unnecessary for the MVP.

Train each algorithm with the three feature sets. Use a time-aware split so later dates do not leak into earlier training data. If multiple users are present, also report whether the split permits the same user in both train and test sets.

Report:

- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- R-squared
- a naive baseline, such as the training-set mean step count

Also report the sample size, feature list, split method, random seed, and missing-data policy. Feature importance or linear coefficients may support explanations, but they do not establish causality.

## 8. Bedrock agent design

Use the Amazon Bedrock Converse API with client-side tool use. The application sends tool schemas to the model. The model requests a tool, the application executes it, and the tool result returns to the model.

The agent receives only the minimum evidence needed for the question. It does not receive the full transaction or health database.

Example interaction:

```text
User: Compare finance and environmental factors for User 1 in August.

Agent -> get_health_context(...)
Agent -> get_financial_context(...)
Agent -> get_environment_context(...)
Agent -> run_activity_prediction(..., feature_set="combined")
Agent -> grounded response
```

The final response should include:

- the observed activity value
- the predicted value and model version
- the error or uncertainty
- the strongest measured associations
- evidence IDs
- a clear non-causal statement

The agent MUST NOT invent missing values, diagnose a medical condition, or turn an association into a causal claim.

## 9. Plaid integration

Plaid replaces the mock finance adapter only after the local MVP works.

```text
MockFinanceProvider
        |
        v
PlaidSandboxFinanceProvider
        |
        v
normalized daily_finance rows
```

Use Plaid Sandbox first. Use `/transactions/sync` with its cursor model and test update handling with webhooks. Normalize transactions into daily categories before the agent can use them.

The system should store only the fields required for the experiment. It SHOULD avoid sending raw merchant descriptions, account identifiers, access tokens, or complete transaction records to Bedrock.

Plaid Sandbox proves integration logic, not production data quality. Production access, institution behavior, consent, pricing, and compliance need separate validation.

## 10. Garmin integration

Use the same adapter boundary:

```text
MockHealthProvider
        |
        v
GarminHealthProvider
        |
        v
normalized daily_health rows
```

Garmin Health can supply all-day metrics such as steps, heart rate, sleep, intensity minutes, and stress after user consent and device synchronization. The developer program requires approval before the evaluation environment is available, so Garmin access cannot be an MVP dependency.

Start with daily steps. Add other measures only after their meaning, missingness, and sampling differences are understood. Do not assume continuous location tracking from Garmin health summaries.

## 11. Environmental API integration

Start with synthetic environmental features. Then implement one provider, not several.

Possible first provider:

- Google Places Nearby Search for a managed service with clear place types and radius controls.
- OpenStreetMap data for a lower-cost research path, subject to the selected service's usage and attribution rules.

Normalize the result behind:

```python
get_environment_features(latitude, longitude, radius_meters)
```

Return only the features needed by the model:

```json
{
  "parks_nearby": 4,
  "gyms_nearby": 3,
  "grocery_stores_nearby": 5,
  "radius_meters": 2000,
  "provider": "provider-name",
  "retrieved_at": "2026-08-31T12:00:00Z"
}
```

Use coarse or activity-consented locations. Do not build continuous personal tracking for this project.

## 12. Where RAG belongs

The MVP does not need vector RAG.

The important MVP facts are structured:

```text
average_steps = 6850
restaurant_spending = 420.00
parks_nearby = 3
```

PostgreSQL queries and deterministic tool calls retrieve these facts more accurately and transparently than embeddings. Pinecone would add another service without improving this path. pgvector is also unnecessary at this stage.

Vector retrieval becomes useful when the system adds unstructured text, such as:

- user notes
- research documents
- prior agent analyses
- historical narrative summaries
- long environmental descriptions

At that point, pgvector is the simpler first choice because PostgreSQL already owns the structured data. Use a separate vector service only if measured scale or operational needs justify it.

```text
Structured SQL retrieval + semantic text retrieval -> Bedrock explanation
```

## 13. GraphRAG as a later extension

GraphRAG becomes useful only when questions require stable entities and multi-hop relationships that SQL joins or ordinary retrieval handle poorly.

Example later graph:

```text
User
 |-- MADE_TRANSACTION --> Merchant -- HAS_CATEGORY --> Fitness
 |-- PERFORMED_ACTIVITY -> Run ------ OCCURRED_AT ---> Trail
 |-- LIVES_NEAR --------> Area ------ HAS_AMENITY ----> Park
 |-- HAS_METRIC --------> DailyStepCount
```

This could answer questions such as:

> During high-activity periods, which types of places and spending patterns were connected to those activities?

GraphRAG should be added only after a test set shows that multi-hop graph retrieval improves answer quality enough to justify graph construction and maintenance.

## 14. EvoGraph-R1 inspiration without its complexity

EvoGraph-R1 provides a useful design idea: retrieval can be iterative, and an agent can identify a knowledge gap before deciding whether to retrieve, search, edit a graph, or answer.

Its main contribution is more specific than "GraphRAG is better than RAG." It uses a persistent multimodal hypergraph as an environment. An RL-trained policy selects `GRAPHRETRIEVE`, `WEBSEARCH`, `GRAPHEDIT`, or `ANSWER`. Graph edits can insert, update, or delete graph content.

This project can borrow three principles:

1. Keep evidence persistent and traceable.
2. Let tool results inform the next action.
3. Record failures and missing knowledge instead of hiding them.

The project will not reproduce EvoGraph-R1's multimodal hypergraph construction, Markov decision process, GRPO training, trajectory rewards, or self-editing graph. Those features address a different research scale. An automated graph edit is also not guaranteed to be correct.

## 15. AWS migration mapping

Move one component at a time after the local checkpoint.

| Local component | First AWS target | Later option |
|---|---|---|
| FastAPI container | ECS on Fargate | API Gateway plus Lambda for short operations |
| PostgreSQL container | RDS for PostgreSQL | Aurora PostgreSQL if scale justifies it |
| Local scheduled job | EventBridge Scheduler | Step Functions for multi-step workflows |
| In-process job handoff | SQS | Dead-letter queues and retry policies |
| Local worker | Lambda or ECS task | Separate ingestion and model workers |
| Local model artifact | S3 plus ECS/Lambda loading | SageMaker endpoint if serving needs justify it |
| Environment variables | Secrets Manager | KMS-backed rotation policies |
| Local logs | CloudWatch Logs and Metrics | Traces, alarms, and dashboards |
| Bedrock provider | Bedrock Runtime | Guardrails or AgentCore only if measured needs justify them |

The first cloud version can remain small:

```text
FastAPI on ECS
   |-- RDS PostgreSQL
   `-- Amazon Bedrock
```

A successful local test does not prove an AWS deployment. A successful AWS deployment does not prove model quality. Report each type of evidence separately.

## 16. Floci's role

Floci belongs between the plain local MVP and real AWS.

Use it to test AWS-shaped integration code for services such as SQS, EventBridge, Lambda, S3, Secrets Manager, and CloudWatch without creating cloud resources for every development run.

```text
Plain local MVP
    -> Floci event-driven integration tests
    -> small real AWS deployment
    -> production hardening
```

Floci is not required before the MVP checkpoint. It emulates service APIs and selected behavior, but it does not prove IAM behavior, quotas, managed-service performance, regional availability, billing, or production reliability in AWS.

Floci's Bedrock Runtime can return stubbed responses or proxy to another model backend. That is useful for contract tests, but it is not evidence that a real Bedrock model completed the task.

## 17. First working demo

The first demo uses synthetic User 1 and August data.

```text
POST /agent/analyze

{
  "user_id": 1,
  "start_date": "2026-08-01",
  "end_date": "2026-08-31",
  "question": "Compare financial and environmental factors and explain the activity level."
}
```

Expected execution:

```text
FastAPI
  -> Bedrock requests health context
  -> application queries PostgreSQL
  -> Bedrock requests financial context
  -> application queries PostgreSQL
  -> Bedrock requests environmental context
  -> application queries PostgreSQL
  -> Bedrock requests the combined prediction
  -> application runs the versioned model
  -> Bedrock writes a grounded response
```

Example response:

> User 1 averaged 6,850 daily steps in August. The combined model predicted 7,020 steps, an absolute error of 170 steps. In this dataset, environmental features contributed more than financial features. Greater park access was associated with higher activity. This result is predictive and does not establish causation. Evidence: `health:user-1:2026-08`, `finance:user-1:2026-08`, `environment:user-1:2026-08`, model `combined-rf-v1`.

If this request works, produces traceable evidence, and passes the evaluation checks below, the concept works.

## 18. Build order and MVP-complete checkpoint

1. Create Docker Compose with FastAPI and PostgreSQL.
2. Create and migrate the schema.
3. Generate the versioned synthetic dataset.
4. Expose one deterministic FastAPI context endpoint.
5. Implement and test all retrieval and comparison tools.
6. Train the baseline and combined models; save metrics and versions.
7. Add the Bedrock tool-use loop and grounded response format.
8. Run the end-to-end test set and record evidence.

```text
============================================================
MVP COMPLETE

- One narrow request runs end to end.
- Each tool has deterministic tests.
- The three feature conditions have measured model results.
- The agent selects valid tools and cites returned evidence.
- Latency, cost, reliability, and failures are recorded.
============================================================
```

Do not move the checkpoint past external API integration.

After the checkpoint:

9. Add Plaid Sandbox.
10. Add the Garmin adapter when access is approved.
11. Add one environmental provider.
12. Expand the evaluation dataset with API and failure cases.
13. Test event boundaries with Floci.
14. Deploy the small AWS version.
15. Add monitoring and CI/CD.
16. Add pgvector only for an actual text-retrieval requirement.
17. Add GraphRAG only after a measured multi-hop retrieval need.

## 19. Evaluation plan and course requirements

The course's System Implementation Track requires a working AI agent or recommendation system for a specific task. It also requires one narrow end-to-end path, a measurement at each component, and evaluation of behavior, cost, reliability, and representative failures. The final deliverables include an eight-page double-column paper, code, and a demo.

Use a fixed question set with known expected evidence and tool paths.

| Layer | Required measurements |
|---|---|
| Data ingestion | records accepted/rejected, missing fields, duplicates, freshness |
| Retrieval tools | correct rows, correct date range, valid arguments, latency |
| Prediction | MAE, RMSE, R-squared, naive baseline, feature-set comparison |
| Agent | tool-selection accuracy, argument accuracy, unnecessary tool calls |
| Grounding | supported factual claims divided by total factual claims |
| End-to-end | answer correctness, completion rate, latency, cost per answer |
| Reliability | timeouts, retries, partial-data handling, recovery rate |
| Failure analysis | representative data, model, tool, and agent failures |

Minimum evaluation artifacts:

- a versioned evaluation question set
- expected tool calls and arguments
- expected evidence records
- model result tables for finance, environment, and combined conditions
- request traces with tool durations and token usage
- a failure log with at least one example per failure class
- a limitations section

The course also requires individual work. AI tools may refine student-written material, but the student remains responsible for the implementation, evidence, analysis, and final report.

## 20. Privacy, security, and responsible-use caveats

- Use synthetic data and Plaid Sandbox for the MVP.
- Obtain explicit consent before collecting financial, health, or location data.
- Collect the minimum fields needed for the stated experiment.
- Keep provider access tokens and secrets out of source code, prompts, logs, and model inputs.
- Encrypt sensitive data in transit and at rest in a real deployment.
- Separate user identities from analytical records where practical.
- Use least-privilege database and AWS roles.
- Send aggregated features to the LLM instead of raw transactions or detailed health records.
- Reduce location precision and define a retention and deletion policy.
- Keep an audit trail of ingestion, tool calls, model versions, and evidence used.
- Treat the output as an informational pattern analysis, not medical or financial advice.
- Do not infer protected traits, diagnose conditions, or make causal claims from observational data.
- Review the current provider terms, licensing, and data-handling requirements before any production use.

## 21. Concise next steps

1. Create the repository skeleton and Docker Compose file.
2. Implement the schema migration.
3. Generate 90 days of reproducible synthetic data for four profiles.
4. Build `get_health_context()` and expose it through FastAPI.
5. Add the finance and environment tools.
6. Train the first linear-regression comparison.
7. Define ten evaluation questions before adding Bedrock.

The first near-term milestone is simple: load synthetic data into PostgreSQL and return one complete, validated health-context response through FastAPI.

## References

- CAP 6938 course slides, *L01: Introduction to AI Knowledge Systems*, especially slides 4, 10, 12, 20, and 23.
- *EvoGraph-R1: Self-Evolving Multimodal Knowledge Hypergraphs for Agentic Retrieval*, project source PDF.
- [Amazon Bedrock tool use](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html)
- [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Plaid Transactions](https://plaid.com/docs/transactions/)
- [Plaid Sandbox](https://plaid.com/docs/sandbox/)
- [Garmin Health API](https://developer.garmin.com/gc-developer-program/health-api/)
- [Google Places Nearby Search](https://developers.google.com/maps/documentation/places/web-service/nearby-search)
- [Floci AWS emulator](https://floci.io/aws/)
- [Floci Bedrock Runtime behavior](https://floci.io/floci/services/bedrock-runtime/)
