# Project Proposal: Financial and Environmental Health Intelligence Agent

## 1. Project Title

**Financial and Environmental Health Intelligence Agent: Evaluating Whether Financial Behavior and Geographic Context Predict Physical Health**

## 2. Project Overview

This project proposes the development of an AI-powered knowledge system that combines personal financial data, health and activity data, and geographic context to investigate whether a person's financial behavior, location, or the combination of both is associated with measurable indicators of physical health.

The system will integrate three primary data sources:

- **Plaid API** for user-authorized financial information
- **Garmin Health and Activity APIs** for health, fitness, and activity data
- **A geographic/context API** for converting location information into environmental features such as proximity to parks, gyms, grocery stores, walkable destinations, and other relevant points of interest

The system will use these sources as external knowledge stores and process them through an AI agent capable of retrieving the necessary information, generating structured features, executing predictive models, and explaining the resulting relationships.

The central research question is:

> **How predictive are financial behavior and geographic context of an individual's physical activity and health indicators?**

Three experimental conditions will be evaluated:

1. Financial information only
2. Geographic/environmental information only
3. Financial and geographic information combined

The objective is not to establish that finances or location *cause* better or worse health. Instead, the project will measure whether these variables contain useful predictive information about observable health and activity outcomes.

## 3. Motivation

Physical health is influenced by many interacting factors. Financial circumstances can affect access to food, transportation, recreation, gyms, and other resources. Similarly, where a person spends time may affect access to parks, walkable areas, recreational facilities, and other environments that encourage or discourage physical activity.

These information sources are normally analyzed independently.

Financial applications understand transactions but generally do not understand physical activity. Health applications understand heart rate, sleep, steps, and exercise but generally do not understand a user's financial behavior.

This project investigates whether combining these independent knowledge sources provides a more informative representation of a user's circumstances.

The project also fits the AI Knowledge Systems framework because the system must acquire external information, transform it into useful representations, store and retrieve those representations, reason over them, and evaluate the resulting behavior. The course describes this lifecycle as acquisition, representation, storage/indexing, access, reasoning/action, and evaluation/update. fileciteturn0file0L199-L215

## 4. Research Questions

The primary research question is:

> **Does combining financial and geographic context improve prediction of physical health and activity compared with using either source independently?**

The project will additionally investigate:

**RQ1 — Financial Context**

How accurately can financial behavior alone predict selected health and activity indicators?

**RQ2 — Environmental Context**

How accurately can geographic and environmental characteristics alone predict selected health and activity indicators?

**RQ3 — Combined Knowledge**

Does combining financial and geographic features produce significantly better predictions than either individual source?

**RQ4 — Agent Reliability**

Can an AI agent reliably select the appropriate data sources and analysis tools required to answer health-context questions?

**RQ5 — Explainability**

Can the system generate explanations grounded in the retrieved financial, geographic, and health information without introducing unsupported conclusions?

## 5. External Knowledge Sources

### 5.1 Plaid API

Plaid will provide user-authorized financial information.

The Transactions API can provide up to 24 months of transaction history and includes information such as transaction date, amount, merchant, category, and merchant location. Plaid recommends `/transactions/sync` for retrieving and incrementally updating transaction information. citeturn823544search0turn823544search3

Rather than exposing raw transaction data directly to the language model, the system will transform transactions into structured financial features.

Potential features include:

- Estimated monthly income
- Monthly expenses
- Disposable cash flow
- Grocery spending
- Restaurant spending
- Fitness-related spending
- Healthcare-related spending
- Transportation spending
- Recurring obligations
- Spending volatility
- Savings-to-spending ratio
- Discretionary-spending ratio

For development and evaluation, Plaid provides a fully featured Sandbox environment with test financial institutions and synthetic users. Custom transactions can also be generated programmatically. citeturn823544search1turn823544search2

This allows the financial pipeline to be developed without requiring participants to expose actual financial accounts during the initial implementation.

### 5.2 Garmin Health API

Garmin will provide the measurable health and wellness outcomes.

The Garmin Health API provides all-day metrics including:

- Steps
- Intensity minutes
- Heart rate
- Sleep
- Calories
- Stress
- Pulse Ox
- Body Battery
- Respiration
- Body composition
- Blood pressure

Garmin provides these metrics after the user gives consent and synchronizes a supported device with Garmin Connect. citeturn650935search12

Rather than creating a subjective definition of "healthy," the project will use directly measurable outcomes.

Potential dependent variables include:

- Average daily steps
- Weekly intensity minutes
- Resting heart rate
- Sleep duration
- Sleep consistency
- Stress measurements
- Exercise frequency
- Activity calories

A secondary implementation could construct a normalized **Physical Activity and Wellness Score**, although individual health indicators will remain available so that results are interpretable.

### 5.3 Garmin Activity API

