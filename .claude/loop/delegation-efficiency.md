# Loop: delegation-efficiency

Feature: Cut delegation tokens and waste for Claude Code, Codex, and OpenCode alike.
Publish authorized: yes (user, 2026-09-25) — stop before merges.
Writer model constraint: default order.
Base: main. Phase 1 merged 2026-09-25 by the senior with user authorization. User authorized merging this stack too.
User decisions (2026-09-25): tier S approved (coordinator drives writer directly);
port only "writers run no commands" from codex/grok-permission-diagnostics (no
approval-before-fallback); release all 9 steps; stop before merges.

## Principle

Optimizations live where all three tools see them: (1) dev_supervisor
subcommands, (2) one tool-neutral rulebook docs/DELEGATION.md. AGENTS.md,
.codex/TEAM.md, the OpenCode skill, and the Claude skill become thin pointers.

## Baseline (Phase 1, debt-guardrails)

Subagent tokens: juniors ~870k, reviewers ~670k, audits ~280k (~1.8M total),
for ~270 code lines + tests + docs. Worst: item 04 (1 YAML line) ~150k.
Writer/review-model tokens not measured (usage ledger not wired).

## Tier contract (goes into docs/DELEGATION.md)

| Tier | Complexity | Flow |
|---|---|---|
| S | simple; config or narrow; no new contract; no security surface | Coordinator: brief file -> dev_supervisor -> gates -> review. No subagents. |
| M | standard | One junior drives writer + gates + self-repair. Coordinator launches review. No reviewer agent. |
| L | complex+, security, or test-gate deliverables | Junior + reviewer agent (probes and mutations only; no full gate rerun) + review command. |

Rules: report <= 40 lines, fixed fields, SHA not pasted diffs, send once;
brief <= ~60 lines, paths not pasted content; one feasibility probe per
repo-dependent acceptance criterion before dispatch; reading budget per role
(junior: protocol + role + brief; writer: supervisor prompt only; reviewer:
reviewer role + brief + diff); stop background work before handback; every
long command has a timeout; review model != writer model; effort by tier.

## Contracts (shared tooling)

- `python -m dev_supervisor ... --work-item ID --phase implement|repair` (T2)
- `python -m dev_supervisor.usage --work-item ID` -> one summary line per phase (T2)
- `python -m dev_supervisor.review --base REF --brief FILE --complexity C --writer-model M [--timeout 900] [--work-item ID]`
  -> runs codex exec read-only with code-reviewer.toml instructions and -o FILE;
  prints only the final message (bounded); exit 0 APPROVE, 1 REQUEST_CHANGES, 2 BLOCKED (T3)
- `python -m dev_supervisor.gates --base REF [--reuse]`
  -> detects areas from changed paths; runs backend / frontend / root-tools / infra-bedrock gates;
  prints one line per gate + added code lines; records .fewia-supervisor-gates/<sha>.json (gitignored);
  --reuse prints the record when HEAD and tree are unchanged (T4)

## Items

