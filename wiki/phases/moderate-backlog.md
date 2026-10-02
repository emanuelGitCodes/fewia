# Moderate backlog — local completion record

- **Date**: 2026-10-02
- **Scope**: items 06 through 15 rated exactly Moderate
- **Baseline**: `bb95042e63f4cad74e93c583e39db2d40f462109`
- **Application head**: `ef586c142f4e9e7f93741ee7ab5fb1b0b9d98149`
- **Records branch**: `codex/moderate-completion-records` (also includes approved current-scope docs `4e4e824`)
- **Status**: nine items complete locally; item 13 partial
- **Publication**: no push, pull request, merge, or deployment to the existing stack

This page records local implementation and verification. It does not claim production health or an evaluation benchmark.

## Scope

The work covers nginx API resolution, chat replay, plan-cap context, public answers, refusals, diet and ingredient errors, a read-only budget summary, Spoonacular read-time overlay stripping, a 40-meal catalog, and meal-template suggestions.

Plaid remains last. Older health and activity planning text stays historical.

## Items 06 through 15

| Item | Behavior | Status | Files |
|---|---|---|---|
| 06 | nginx resolves the API address again after container recreation. | Complete locally | [frontend/nginx.conf](../../frontend/nginx.conf) |
| 07 | Intermediate model turns replay validated tool calls only. User-visible conversation history remains. | Complete locally | [backend/app/agent/chat_loop.py](../../backend/app/agent/chat_loop.py) |
| 08 | Server context exposes the plan cap. The prompt preserves or lowers the cap. Latest pantry changes remain. Catalog pairs supply ingredient IDs and names. | Complete locally | [chat_context.py](../../backend/app/agent/chat_context.py), [chat_loop.py](../../backend/app/agent/chat_loop.py), [chat_job.py](../../backend/app/services/chat_job.py) |
| 09 | Public answers derive totals, acceptance, missing prices, and conflicts from validated tools. Previous estimates remain for unresolved requests. | Complete locally | [chat_answer.py](../../backend/app/agent/chat_answer.py), [ChatWorkspace.tsx](../../frontend/src/ChatWorkspace.tsx), [App.tsx](../../frontend/src/App.tsx) |
| 10 | Bounded JSON refusal parser. Fixed text for secrets, purchases, and external URLs. No public plan or evidence on refusal. | Complete locally | [chat_refusal.py](../../backend/app/agent/chat_refusal.py), [chat_loop.py](../../backend/app/agent/chat_loop.py) |
| 11 | Typed unsupported diet and ingredient errors with bounded static clarification. Unknown values are not echoed or guessed. | Complete locally | [planning_tool.py](../../backend/app/agent/planning_tool.py), [chat_dispatch.py](../../backend/app/agent/chat_dispatch.py), [chat_answer.py](../../backend/app/agent/chat_answer.py) |
| 12 | Read-only `get_budget_summary` accepts only an empty exact dict. Server-owned budget, period, and source. Formatted USD. Pending cents stay separate. A successful summary preserves an existing candidate. | Complete locally | [budget_tool.py](../../backend/app/agent/budget_tool.py), [chat_dispatch.py](../../backend/app/agent/chat_dispatch.py), [chat_loop.py](../../backend/app/agent/chat_loop.py) |
| 13 | API reads strip old price overlays from copied results before optional current overlay attachment. Stored data is preserved. | Partial. Read-time suppression is complete. Data deletion is unapproved. | Decision [0016](../decisions/0016-spoonacular-read-time-overlay.md), [`.codex/project-context.md`](../../.codex/project-context.md) |
| 14 | 40 supported meals in catalog `sample-prices-v2`. Original 10 recipes, quantities, and prices remain. 22 mapped ingredients remain. | Complete locally | [catalog.py](../../backend/app/domain/catalog.py), [catalog_recipes.json](../../backend/app/domain/catalog_recipes.json), [grocery.py](../../backend/app/domain/grocery.py) |
| 15 | Six deterministic presets, bounded immutable cache, `POST /grocery/templates` with server budget filtering. Typed client and meal-ideas UI. | Complete locally | [plan_templates.py](../../backend/app/services/plan_templates.py), [api/plan_templates.py](../../backend/app/api/plan_templates.py), [templateApi.ts](../../frontend/src/templateApi.ts), [useTemplateSuggestions.ts](../../frontend/src/useTemplateSuggestions.ts), [TemplatePicker.tsx](../../frontend/src/TemplatePicker.tsx) |

## Validation

Backend at core `c3f72fce65864011bfa527a8ba461f1671031992`: 1678 tests passed. One existing Starlette deprecation warning. `FEWIA_REQUIRE_DB=1` used an isolated migrated PostgreSQL database. Ruff check, Ruff format, and strict mypy passed. No backend source changed after this head.

Final frontend lint, full tests, and production build passed at `ef586c142f4e9e7f93741ee7ab5fb1b0b9d98149`. Focused picker tests passed 12 of 12. Strict TypeScript passed.