The Garmin Activity API can provide detailed recorded fitness activities, including running, cycling, swimming, strength training, and other activity types. It can also provide complete FIT, GPX, or TCX activity files. citeturn650935search0

Garmin FIT activity files can contain GPS tracks in addition to timestamps, sensor data, and activity information. citeturn650935search7turn650935search13

This allows geographic context to be associated with recorded activity locations.

The system will not assume that Garmin provides continuous user tracking. Geographic analysis will therefore be limited to consented location information available through recorded activities or another explicit location source.

### 5.4 Geographic Context API

Raw latitude and longitude values are not sufficiently meaningful by themselves.

A geographic service will convert location information into environmental characteristics.

Possible features include:

- Number of parks within a defined radius
- Number of gyms or recreation facilities
- Distance to the nearest park
- Grocery-store accessibility
- Restaurant density
- Trail availability
- Urban/suburban characteristics
- Walkable destination density

An implementation could use a mapping or places service such as Google Places, OpenStreetMap/Overpass, or another suitable location API.

The result would transform:

`28.5383, -81.3792`

into higher-level structured knowledge such as:

`parks_within_2km = 4`

`gyms_within_2km = 6`

`grocery_stores_within_2km = 3`

This representation is more appropriate for predictive modeling than raw coordinates.

## 6. Proposed System Architecture

The system will be implemented using an AWS-centered architecture.

```text
                   ┌────────────────────┐
                   │       User         │
                   └─────────┬──────────┘
                             │
                             ▼
                   ┌────────────────────┐
                   │   Web Application  │
                   └─────────┬──────────┘
                             │
                             ▼
                      Amazon API Gateway
                             │
                             ▼
                      Agent Orchestrator
                       AWS Lambda / ECS
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
      Plaid Tool         Garmin Tool       Location Tool
          │                  │                  │
          ▼                  ▼                  ▼
    Financial Data      Health Data       Geographic Data
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                    Feature Engineering
                             │
                             ▼
                     Structured Store
                      Aurora PostgreSQL
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
             Prediction Model     Vector Store
                SageMaker          pgvector
                    │                 │
                    └────────┬────────┘
                             ▼
                       AI Agent / LLM
                             │
                             ▼
                   Grounded Explanation
```

## 7. AWS Components

### Amazon API Gateway

Provides the external REST interface used by the application.

### AWS Lambda

Handles short-duration serverless tasks such as:

- Plaid synchronization
- Garmin synchronization
- Geographic enrichment
- Feature calculation
- Agent tool execution

Longer-running processes could instead execute through ECS/Fargate.

### Amazon EventBridge

Schedules periodic synchronization jobs and analytical workflows.

For example:

```text
Every night
    ↓
EventBridge
    ↓
Fetch Plaid updates
Fetch Garmin updates
Enrich location
Generate daily features
Store observation
```

### Amazon SQS

Decouples API ingestion and processing.

This prevents failures or throttling from one external service from blocking the entire pipeline.

### Amazon Aurora PostgreSQL

Stores normalized financial, health, geographic, and experiment data.

Example conceptual schema:

```text
users

financial_daily_features
- user_id
- date
- income
- spending
- grocery_spending
- restaurant_spending
- transportation_spending
- discretionary_spending

health_daily_features
- user_id
- date
- steps
- resting_hr
- sleep_minutes
- stress
- intensity_minutes

environment_features
- user_id
- date
- park_count
- gym_count
- grocery_count
- activity_location_type

predictions
- model_version
- user_id
- prediction
- actual_value
- confidence
```

### pgvector

A pgvector extension can support semantic retrieval of generated summaries, historical observations, and agent memory.

The vector database would **not replace SQL** for numerical data.

Structured financial and health metrics belong in relational columns and should be queried with SQL.

Embeddings would instead be useful for information such as:

- Previous agent analyses
- User-generated notes
- Historical explanations
- Similar observations
- Experiment documentation

### Amazon SageMaker

Hosts and versions predictive models.

Candidate models could include:

- Linear regression
- Logistic regression
- Random Forest
- XGBoost
- Small neural networks

The first implementation should intentionally use relatively interpretable baselines before more complex models are introduced.

### Amazon Bedrock

An LLM hosted through Bedrock could serve as the agent reasoning layer.

The LLM would not directly make health predictions.

Instead, it would orchestrate deterministic tools such as:

```text
get_financial_features()
get_health_history()
get_environment_features()
run_health_prediction()
compare_models()
retrieve_similar_periods()
explain_prediction()
```

This separation reduces hallucination risk and makes individual system components measurable.

## 8. AI Agent Design

The agent follows the reason-act pattern discussed in the course.

The course describes AI agents as systems combining language models with tools, context, memory, planning, and execution feedback. fileciteturn0file0L379-L400

A sample interaction might be:

