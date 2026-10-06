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

## Delegation

Every coordinator follows [docs/DELEGATION.md](docs/DELEGATION.md), whatever
the tool. The coordinator picks tier S, M, or L for each work item.

- Writers edit files only. A Grok writer MUST NOT run shell commands. A
  Codex writer MAY run read-only shell commands to read and search files.
  No writer runs tests, package managers, git commands, or commands that
  write files.
- Juniors follow `docs/delegation/junior.md`. Briefs follow
  `docs/delegation/brief.md`.
- Run checks with `python -m dev_supervisor.gates`. Run independent review
  with `python -m dev_supervisor.review`.
- Reports stay within 40 lines and name the SHA instead of pasting diffs.

## Read first

The coordinator reads these sources before decomposition. Workers receive
bounded briefs with hard rules and targeted integration context. Follow
`docs/DEV_SUPERVISOR.md`; do not preload the full conversation or graph.

- `.codex/project-context.md` — the accepted product scope.
- `wiki/index.md` — decisions and phase records. Read the newest decisions.
- `project-plan.md` — the status banner.

Juniors and writers read only the files their brief names.

## Rules

- All Python MUST carry type annotations. `uv run mypy --strict app`
  MUST pass.
- `uv run ruff check` and `uv run ruff format --check` MUST pass.
- A pull request MUST NOT add more than 1000 lines of code. Tests, docs,
  lockfiles, and generated files do not count. A larger change ships as
  a stack with the merge order in each PR body.
- Work on a branch. Agents MUST NOT push to `main`. Writers and juniors
  MUST NOT merge. A coordinator merges only with explicit user
  authorization for that stack.
- LLM calls go through the `LLMProvider` protocol in
  `backend/app/agent/`. Do not import boto3 outside the provider and
  infra modules.
- Secrets MUST stay out of source, prompts, logs, and model inputs.
- Every commit MUST pass the gitleaks pre-commit hook. Agents MUST NOT
  skip it with `--no-verify` or `SKIP=gitleaks`. A finding that is a
  false positive goes in `.gitleaksignore` only after the coordinator
  reviews it.
- Prose in comments, docstrings, Markdown, and commit messages uses
  short, plain, active sentences. Requirement words are MUST, MUST NOT,
  SHOULD, SHOULD NOT, and MAY, in uppercase, with no synonyms.
- A comment MUST NOT carry history, justification, status, or dates.
  Those go in `wiki/`.
- After a work item is done, append one dated entry to `wiki/log.md`.
  The log is append-only.

## Verification

Before reporting done, run the gates for the changed paths:

```bash
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
```

For backend changes, that command runs these checks:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Report the actual command output, including failures.
