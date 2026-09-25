---
name: fewia-workflow
description: Run FEWIA work with the tiered delegation loop, CLI supervisor writes, the shared gates and review commands, and bounded reports.
---

# FEWIA workflow

The rulebook is [docs/DELEGATION.md](../../../docs/DELEGATION.md). This skill
adds only the OpenCode mechanics. Canonical role scope lives in
`.codex/agents/<role>.toml` under `developer_instructions`.

You MUST NOT resume health-model training.

## Reading

- `tech-lead` reads root `AGENTS.md`, `.codex/project-context.md`,
  `.codex/TEAM.md`, and `docs/DELEGATION.md`.
- A specialist reads its role file, `docs/delegation/junior.md`, and its
  brief.

## Tiers in OpenCode

`tech-lead` picks tier S, M, or L for each work item.

- **Tier S.** `tech-lead` runs the writer, the gates, and the review command
  itself. It calls no specialist.
- **Tier M.** `tech-lead` calls one specialist, such as `@backend-dev`, with
  a brief from `docs/delegation/brief.md`. `tech-lead` runs the review
  command.
- **Tier L.** `tech-lead` also calls `@code-reviewer`, which follows
  `docs/delegation/reviewer.md`.

Specialists MUST NOT spawn further agents. Native OpenCode `task` is for
bounded exploration only. It is not supervisor fallback.

## Worktrees

Native OpenCode has no implicit worktree isolation. Give each specialist
its own worktree with `git worktree add`. Child workers MUST NOT switch
branches in a shared checkout.

## Commands

Run every command from the item worktree root.

```bash
uv run --project backend python -m dev_supervisor \
  --task "$BRIEF_FILE" --role backend-dev --cwd "$PWD" \
  --complexity standard --write-file relative/path \
  --work-item fewia-42 --phase implement
uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main
uv run --project backend python -m dev_supervisor.review --cwd "$PWD" \
  --base main --brief "$BRIEF_FILE" --complexity standard \
  --writer-model grok-4.6 --work-item fewia-42
uv run --project backend python -m dev_supervisor.usage --work-item fewia-42
```

Writers edit files only. The specialist or `tech-lead` runs every command.
Reports stay within 40 lines and name the SHA.