> "Why was my physical activity lower this month?"

The agent could execute:

```text
1. get_health_history(last_60_days)

2. compare_activity_periods(
      current_month,
      previous_month
   )

3. get_financial_features(current_month)

4. get_environment_features(current_month)

5. run_association_analysis()

6. retrieve_relevant_historical_patterns()

7. generate_grounded_explanation()
```

The final response could state:

> Daily steps decreased 18% compared with the previous month. During the same period, recorded outdoor activities decreased from 11 to 4, while transportation spending increased by 27%. The model considers environmental and financial features associated with the lower activity period, but these relationships should not be interpreted as causal.

Every factual statement generated by the agent would be traceable to a retrieved record or computed result.

## 9. RAG and GraphRAG Component

RAG is useful here, but it should not be forced onto data that is naturally relational.

SQL should handle numerical questions such as:

> "How many steps did the user average this month?"

RAG can instead retrieve textual or historical context.

Example:

```text
Question
   ↓
Structured intent detection
   ↓
SQL retrieval ──────► Numerical evidence
   │
   └── RAG retrieval ► Historical/context evidence
                           │
                           ▼
                          LLM
                           │
                           ▼
                     Final explanation
```

A GraphRAG extension could model relationships among:

```text
User
 │
 ├── VISITED_AREA ──► Location
 │                        │
 │                        ├── HAS_PARK
 │                        ├── HAS_GYM
 │                        └── HAS_GROCERY_STORE
 │
 ├── MADE_TRANSACTION ──► Merchant
 │                            │
 │                            └── HAS_CATEGORY
 │
 └── PERFORMED_ACTIVITY ──► Activity
                              │
                              ├── OCCURRED_AT ──► Location
                              └── HAS_HEALTH_METRICS
```

GraphRAG would allow multi-hop questions such as:

> "During periods when the user exercised frequently, what types of locations and spending patterns were associated with those activities?"

This component should be treated as an extension rather than a requirement for the minimum viable implementation.

## 10. Machine Learning Experiment

The core experiment will compare three predictive models.

### Model A — Financial Model

Inputs:

```text
income
cash flow
grocery spending
restaurant spending
fitness spending
transportation spending
discretionary spending
spending volatility
```

Output:

```text
Health/activity metric
```

### Model B — Environmental Model

Inputs:

```text
park accessibility
gym accessibility
activity-location characteristics
grocery accessibility
walkable destination density
```

Output:

```text
Health/activity metric
```

### Model C — Combined Model

Inputs:

```text
Financial features
+
Environmental features
```

Output:

```text
Health/activity metric
```

The primary experimental comparison becomes:

```text
Finance
   vs.
Environment
   vs.
Finance + Environment
```

## 11. Evaluation Metrics

Because the project is a complete AI system rather than only a machine-learning model, evaluation will occur at several levels.

### Prediction Quality

For continuous variables such as daily steps:

- Mean Absolute Error
- Root Mean Squared Error
- R²

For categorical outcomes such as meeting an activity target:

- Accuracy
- Precision
- Recall
- F1 score
- ROC-AUC

### Tool-Calling Accuracy

A test set of agent questions will record whether the agent:

- Selected the correct API/tool
- Supplied valid arguments
- Retrieved the required evidence
- Avoided unnecessary calls

### Grounding Accuracy

Generated statements will be checked against retrieved evidence.

Potential metric:

**Supported Claim Rate**

`number of supported factual claims / total factual claims`

### Reliability

The system will record:

- Plaid API failures
- Garmin API failures
- Geographic API failures
- Retries
- Timeout frequency
- Incomplete records
- Model failures
- Agent recovery success

### Latency

Latency will be measured separately for:

- API retrieval
- Feature generation
- Prediction
- Retrieval
- LLM inference
- Total request latency

### Cost

The project will measure:

- LLM token cost
- AWS compute cost
- Database cost
- API calls per request
- Average cost per completed analysis

These measurements directly support the course requirement to evaluate end-to-end behavior, cost, reliability, and representative failures. fileciteturn0file0L460-L468

## 12. Ablation Study

A useful ablation experiment will remove individual knowledge sources.

```text
Experiment 1
Finance only

Experiment 2
Environment only

Experiment 3
Finance + Environment

Experiment 4
Finance + Environment
without historical retrieval

Experiment 5
Complete system
```

This allows the project to determine whether each additional source actually contributes useful information.

A second agent-oriented ablation could compare:

```text
LLM with raw context

vs.

LLM + structured tools

vs.

LLM + tools + retrieval/memory
```

The comparison would determine whether the agent architecture improves correctness and reliability compared with simply supplying raw data to a language model.

## 13. Privacy and Security

This project involves highly sensitive financial, health, and location information.

The implementation will therefore follow a data-minimization design.

