# Wiki index

The schema and conventions live in [schema.md](schema.md). The
chronological record lives in [log.md](log.md).

## Decisions

- [0001 — Real Bedrock from day one](decisions/0001-real-bedrock-from-day-one.md)
- [0002 — Frontend after the MVP checkpoint](decisions/0002-frontend-after-mvp-checkpoint.md)
- [0003 — Private GitHub repo, stacked pull requests](decisions/0003-private-github-stacked-prs.md)
- [0004 — Six-agent team with a delegating tech lead](decisions/0004-agent-team-delegation.md)
- [0005 — Human-gated agent learning](decisions/0005-human-gated-agent-learning.md)
- [0006 — Codex writes, Claude verifies](decisions/0006-codex-writes-claude-verifies.md)
- [0007 — Evidence ID format](decisions/0007-evidence-id-format.md)
- [0008 — Grocery bot with local Floci services](decisions/0008-grocery-bot-pivot.md)

- [0009 — Codex and Grok development review](decisions/0009-codex-grok-review.md)
- [0010 — Park Instacart. Use USDA nutrition and Spoonacular cost](decisions/0010-usda-spoonacular-overlay.md)
- [0011 — Dynamic delegated effort](decisions/0011-dynamic-delegated-effort.md)
- [0012 — Tool calling as the orchestration boundary](decisions/0012-tool-calling-orchestration.md)
- [0013 — Claude Code as senior coordinator](decisions/0013-claude-senior-coordinator.md)
- [0014 — Tiered delegation and token budgets](decisions/0014-tiered-delegation.md)
- [0015 — Writer routing by difficulty](decisions/0015-writer-routing-by-difficulty.md)
- [0016 — Spoonacular prices at read time, user-entered budget](decisions/0016-spoonacular-read-time-overlay.md)
- [0017 — Forty-meal sample catalog](decisions/0017-forty-meal-catalog.md)
- [0018 — Retain legacy data for now](decisions/0018-retain-legacy-data.md)
- [0019 — Invitation-only hosted demo](decisions/0019-invitation-only-hosting.md)
- [0020 — One hook set for every agent CLI](decisions/0020-shared-hooks-for-every-agent-cli.md)
- [0021 — Claude-only delegation in Claude Code sessions](decisions/0021-claude-only-delegation.md)

## Phases

- [Phase 0 — Repo bootstrap and the agent team](phases/phase-0.md)
- [Phase 1 — Skeleton: Compose, schema, CI](phases/phase-1.md)
- [Phase 2 — Synthetic data](phases/phase-2.md)
- [Phase 3 — Deterministic tools and FastAPI endpoints](phases/phase-3.md)
- [Grocery MVP checkpoint — professor feedback](phases/grocery-mvp-checkpoint.md)
- [Moderate backlog — local completion record](phases/moderate-backlog.md)
- [Evaluation completion checkpoint — local evidence](phases/evaluation-completion.md)
- [Evaluation draft publication and Graphify update](phases/evaluation-publication.md)
- [Evaluation recovery checkpoint — published source and current recovery](phases/evaluation-recovery.md)
- [Backlog build checkpoint — branches, checks, and remaining work](phases/backlog-build-20261003.md)
- [Agent catalog scope correction — 40-meal wording in role briefs](phases/agent-catalog-scope-20261003.md)
- [Backlog resume — published evidence and remaining work](phases/backlog-resume-20261003.md)
- [Benchmark — original fixture and live results, known gold mismatch, and release limits](phases/benchmark-20261003.md)
- [Post-hoc gold correction — saved observations, six tool deltas, and unchanged release limits](phases/posthoc-gold-20261003.md)
- [Fresh live benchmark — 25/33 task success, 97.3% supported claims, and unchanged release limits](phases/benchmark-20261005.md)
- [Hosting preparation — accepted private access, published source, bounded CI and CLI usage](phases/hosting-preparation-20261003.md)
- [Backlog final record — published PRs 322-381, integration evidence, and Graphify archive](phases/backlog-final-20261003.md)
- [Integrity check — merged main exercised end to end, findings, and backlog state](phases/integrity-20261004.md)
- [Tonight prototype — Familiar and Pantry Edit local demo](phases/tonight-prototype.md)

The grocery checkpoint is the active product record. Phases 0 through 3 remain historical.

The current product supports 40 meals under [decision 0017](decisions/0017-forty-meal-catalog.md)
and the [project scope](../.codex/project-context.md).
It supports 1-3 meals per request and 1-8 servings per meal.
The benchmark does not provide exhaustive catalog coverage.
Its original results remain 17/33 task success and 98/100 bounded supported claims.
The separate [post-hoc correction](phases/posthoc-gold-20261003.md)
changes six F04/F05 tools assessments using the same saved observations.
Task success becomes 23/33 (69.7%), with ten failed and zero unassessed.
The 90% target still FAILS; claims and 0/33 no-tool success stay unchanged.
The correction matches the existing final-turn scorer contract.
It changes no scoring code or allowed outcomes and makes no provider or database calls.
It is not a fresh batch, model retest, or independent benchmark.
A [fresh live batch](phases/benchmark-20261005.md) on 2026-10-05 reports 25/33
(75.8%) task success; the 90% target still FAILS. Claims PASS at 109/112 (97.3%).
D3's [author-owned course supporting pack](../docs/course/README.md) is prepared.
It links prompts, figures, failure examples, and provenance for the author's own writing.
The final paper has a maximum of eight pages in two columns.
The owner still writes the final paper and records/submits the video.
Coordinator verification and independent review remain open.

Source publications now include original benchmark #349, post-hoc record #353,
course pack #361, and later hosting source through runbook #381.
The [hosting snapshot](phases/hosting-preparation-20261003.md)
keeps its 2026-10-03 heads, parents, and CI observations.
The [final record](phases/backlog-final-20261003.md) lists the 60 created pull requests #322-#381 as of its 2026-10-04 snapshot; all merged later that day, see the [integrity check](phases/integrity-20261004.md).
Observed main remains `8bfd4b80c71bca85cb1245446d933f965b17b86a`.
[Decision 0019](decisions/0019-invitation-only-hosting.md) accepts owner and invited-user access with no public signup.
Invited users share the current server-selected demo context. They have no private application accounts.
D5 source, preflight CLI, and runbook are published. Live deployment still awaits owner inputs and confirmations.
No AWS resources, users, or invitations have been created by this run.
The owner MUST confirm every mutating AWS step first. No merge authorization exists.
D4 remains paused. Live Instacart stays parked.

## Tonight prototype

- [Phase record](phases/tonight-prototype.md)
- [WCAG 2.2 AA audit](../docs/design/tonight-wcag-audit.md)
- [VoiceOver audit](../docs/design/tonight-voiceover-audit.md)

## Development operations

- [Development writer supervisor](../docs/DEV_SUPERVISOR.md)
- [Agent hooks for Claude Code, Grok, and Codex](../.claude/README.md#hooks)