| ID | Title | Owner | Tier | Base | Branch | Owned files | Depends | State |
|---|---|---|---|---|---|---|---|---|
| 01 | Decision 0014 + canonical docs/DELEGATION.md | senior (prose) | S | main | claude/delegation-efficiency-01 | docs/DELEGATION.md, wiki/decisions/0014-*.md, wiki/index.md | — | blocked |
| 02 | Writers edit files only; --task file check; lease release on pre-spawn error | aws-infra junior (dev tooling) | M | 01 | -02 | dev_supervisor/__main__.py, dev_supervisor/lease.py, tests/supervisor/* | 01 | merged |
| 03 | Wire usage ledger (--work-item, --phase, usage summary) | aws-infra | M | 02 | -03 | dev_supervisor/__main__.py, dev_supervisor/usage.py, tests/supervisor/* | 02 | queued |
| 04 | dev_supervisor.review command | aws-infra | M (L if >150) | 03 | -04 | dev_supervisor/review.py (new), tests/supervisor/test_review.py | 03 | blocked |
| 05 | dev_supervisor.gates command + line counter | aws-infra | M, may split 05a/05b | 03 | -05 | dev_supervisor/gates.py (new), tests/supervisor/test_gates.py, .gitignore | 03 | in_progress |
| 06 | Adapters: AGENTS.md, CLAUDE.md slim, TEAM.md, DEV_SUPERVISOR.md, tech-lead/code-reviewer TOML, OpenCode skill + adapters, Claude skill slim | senior (prose/config) | S | 04+05 | -06 | listed files | 04, 05 | blocked |
| 07 | .claude/agents adapters (own PR per repo rule) | senior (config) | S | 06 | -07 | .claude/agents/*.md | 06 | blocked |
| 08 | Wiki log entries | senior | S | 07 | -08 | wiki/log.md | 07 | queued |
| 09 | Pilot: Phase 1 follow-ups via new tiers; measure vs baseline | loop | S/M | main after merge | debt-followups-* | ruff.toml + dev_supervisor long lines; audit.yml --no-deps; conftest skip counter | 01–08 merged | queued |

Routing addition: dev_supervisor/ and dev tooling -> aws-infra (add to TEAM.md in item 06).

## Feasibility probes to run at dispatch

- 02: confirm GUARD text location; test that lease() leaves no stale state when execute() raises before attempt().
- 03: confirm usage.write_usage signature; events.py exposes codex turn.completed meta for token counts.
- 04: `codex exec --help` has -o/--output-last-message and --sandbox read-only; check exit codes; confirm timeout handling via subprocess.
- 05: list gate commands from AGENTS.md, tooling.yml, frontend package.json; the counter regex from junior-protocol.md.

## Events

- 2026-09-25 plan approved; waiting for Phase 1 merges.
- 2026-09-25 user authorized merging Phase 1 and this stack. Phase 1 merged (#157-#165).
- 01, 06, 07 written by senior (prose/config) on stacked branches; Luna review REQUEST_CHANGES (merge-rule conflict + 4 lost rules) -> fixed.
- 02 done 439d516 (65 lines, grok completed, no task_failed). Luna r1 REQUEST_CHANGES (prompt names git; annotation claim rejected). Repair 5f57416. Luna r2 APPROVE. Senior gates pass. PR #166. Junior tokens ~124k (tier M).
- 04, 05 in progress (juniors).
- 02 merged #166.
- 05 junior delivered 147 lines by compression (file noqa, fmt off, joined statements, encoded table). Rejected. Split into 05a (readable core) and 05b (record + --reuse). Rulebook gained a no-compression rule.
- 04 done 9b619a9, 149 lines, readable. Live smoke: Luna low effort, 31 s, 132,793 input tokens, found a real bug (synthetic verdict). Senior repair round 1 sent (synthetic verdict, temp file leak).
- Tokens so far (subagent): 02 junior ~125k; 04 junior ~155k; 05 junior ~126k (before split).
- Codex auth fails for every run (401 Incorrect API key) since ~mid-session; earlier Codex runs worked. User must re-authorize Codex. Reviews moved to separate read-only Grok sessions (`--permission-mode plan`) as the stated SHOULD deviation (review model differs from writer: not possible; separate agent session per decision 0009).
- 04 repair d26846e: 150 lines, readable, gates pass. Dogfood review command returned BLOCKED correctly (codex 401) — failure path verified live.
- Follow-up: dev_supervisor.review should support a grok provider fallback and surface the codex error line (401, quota) in its output.
- 05 split done: 05a 625fb0b (144 lines, clean), 05b 21b0c82 (65 lines). Junior ~284k tokens. Junior drafted exact code in scratch and dispatched it to the writer: rule violation (Grok as typist). Kept code (independent review follows); junior.md now forbids drafting code.
- Codex outage confirmed on status.openai.com ("Issues with Codex", identified). Reviews on Grok.
- Codex restored (user check). Prose stack reviewed with dev_supervisor.review (Luna): r1 REQUEST_CHANGES (tier S review before commit), r2 REQUEST_CHANGES (repair loop), r3 model APPROVE; tool reported BLOCKED because the model bolded the verdict inline -> review.py parser bug (item 04b, tier S).
- Review token cost via the tool: 309k input (medium, whole prose stack), 151k and 183k input (low). Output ~1-2k.
- 2026-10-03 State reconciliation: 01, 04, 06, and 07 blocked after their recorded review tools returned BLOCKED; 02 merged at #166; 03, 08, and 09 queued with no item-specific work event; 05 in_progress.
