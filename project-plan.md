# FEWIA Build Plan: MVP + Agent Delegation

> **Status**: Phase 0, Phase 1, and Phase 2 are complete
> ([wiki/phases/phase-0.md](wiki/phases/phase-0.md),
> [wiki/phases/phase-1.md](wiki/phases/phase-1.md),
> [wiki/phases/phase-2.md](wiki/phases/phase-2.md)).
> Execution starts at Phase 3. `wiki/` records work and decisions; an
> executor MUST read `CLAUDE.md` and `wiki/index.md` before starting.
> The delegation sections assume Claude Code (Agent tool, skills,
> worktrees); another executor follows the phases, deliverables, and
> verification steps directly.

## Context

At the start of this plan, the `fewia` repo held only `docs/`. The proposal ([writing-block.md](docs/writing-block.md)) and the MVP plan ([CAP6938_MVP_PROJECT_PLAN.md](docs/CAP6938_MVP_PROJECT_PLAN.md)) define the Financial and Environmental Wellness Intelligence Agent for CAP 6938. The goal is a working MVP that runs one narrow path end to end: synthetic data → PostgreSQL → typed FastAPI tools → three prediction models → a Bedrock tool-use agent → a grounded, evidence-cited answer.

Decisions made with the user:

- **Real Bedrock from day one.** Floci is used only for AWS-shaped integration tests (SQS, EventBridge, S3, Secrets Manager), never as the LLM.
- **Frontend after the MVP checkpoint.** Phases 1–6 are backend-only.
- **git init + GitHub repo.** Every work item ships as a small PR (≤150 added code lines, per the `stacked-prs` skill). Larger changes ship as stacks.

Secondary goal: the user learns multi-agent delegation. The plan creates a project agent team in `.claude/agents/` and routes every phase's work through it.

## Tech constraints

- Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, scikit-learn, boto3.
- All Python MUST use type annotations; `mypy --strict` and `ruff` in CI.
- Docker Compose runs `api` + `postgres` (+ `floci` profile for integration tests).
- Bedrock Converse API with client-side tool use, behind an `LLMProvider` protocol.
- Prose follows house-style (ASD-STE100 + RFC 2119); PR size follows stacked-prs.

## Repository layout (target)

```text
fewia/
├── .claude/agents/          # the agent team (Phase 0)
├── CLAUDE.md                # project rules for all agents
├── compose.yaml
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── db/              # models, session, Alembic migrations
│   │   ├── tools/           # deterministic agent tools
│   │   ├── agent/           # Bedrock loop, LLMProvider protocol
│   │   ├── ml/              # training, model registry
│   │   └── synth/           # synthetic data generator
│   └── tests/
├── infra/                   # Floci config, later CDK/Terraform
├── frontend/                # Phase 7 (React + TS + Vite)
├── eval/                    # question set, expected tool calls, results
└── docs/
```

## Phase 0 — Repo bootstrap and the agent team ✅ COMPLETE

Completed 2026-08-31. All five deliverables shipped: private GitHub
repo `emanuelGitCodes/fewia`, `CLAUDE.md`, the six agents in
`.claude/agents/`, `docs/DELEGATION.md`, and the seeded knowledge
graph. Record: [wiki/phases/phase-0.md](wiki/phases/phase-0.md).

Deliverables (mostly config/docs; PR cap does not bind):

1. `git init`, create the GitHub repo with `gh repo create`, first commit of `docs/`. **Ask before pushing** (health/finance project — confirm public vs private; recommend private).
2. `CLAUDE.md` (project): tech constraints above, build/test commands, definition of done ("typed, tested, mypy/ruff clean, PR ≤150 code lines, house-style prose").
3. **Agent team** in `.claude/agents/` (markdown with frontmatter: description, tools, model):
   - `tech-lead` — the delegator. No Edit/Write of app code; decomposes a phase into ≤150-line work items, spawns the specialist agents below via the Agent tool (worktree isolation for parallel work), reviews their reports, and states PR merge order. This is the "agent that spreads tasks between other agents."
   - `backend-dev` — FastAPI/SQLAlchemy/tools/agent-loop code. Typed Python only.
   - `ml-dev` — synthetic data, feature building, model training, metrics tables.
   - `aws-infra` — Docker Compose, Floci, IAM/Bedrock setup, later ECS/RDS deploy. May use the AWS MCP tools for read/verify; mutations require user confirmation.
   - `test-engineer` — pytest suites, eval harness, CI workflow. Owns test quality; other agents still write basic tests for their own code.
   - `frontend-dev` — React + TypeScript (idle until Phase 7).
4. A short `docs/DELEGATION.md`: how the user hands work to agents (`Agent tool with subagent_type`, `SendMessage` to continue one, worktrees, background runs) — this is the learning deliverable.
5. Run `/graphify` on `docs/` to seed the knowledge graph; re-run at each phase checkpoint.

## Phase 1 — Skeleton: Compose, schema, CI ✅ COMPLETE  *(owner: aws-infra + backend-dev)*

Completed 2026-08-31. Four stacked branches shipped through pull
requests #1 to #5 and sit on `main` at `82cbd70`: Compose plus
`/healthz`, the six SQLAlchemy models, the first Alembic migration, and
the GitHub Actions workflow. CI passes on `main`. Record:
[wiki/phases/phase-1.md](wiki/phases/phase-1.md).

- PR 1: `compose.yaml` (FastAPI + Postgres 16), `backend/pyproject.toml`, health endpoint `GET /healthz`, Dockerfile.
- PR 2 (stacked): SQLAlchemy models + Alembic migration for the six tables in the MVP doc §4 (`users`, `daily_finance`, `daily_environment`, `daily_health`, `model_runs`, `predictions`).
- PR 3 (stacked): GitHub Actions CI — ruff, mypy --strict, pytest against a Postgres service container.

