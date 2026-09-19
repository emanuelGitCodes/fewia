---
name: fewia-workflow
description: Run FEWIA grocery-bot work with bounded roles, CLI supervisor writes, independent Codex or Grok review, and required backend gates.
---

# FEWIA workflow

`.codex/project-context.md` is the canonical compact startup context.
It includes AGENTS.md hard rules and product constraints.
The coordinator reads `.codex/TEAM.md` and `docs/DEV_SUPERVISOR.md` when
dispatching. Workers receive the selected role, a bounded assignment,
those hard rules, and relevant integration context only.

Canonical role scope lives in `.codex/agents/<role>.toml` under
`developer_instructions`.

The grocery MVP checkpoint is current.
You MUST NOT resume health-model training.

## Bounded work

Own only assigned files. Preserve other edits.
Workers MUST NOT spawn agents or recursive workers.
Native bounded agents MUST use `fork_turns` none.
Repair MUST reuse the owning worker and the explicit task.
Do not use `resume --last`.
Child workers MUST NOT switch branches in a shared checkout.
Serialize writes to shared files.
Native OpenCode `task` is not supervisor fallback.

## Writes

Route all repository writes through the CLI
supervisor. Example:

```bash
uv run --project backend python -m dev_supervisor \
  --task /private/tmp/assignment.txt --role backend-dev --cwd "$PWD" \
  --complexity standard --write-file relative/path
```

The supervisor requires `--complexity`.
Use `standard` for ordinary coding work.
The coordinator MUST NOT select `maximum` for ordinary tasks.
The assignment MUST name owned files. Repeat `--write-file` for each
owned path. Details live in `docs/DEV_SUPERVISOR.md`.

## Review and gates

A separate Codex or Grok agent independently verifies the result.
Writers MUST run focused checks while developing.
The independent reviewer MUST run the required backend gates in
`AGENTS.md` plus relevant scope gates.
A writer MUST NOT certify its own independent review.
Report actual command output, including failures.