Independent Luna review approved final core (high), template hook (medium), final picker (medium), and current-scope docs (low). The budget module coverage finding closed with an empty-dict-subclass regression test.

### Evidence classes

| Class | Result |
|---|---|
| Unit and fixture | Backend 1678 passed. Frontend lint, tests, and production build passed. Picker tests 12 of 12. |
| Mutation | Removing the JSON key guard caused 2 expected failures. Accepting nonempty budget args caused 6. Weakening exact dict to `isinstance` caused 1. Clearing a candidate on summary success caused 1. Throwaway checkouts were removed. |
| Live Bedrock | Isolated API, outbox, Floci, and worker with real Nova 2 Lite. Bean tacos for 2 with pantry olive oil: 1104 cents. Removing oil: 1703 cents. Cap 2500 preserved both. Exact secret-refusal answer with no plan or evidence. Budget summary: 2500 available, 0 pending, manual source, one summary tool, zero planner revisions. |
| Live template API | Five vegan suggestions under 4000 cents. |
| Browser | Chose 3 meals and built an accepted 2299-cent plan. Preserved monthly 100, cap 40, vegan, olive-oil pantry, and egg exclusion. Empty 0-cap state, mocked network failure and retry, stale-choice hiding, real 4000-cent budget chat, and Previous estimate label passed. Deferred network check confirmed 1 request, disabled Find while pending, then re-enabled. That delayed-response fixture still used the real API response. Desktop 1440 and mobile 390 had no horizontal overflow. Console had 1 expected `ERR_FAILED` from the intentional template-network abort. |
| Emulator / Sandbox / deployed | No live Plaid. No Instacart checkout. No live store prices. No deployed stack claim. |

Saved local artifacts under `backend/artifacts/moderate-backlog/verification` are untracked evidence. Valid screenshots: `desktop.png` and `mobile-picker.png`. Do not cite `mobile-fullpage-capture-artifact.png`. A repeated-tile mobile full-page screenshot was a capture artifact. The DOM had one header and one `h1`. Valid viewport recapture passed. Detector run on changed UI files returned `[]`.

This record does not claim a broad browser regression suite, a 90-run evaluation, live Plaid, Instacart checkout, or live store prices.

### Repaired failures

Initial gate failures were repaired: Ruff long strings; TypeScript test fixture narrowing; accumulated mock calls; shared App hook mock default (3 failed, 392 passed before repair); manual-start stale transition; reviewer boundary coverage. One incorrect temporary database URL produced 11 database errors. The corrected URL passed without application changes. Earlier reader-tool BLOCKED reports were brief ambiguity. No provider or model substitution occurred.

## Local stack order

These are local branches. They are not published pull requests. Every slice stays within 150 added application lines.

1. `codex/moderate-foundation` `ea89dc9` — 114
2. `codex/moderate-answers` `26ccb60` — 139
3. `codex/moderate-clarifications` `ddc73ee` — 90
4. `codex/moderate-refusals` `b08471b` — 64
5. `codex/moderate-budget-foundation` `39a5659` — 141 (later test-only coverage repair in core)
6. `codex/moderate-templates` `e42531a` — 137
7. `codex/moderate-template-api` `3668c79` — 142
8. `codex/moderate-template-client` `033db58` — 149
9. `codex/moderate-app-integration` `c3f72fc` — 144
10. `codex/moderate-template-state` `ba119a6` — 132
11. `codex/moderate-template-picker` `ef586c1` — 126
12. `codex/moderate-completion-records` — documentation only

Retained commits remain available. Completed managed worktrees were recoverably archived.

## Remaining retention decision

Item 13 does not delete stored rows. Table deletion needs a separate retention decision. [`.codex/project-context.md`](../../.codex/project-context.md) states: "Table deletion needs a separate retention decision." Decision [0016](../decisions/0016-spoonacular-read-time-overlay.md) states: "Local job rows written before this decision can still hold a stored Spoonacular total. Deleting them needs a separate retention decision."

Existing local database read-only aggregate inventory: `daily_environment` 360, `daily_finance` 360, `daily_health` 341; total 1061. `model_runs` 0, `predictions` 0, jobs with stored root overlay 0, evidence snapshots with overlay at any depth 0. No row contents were read. No original records or schema changed. This page does not propose or claim an approved destructive policy.

Cleanup: the dedicated browser session is closed. All `fewia-moderate-preview` containers, network, and volumes were removed. `fewia-moderate-checks` was removed. The pre-existing fewia stack was not restarted or modified. Current original container health is recorded by the coordinator separately. Local code is not deployed to that original stack.

## Loop usage

Recorded supervisor usage through completed implementation and scope-documentation review, before this completion-record writer and review:

- 39 writer runs (implement and repair)
- 22137248 input tokens
- 489546 output tokens
- 7781.391 cumulative process seconds
- 34 review runs
- 4106580 input tokens
- 55977 output tokens
- 1725.473 cumulative process seconds

Input includes reported cached input. Native junior and coordinator token totals were not exposed. This is not full-session token or cost accounting. No USD cost was calculated.
