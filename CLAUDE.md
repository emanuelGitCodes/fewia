# FEWIA project rules

FEWIA is the Financial and Environmental Wellness Intelligence Agent for
CAP 6938. The plan lives in `docs/CAP6938_MVP_PROJECT_PLAN.md`. The
delegation guide lives in `docs/DELEGATION.md`.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, scikit-learn,
  boto3. The backend lives in `backend/`.
- The LLM is Amazon Bedrock through the Converse API. Code MUST call it
  through the `LLMProvider` protocol in `backend/app/agent/`.
- Docker Compose runs `api` and `postgres`. The `floci` profile runs the
  AWS emulator for integration tests only.
- The frontend (Phase 7) uses React, TypeScript, and Vite in `frontend/`.

## Rules

- All Python MUST carry type annotations. `mypy --strict` MUST pass.
- `ruff check` and `ruff format --check` MUST pass.
- A pull request MUST NOT add more than 150 lines of code. Tests, docs,
  lockfiles, and generated files do not count. Larger changes ship as a
  stack. Read the `stacked-prs` skill.
- Prose follows the `house-style` skill: ASD-STE100 sentences, RFC 2119
  keywords.
- Secrets MUST stay out of source, prompts, logs, and model inputs. Use
  environment variables locally and Secrets Manager in AWS.
- The agent MUST cite evidence IDs and MUST NOT state causal claims.
- Floci results are integration evidence only. They MUST NOT stand in
  for real Bedrock or real AWS evidence.

## Wiki

`wiki/` records the work done and the decisions made. The conventions
live in `wiki/schema.md`. After a work item merges or a decision lands,
the agent that did the work MUST append a `wiki/log.md` entry and
update the pages it touched. History, dates, status, and justification
go in the wiki, not in code comments.

## Commands

```bash
docker compose up -d                 # api + postgres
cd backend && uv run pytest          # tests
cd backend && uv run mypy --strict app
cd backend && uv run ruff check app tests
cd backend && uv run alembic upgrade head
```

## Definition of done

A work item is done when the code is typed, tested, mypy and ruff clean,
inside the PR size cap, and verified by the phase check in the plan.
