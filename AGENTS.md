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
Claude Code is not an active workflow dependency. These rules bind all writers.

## Startup context

`.codex/project-context.md` is the canonical compact startup context.
It holds product constraints and evidence boundaries.
These engineering and workflow hard rules live here, not in that file.
Writer workflow lives in `docs/DEV_SUPERVISOR.md`. Do not copy that
policy into the compact context.

The coordinator reads `.codex/TEAM.md` and `docs/DEV_SUPERVISOR.md` when
dispatching. Workers receive the selected role, a bounded assignment,
these hard rules, and relevant integration context only.

Do not preload the full conversation or graph.
Do not load `project-plan.md`, `wiki/index.md`, or
`docs/CAP6938_MVP_PROJECT_PLAN.md` unless the question needs them.
Retain those source files.

Do not insert a coordinator hop for routine work.
Native bounded agents start from a fresh task context.
They MUST use `fork_turns` none and MUST NOT spawn recursive workers.
Repair MUST reuse the owning worker and the explicit task context.
Do not use `resume --last`.

A brief MUST stay at or under 500 words, excluding necessary contracts.
A worker return MUST stay at or under 200 words plus file and log
references unless failures need more. Default user responses MUST stay
brief: facts, check result, and blocker. Expand when the user requests
depth or when a material failure needs evidence.

Search before bounded reads. Do not dump raw huge logs or whole graphs.
Store logs locally. Return a summary and the relevant errors.
Batch independent reads. Avoid unchanged polling. Use bounded waits.
A milestone handoff MUST name revision, scope, decisions, checks, and
the next action. Start a fresh task only after an explicit user request.

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
  Record actual checks only. Reviewer evidence MAY be finalized later.
  The log is append-only.

## Verification

Writers MUST run focused tests while developing.
An independent reviewer MUST run the full required backend gates and the
relevant scope gates. The coordinator verifies that evidence. The
coordinator MUST NOT rerun the same gates unless a change or failure
justifies it. A writer MUST NOT certify independent review.

Required reviewer backend gates:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Report the actual command output, including failures.
