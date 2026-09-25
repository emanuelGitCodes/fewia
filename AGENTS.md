# FEWIA rules for Codex

Development writers use the CLI supervisor in `docs/DEV_SUPERVISOR.md`.
The default order is Grok 4.6, Codex Spark, then Luna.
The coordinator classifies each task before delegation.
Valid complexity values are `simple`, `standard`, `complex`, `exceptional`,
and `maximum`.
Grok 4.6 uses `low` for simple tasks.
Grok 4.6 uses `medium` for every harder automatic tier.
Grok 4.6 MUST NOT receive `high`, `xhigh`, or `max`.
Spark uses its CLI default.
Spark does not accept an effort override in this supervisor.
Luna and Sol support automatic selection through `max`.
The supervisor requires `--complexity`.
An explicit `--effort` override MUST stay within the model ceiling.
Explicit task model or effort requests override automatic selection when
supported. Model-only requests forbid substitution.
A separate Codex or Grok agent verifies independently.
Claude Code MAY hold the coordinator seat (decision 0013). It never writes code
and is never the independent reviewer. These rules bind all writers.

## Read first

The coordinator reads these sources before decomposition. Workers receive
bounded briefs with hard rules and targeted integration context. Follow
`docs/DEV_SUPERVISOR.md`; do not preload the full conversation or graph.

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
