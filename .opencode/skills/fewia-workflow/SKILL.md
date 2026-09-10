---
name: fewia-workflow
description: Run FEWIA grocery-bot work with bounded roles, CLI supervisor writes, independent Codex or Grok review, and required backend gates.
---

# FEWIA workflow

Read root `AGENTS.md`, `.codex/TEAM.md`, and `.codex/project-context.md`.
Canonical role scope lives in `.codex/agents/<role>.toml` under
`developer_instructions`.

The grocery MVP checkpoint is current.
You MUST NOT resume health-model training.

## Bounded work

Own only assigned files. Preserve other edits.
Child workers MUST NOT switch branches in a shared checkout.
Serialize writes to shared files.
Native OpenCode has no implicit worktree isolation.

`tech-lead` MAY delegate bounded exploration with native OpenCode `task`.
Specialists MUST NOT spawn further agents.
Native OpenCode `task` is not supervisor fallback.

## Writes

Route all repository writes through the CLI
supervisor. Example:

```bash
uv run --project backend python -m dev_supervisor \
  --task /private/tmp/assignment.txt --role backend-dev --cwd "$PWD" \
  --write-file relative/path
```

The assignment MUST name owned files. Repeat `--write-file` for each
owned path. Details live in `docs/DEV_SUPERVISOR.md`.

## Review and gates

A separate Codex or Grok agent independently verifies the result.
The writer MUST NOT certify its own independent review.

Before reporting done, run and report the root verification gates:

```bash
cd backend
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy --strict app
uv run pytest
```

Report actual command output, including failures.
