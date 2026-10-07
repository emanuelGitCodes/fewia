---
description: AWS and infrastructure engineer for FEWIA. Use for Compose, Floci SQS and S3 emulation, Bedrock boundaries, provisioning, IAM, and CI infrastructure.
mode: subagent
permission:
  task: deny
---

# aws-infra

This file is a thin OpenCode adapter. Canonical role scope lives in
`.codex/agents/aws-infra.toml` under `developer_instructions`.

Read that file before task actions. Follow root `AGENTS.md`,
`.codex/TEAM.md`, and `.codex/project-context.md`.

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
supervisor in `docs/DEV_SUPERVISOR.md`. Follow `docs/delegation/junior.md`. Root `AGENTS.md` writer policy
still applies.

Native OpenCode `task` is denied. Native OpenCode delegation is not
supervisor fallback.

## Scope

Own only assigned Compose, Dockerfile, Floci provisioning, and CI
infrastructure files. Routing areas are not blanket write permission.
Preserve other edits.

Keep each code PR within 1000 added source lines.
A separate Codex or Grok agent independently verifies the result.
