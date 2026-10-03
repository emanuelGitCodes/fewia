# Loop: tech-debt-2

Feature: Tech-debt audit 2026-09-29, Phases 1-3. Phase 4 (Plaid, React 19, eslint 10) is paused by the user.
Publish authorized: yes (user, 2026-09-30); PRs #191-#202
Writer model constraint: --only --model gpt-6.1-sol, then gpt-6-luna (user, 2026-09-29). No Sonnet juniors. Item 00 uses grok-4.6 as a bootstrap exception.

## Audit corrections from probes

- Item "DB tests skip silently": done already. CI sets FEWIA_REQUIRE_DB=1 (#162, #165). Dropped.
- Item "floci healthcheck": the image ships its own HEALTHCHECK (#160). Dropped.
- Plaid code is out of scope for refactors. Plaid files get only mechanical edits (noqa, constant import).

## Contracts

- `app/providers/http_client.py`: `DEFAULT_TIMEOUT`, `build_http_client(base_url: str, headers: Mapping[str, str]) -> httpx.Client`; `aws_client_config(**overrides) -> botocore.config.Config` in `app/providers/aws_config.py`.
- `app/demo.py`: `DEMO_USER_ID: Final = 1`.
- `app/services/job_submission.py`: `find_existing_job(session, kind, idempotency_key) -> models.Job | None`.
- `frontend/src/usePolledJob.ts`: shared polling hook; each caller keeps its own budget and error text.

## Items

| ID | Title | Owner | Complexity | Base | Branch | Owned files | Depends on | State | Round | Review | PR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 00 | Codex writers: read-only shell; edit-free run = no_edits | senior prose + grok writer | standard | main | claude/tech-debt-2-00 | dev_supervisor/__main__.py, tests/supervisor/*, AGENTS.md, docs/DELEGATION.md, wiki/log.md | — | merged | 0 | — | — |
| 01 | Docs drift: infra README, PRODUCT, project-context, wiki log, rollback note, dead refs | senior (prose) | simple | main | claude/tech-debt-2-01 | infra/README.md, PRODUCT.md, .codex/project-context.md, wiki/log.md, runbooks/*, project-plan.md, docs/DEV_SUPERVISOR.md, plans/plaid-instacart-repository-update-plan.md | — | merged | 0 | — | — |
| 02 | Drop unused ML deps and empty app/ml | backend-dev | simple | main | claude/tech-debt-2-02 | backend/pyproject.toml, backend/uv.lock, backend/app/ml/ | — | verified | 0 | — | — |
| 03 | CI permissions, compose config job, image pins | aws-infra | simple | main | claude/tech-debt-2-03 | .github/workflows/ci.yml, compose.yaml | — | verified | 0 | — | — |
| 04 | Enable BLE and DTZ in backend ruff | backend-dev | simple | 02 | claude/tech-debt-2-04 | backend/pyproject.toml, 19 app files (noqa only), 8 test files (DTZ) | 02 | verified | 0 | — | — |
| 05 | Notice parity contract test | test-engineer | standard | main | claude/tech-debt-2-05 | backend/tests/test_notice_parity.py | — | verified | 0 | — | — |
| 06 | Shared httpx and boto config | backend-dev | standard | 04 | claude/tech-debt-2-06 | app/providers/http_client.py, aws_config.py, instacart.py, spoonacular.py, bedrock.py, local_sqs.py, local_sqs_consumer.py, local_artifacts.py | 04 | merged | 0 | — | — |
| 07 | DROPPED: provider_runtime swallows on purpose so secrets stay out of the exception chain | — | — | — | — | — | — | dropped | 0 | — | — |
| 08 | One DEMO_USER_ID | backend-dev | simple | main | claude/tech-debt-2-08 | app/demo.py + 8 importers | — | verified | 0 | — | — |
| 09 | One job lookup | backend-dev | standard | 08 | claude/tech-debt-2-09 | services/job_submission.py, api/chat.py, api/grocery.py, api/sync.py | 08 | verified | 0 | — | — |
| 10 | Shared usePolledJob hook | frontend-dev | standard | main | claude/tech-debt-2-10 | frontend/src/usePolledJob.ts, useChatJob.ts, useGroceryJob.ts | — | superseded | 0 | — | — |

Waves: S items 01 02 03 08 run in the senior session; juniors 05 10 → 04 → 06 09 → 07.

## Agents

| ID | Junior agent | Worktree | Head SHA | Writer model |
|---|---|---|---|---|

## Events

- 2026-09-29 loop opened; user released Phases 1-3.

## Follow-ups

- Two settings systems (`config.Settings`, `GroceryProviderSettings`) and raw env read in `usda_refresh.py:25`.
- Real `time.sleep` in `tests/supervisor/test_process.py`.
- Route-level `commit()` in api/*.py beyond the job lookup.
- Phase 4 (paused): Plaid decision, React 19 and react-test-renderer, eslint 10.
- 2026-09-29 01 committed 9664015; gates PASS (docs only).
- 2026-09-29 02 c8e46d0 gates PASS, review APPROVE (luna low).
- 2026-09-29 03 03dca1d gates PASS, review APPROVE (luna low).
- 2026-09-29 08 f7f14be gates PASS, review APPROVE (luna low); grok-written before the model switch.
- 2026-09-29 Sol and Luna writers returned completed with no edits: GUARD forbids shell; Codex reads via shell. User chose read-only shell rule (item 00).
- 2026-09-29 05 7cbcf40 NUTRITION_NOTICE case uses the wrong backend constant (meal_nutrition.NOTICE is correct); repair pending item 00.
- 2026-09-29 10 luna diff: submit depends on [abortActive, options]; unstable identity. Repair pending item 00.
- 2026-09-29 04 bc1345f committed after UTC-import repair.

## Verified heads (2026-09-29)

| ID | Base | Head | Lines | Review |
|---|---|---|---|---|
| sol | main | a8e5d1f | user's edits | tests 154 pass |
| 00 | claude/sol-6-1-model-id | e0029c3 | 43 | APPROVE luna (grok writer, bootstrap) |
| 01 | main | 9664015 | 0 (prose) | gates PASS; senior prose |
| 02 | main | c8e46d0 | 0 | APPROVE luna |
| 03 | main | 03dca1d | 28 | APPROVE luna |
| 04 | 02 | bc1345f | 29 | APPROVE sol |
| 05 | main | 56f688d | 0 (test) | APPROVE sol r2 |
| 06 | 04 | 9242155 | 40 | APPROVE luna r2 |
| 08 | main | f7f14be | 19 | APPROVE luna |
| 09 | 08 | 5d0a57a | 21 | APPROVE luna |
| 10a | main | f37ebaf | 141 | APPROVE sol |
| 10b | 10a | f2c2bbb | 15 | APPROVE sol |

Item 10 (claude/tech-debt-2-10) is superseded by 10a + 10b (identical final tree).
- 2026-09-30 00 merged origin/main @ 0abe83a (log conflict; no_edits rule aligned with the decision 0015 fallback ladder; tools gates PASS). 01 merged origin/main and 00 @ 7cf056a (log conflicts). Local simulation of the full merge order, plus decision-0016 and nutrition-plural: no conflicts, all gates PASS. Pushes and merges wait for user authorization.
- 2026-09-30 App test before merge: integration branch claude/integration-level1 @ bd7502d (all 13 branches) ran in Compose project fewia-l1 (web 5176, api 8013). Manual planner, pantry rebuild, two-meal over-cap plan, nutrition ("1 serving"), idempotent resubmit, 409 conflict, 422 period and recipe checks pass. Three API cases match an origin/main stack byte for byte (except the per-job evidence hash). Job latency ~11 s on both. Pre-existing on main: exclusion conflict fails as handler_failed with a generic UI error (task chip opened). No Bedrock or Spoonacular in this run.
- 2026-09-30 user: merge all. Merged #194 ecf14a6, #195 8a61c80, #197 11b5b60, #199 9321b65, #201 42651ed, #200 (retargeted) , #202 (retargeted).
- 2026-09-30 #193: merged main in (wiki/log.md conflict, both sides kept in date order) -> 6cc6d95; Tooling CI flake (test_active_tool_cannot_be_declared_stalled) passed on rerun; merged f3d28ec.
- 2026-09-30 #196: merged main in; job_consumer.py conflict took main's fail() helper; ruff BLE001 on two intentional blind excepts; grok-4.6 low added two noqa lines f9b3acf; gates PASS 29/150; review APPROVE gpt-6-luna f9b3acf; same CI flake passed on rerun; merged 869225f.
- 2026-09-30 #198 retargeted to main; gates on main+06: only failure test_synth_loader, which also fails on plain main against the non-empty fewia-l1 DB (environment); merged b9f9f05.
- 2026-09-30 #212 (nutrition "1 serving") merged 6919fda. #213 (decision 0016 + checkpoint; main merged in, log conflict resolved) merged b4a374f. Loop complete.
- 2026-10-03 State reconciliation: 00-01 merged; 02-05 and 08-09 verified from their recorded review heads; 06 merged at b9f9f05; 07 stays dropped; 10 superseded by 10a and 10b.