The system will store derived features whenever possible rather than unnecessary raw records.

For example, the predictive model may need:

```text
restaurant_spending = $280
```

but it may not need:

```text
Restaurant X
March 11
$47.62
Exact address
```

Security controls will include:

- OAuth 2.0 authorization where required
- AWS Secrets Manager for API credentials
- TLS for all external and internal communication
- Encryption at rest using AWS KMS
- Least-privilege IAM policies
- User-specific data isolation
- Explicit data deletion capability
- Removal or coarse-graining of unnecessary GPS data
- Logging without financial or health payloads

Plaid credentials and user access tokens will never be provided to the LLM.

Garmin uses OAuth 2.0 for APIs in the Garmin Connect Developer Program. citeturn650935search2

## 14. Dataset Strategy

The most significant challenge is obtaining enough paired financial and health observations.

There are two possible evaluation strategies.

### Phase 1 — Controlled Synthetic Evaluation

Plaid Sandbox will generate controlled financial personas and transactions.

Synthetic environmental and health profiles can be generated with known relationships.

This enables:

- Architecture validation
- Unit testing
- Controlled experiments
- Tool-calling evaluation
- Failure injection
- Ground-truth prediction experiments

Plaid explicitly supports custom Sandbox transactions, making this approach technically practical. citeturn823544search1

### Phase 2 — Consented Longitudinal Evaluation

If appropriate access and participants are available, consenting users can connect actual Plaid and Garmin accounts.

Observations would then be analyzed longitudinally.

Without a sufficiently large participant population, conclusions would remain individual-level rather than population-level.

The project will therefore avoid claims such as:

> "Wealthier people are healthier."

The appropriate interpretation is:

> "The combined feature set showed greater predictive value for the measured health outcomes in the evaluated dataset."

## 15. Known Limitations

The project has several expected limitations.

First, observed associations do not establish causality.

Second, Garmin users are not necessarily representative of the general population.

Third, health outcomes can be affected by variables not available through these APIs, including age, medical history, occupation, weather, and lifestyle.

Fourth, financial transactions are only an indirect representation of financial circumstances.

Fifth, Garmin location data is primarily associated with recorded activities rather than providing continuous user-location tracking.

Finally, Garmin Connect Developer Program access requires approval. Garmin states that the program is intended for business use, although approved developers receive an evaluation environment. citeturn650935search2turn650935search4

For that reason, the architecture should support a simulated Garmin adapter so project development can continue even if API approval is delayed.

## 16. Minimum Viable Project

The MVP will intentionally remain narrow.

The system will:

1. Retrieve financial information from Plaid Sandbox.
2. Retrieve or simulate Garmin health/activity observations.
3. Retrieve environmental context for an activity location.
4. Convert all three sources into daily or weekly features.
5. Store the features in PostgreSQL.
6. Train finance-only, environment-only, and combined models.
7. Expose those models as tools to an AI agent.
8. Allow a user to ask a health-context question.
9. Have the agent retrieve the required evidence and execute the appropriate model.
10. Produce a grounded explanation.
11. Record latency, cost, tool calls, prediction quality, and failures.

The MVP deliberately avoids trying to create a general-purpose medical or financial assistant.

It answers one specific class of questions:

> **How do financial and environmental signals relate to the user's measured physical activity and wellness indicators?**

## 17. Expected Contribution

The project's contribution is an end-to-end AI knowledge system demonstrating how heterogeneous external knowledge can be integrated into an agent.

The system combines:

**Structured financial knowledge**
→ Plaid

**Health knowledge**
→ Garmin

**Spatial/environmental knowledge**
→ geographic API

**Relational storage**
→ PostgreSQL

**Semantic memory**
→ pgvector

**Prediction**
→ SageMaker

**Reasoning and tool orchestration**
→ LLM agent

The primary hypothesis is:

> **A model using both financial and environmental context will predict selected physical activity and wellness indicators more accurately than models using either source independently.**

A secondary system hypothesis is:

> **An agent using structured tools and retrieved evidence will produce more reliable and better-grounded explanations than an LLM provided with unstructured raw context alone.**

## 18. Final Project Scope

This proposal is intentionally structured around the System Implementation Track requirements.

The final deliverable will demonstrate one complete path:

```text
External APIs
     ↓
Knowledge acquisition
     ↓
Feature representation
     ↓
Storage
     ↓
Retrieval
     ↓
Prediction
     ↓
Agent reasoning
     ↓
Grounded explanation
     ↓
Evaluation
```

The final paper will report component-level measurements, end-to-end performance, system cost, reliability, ablation results, representative failure cases, limitations, and lessons learned.

The resulting project is therefore not simply a dashboard that combines Plaid and Garmin data. It is an evaluated AI knowledge system in which multiple external knowledge sources affect prediction, reasoning, and agent behavior.