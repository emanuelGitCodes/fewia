# OpenCode project adapters

This directory is project-only. It does not change global OpenCode
settings, credentials, or plugins.

Canonical role scope lives in `.codex/agents/<role>.toml` under
`developer_instructions`. These Markdown files are thin adapters.
`model` in the TOML files is Codex-only.
The TOML files keep the Luna model.
They MUST NOT pin `model_reasoning_effort`.
Native dispatch MUST select effort from the complexity rubric.
OpenCode inherits the user's model choice.

Root writer policy lives in `AGENTS.md`. Coding writes use the CLI
supervisor in `docs/DEV_SUPERVISOR.md`. Native OpenCode `task` is not
supervisor fallback.

## Folder tree

```
.opencode/
  README.md
  agents/
    agent-dev.md
    aws-infra.md
    backend-dev.md
    catalog-dev.md
    database-dev.md
    docs-dev.md
    eval-engineer.md
    frontend-dev.md
    ml-dev.md
    provider-dev.md
    reliability-dev.md
    security-dev.md
    tech-lead.md
    test-engineer.md
  skills/
    fewia-workflow/
      SKILL.md
```

## Select the primary

Start OpenCode with `tech-lead`:

```bash
opencode --agent tech-lead
```

`tech-lead` is the only project-defined primary.
Built-in Build and Plan remain available.
The other 14 roles are subagents.

## Invoke a specialist

Ask `tech-lead` to call a specialist by name, such as `@backend-dev`.
Give an exact owned-file brief. Routing areas are not blanket write
permission.

`tech-lead` MAY delegate bounded exploration with native OpenCode `task`.
Specialists MUST NOT spawn further agents.
Child workers MUST NOT switch branches in a shared checkout.
Serialize writes to shared files.

Native OpenCode has no implicit worktree isolation.
Use an explicit isolated worktree when the assignment requires one.

## Skills

The project skill is `fewia-workflow` at
`skills/fewia-workflow/SKILL.md`. Use it for bounded FEWIA workflow,
supervisor writes, independent review, and backend gates.

## Discovery

List project agents:

```bash
opencode agent list
```

Inspect the skill:

```bash
opencode debug skill
```

If piped `opencode debug skill` output is truncated, redirect stdout to a
temporary file and inspect that file.
You MUST NOT print global config or secrets.
