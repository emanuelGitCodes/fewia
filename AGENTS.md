# FEWIA rules for Codex

Codex writes code for FEWIA. Claude verifies it. This file binds Codex;
`CLAUDE.md` states the same contract for Claude agents.

## Read first

- `project-plan.md` — the phases and the current status banner.
- `wiki/index.md` — decisions and phase records.
- `docs/CAP6938_MVP_PROJECT_PLAN.md` — the specification.

## Rules

- All Python MUST carry type annotations. `uv run mypy --strict app`
  MUST pass.
- `uv run ruff check` and `uv run ruff format --check` MUST pass.
- A pull request MUST NOT add more than 150 lines of code. Tests, docs,
  lockfiles, and generated files do not count. A larger change ships as
  a stack with the merge order in each PR body.
- Work on a branch. Codex MUST NOT merge, and MUST NOT push to `main`.
- LLM calls go through the `LLMProvider` protocol in
  `backend/app/agent/`. Do not import boto3 outside the provider and
  infra modules.
- Secrets MUST stay out of source, prompts, logs, and model inputs.
- Prose in comments, docstrings, Markdown, and commit messages uses
  short, plain, active sentences. Requirement words are MUST, MUST NOT,
  SHOULD, SHOULD NOT, and MAY, in uppercase, with no synonyms.
- A comment MUST NOT carry history, justification, status, or dates.
  Those go in `wiki/`.
- After a work item is done, append one dated entry to `wiki/log.md`.
  The log is append-only.

## Verification

Before reporting done, run and pass:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Report the actual command output, including failures.
