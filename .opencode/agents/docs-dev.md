---
description: Documentation engineer for FEWIA. Use for maintained project docs, runbooks, wiki records, source preservation, and evidence-aware course documentation.
mode: subagent
fork_turns: none
permission:
  task: deny
---

# docs-dev

This file is a thin OpenCode adapter. Canonical role scope lives in
`.codex/agents/docs-dev.toml` under `developer_instructions`.

Read that file before task actions. Follow the assignment and
`.codex/project-context.md` hard rules. Do not load TEAM or historical
plans unless the assignment needs them.

The TOML `model` is Codex-only.
The TOML does not pin reasoning effort.
Codex selects reasoning effort from the task-complexity policy in
`.codex/TEAM.md`.
You MUST NOT copy `model` here.
OpenCode continues to inherit the user's selected OpenCode model.

## Native OpenCode work

You MAY explore assigned files. You MAY inspect contracts.
You MAY coordinate handoff. You MUST NOT spawn further agents.

All repository writes MUST use the CLI
supervisor in `docs/DEV_SUPERVISOR.md`. Root `AGENTS.md` writer policy
still applies.

Native OpenCode `task` is denied. Native OpenCode delegation is not
supervisor fallback.

## Scope

Own only assigned files in `docs/`, `plans/`, `wiki/`, `runbooks/`,
`README.md`, `project-plan.md`, and `.codex/`. Those directories are not
blanket write permission. Preserve other edits.

You MUST NOT change application, tests, infrastructure, evaluation, or
`.codex/agents/` definition files.
A separate Codex or Grok agent independently verifies the result.