Verify: `docker compose up` → `/healthz` returns 200; `alembic upgrade head` succeeds; CI green.

## Phase 2 — Synthetic data ✅ COMPLETE  *(owner: ml-dev)*

Completed 2026-09-01. Three stacked branches shipped through pull
requests #10, #11, and #12 and sit on `main` at `4e47640`: the typed
records, the seeded generator, and the loader with its CLI. Two runs
with seed 42 write identical rows. CI passes on `main`. Record:
[wiki/phases/phase-2.md](wiki/phases/phase-2.md).

- Seeded generator (`app/synth/`): 4 profiles × 90 days, weekday effects, noise, missing records, outliers (MVP doc §5). Dataset version string stored in `source` columns.
- CLI entry point: `python -m app.synth --seed 42 --days 90`.

Verify: two runs with the same seed produce identical rows; row counts and missingness match spec; a pytest asserts reproducibility.

## Phase 3 — Deterministic tools + FastAPI endpoints  *(owner: backend-dev; tests: test-engineer)*

- Implement the five tools from MVP doc §6 as typed functions returning Pydantic models with `evidence_id`, `record_count`, `source`, warnings: `get_health_context`, `get_financial_context`, `get_environment_context`, `run_activity_prediction` (stub until Phase 4), `compare_periods`.
- Expose each as a REST endpoint (`GET /context/health`, etc.) so the path is provable without any LLM.
- One PR per tool (natural ≤150-line units); test-engineer follows with a test PR per tool covering date-range edges, missing data, and empty results.

Verify: curl each endpoint against synthetic User 1 August data; responses carry evidence IDs; tests green.

## Phase 4 — Models and metrics  *(owner: ml-dev)*

- Linear regression + random forest × three feature sets (finance / environment / combined) → daily steps. Time-aware split; naive mean baseline.
- Persist each run to `model_runs` (MAE, RMSE, R², seed, data version); save artifacts to `backend/artifacts/` (S3 later).
- Wire the real model into `run_activity_prediction`, returning `model_version`.
- Output: a metrics table in `eval/results/` comparing the three conditions — this is the course's core experiment.

Verify: training CLI runs from Compose; `model_runs` has 6 rows (2 algos × 3 feature sets); combined-model prediction returns through the API with a model version.

## Phase 5 — Bedrock agent loop  *(owner: backend-dev; infra: aws-infra)*

- `LLMProvider` protocol; `BedrockConverseProvider` using boto3 `converse` with client-side tool use. aws-infra verifies model access (recommend Claude on Bedrock, cross-region inference profile) and sets least-privilege credentials; secrets via env, never in code or prompts.
- Tool schemas generated from the Pydantic models of Phase 3. Loop: send question + schemas → execute requested tool → return result → repeat → final grounded answer with evidence IDs and a non-causal statement (MVP doc §8).
- `POST /agent/analyze` endpoint (MVP doc §17). Log every tool call, latency, and token usage to a `request_traces` table (new migration).

Verify: the §17 demo request runs end to end against real Bedrock and cites evidence IDs; a stub `LLMProvider` fake keeps tests free and deterministic.

## Phase 6 — Evaluation harness → MVP CHECKPOINT  *(owner: test-engineer)*

- `eval/questions.yaml`: ≥10 questions with expected tool calls, arguments, and evidence IDs (write these before trusting the agent).
- Runner scores: tool-selection accuracy, argument accuracy, unnecessary calls, supported-claim rate, latency, cost per answer; failure log with ≥1 example per failure class.
- Emit the tables the final paper needs (MVP doc §19).

**MVP complete** when the checkpoint block in MVP doc §18 holds. Do not start Phase 7+ before this.

## Phase 7 — Frontend  *(owner: frontend-dev)*

- Vite + React + TypeScript in `frontend/`: a question box calling `/agent/analyze`, an evidence/tool-trace panel, and a model-comparison table read from `model_runs`. No auth for the demo.
- Added to Compose behind a profile.

## Phase 8 — Floci integration tests + AWS deploy  *(owner: aws-infra)*

- Floci (`floci/floci` image, port 4566) in a Compose profile; contract tests for the event path (EventBridge nightly sync → SQS → worker) and S3 artifact storage, per MVP doc §16. Floci never substitutes for Bedrock evidence.
- Then the small real deployment (MVP doc §15): ECS Fargate + RDS Postgres + Bedrock, secrets in Secrets Manager, logs in CloudWatch. aws-infra uses the AWS MCP to verify state; every mutating step is confirmed with the user first.

## Phase 9 — External providers (post-MVP, time permitting)

Adapter swaps behind existing interfaces, in order: Plaid Sandbox (`/transactions/sync`), one environment provider (Google Places or Overpass), Garmin when program access is approved. pgvector and GraphRAG only if a measured need appears (MVP doc §12–13).

## Delegation workflow (the learning goal)

Per phase: the user (or tech-lead) states the phase goal → **tech-lead** decomposes it into ≤150-line work items with explicit interfaces → specialists run in parallel worktrees → each delivers a branch + PR with parent named in the body → test-engineer or `/code-review` reviews → user merges in stated order → `/graphify` refreshes the graph. Independent phases can overlap (e.g., Phase 2 ml-dev and Phase 3 backend-dev run concurrently after Phase 1).

## Verification summary

- Every phase ends with a runnable check listed above (compose up, curl, pytest, eval runner).
- CI (ruff + mypy --strict + pytest) gates every PR.
- The final acceptance test is the §17 demo request returning a grounded answer with evidence IDs, plus the §18 checkpoint block.
