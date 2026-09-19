# Grocery build progress

The active scope is [.codex/project-context.md](../.codex/project-context.md).
The user authorized continued implementation through the local grocery demo.
Live provider access remains pending. No push or merge is authorized here.

## Reviewed local slices

| Slice | Original commit | Integrated commit |
| --- | --- | --- |
| Job leases | 66a573c | 66a573c |
| SQS transport | 07752e7 | 07752e7 |
| Recovery sweep | febc3bc | febc3bc |
| Sample catalog | dbcb019 | d497681 |
| Budget calculation | 96b2f85 | 53f961b |
| Bedrock boundary | 352a9c6 | 352a9c6 |
| Delivery contracts | 97f9967 | ced7825 |
| Cooperative execution | 785b211 | 24107d4 |
| Deterministic planner | a696ae3 | 54d4d88 |
| Planning tool | a50a936 | a50a936 |
| SDK document repair | 1e34903 | 1e34903 |
| Chat parser | 3fd9898 | 3fd9898 |
| Chat dispatch | 7723b41 | 7723b41 |
| Public chat context | 9b7e20e | 9b7e20e |
| Bounded chat loop | 1e0551f | 1e0551f |
| Plan job adapter | 26e28e9 | f8bcd51 |
| Bounded worker command | 3272de0 | 5104b8e |
| Grocery API models | 63e7fcc | 0c40a86 |
| Grocery API routes | 4287878 | 9b11980 |
| Plaid schema | 2083eb1 | dd34743 |
| Plaid normalized pages | 42943f1 | d505bb9 |
| Plaid Sandbox HTTP | e031c43 | 5c5481d |
| Atomic Plaid sync | 7c79614 | 43d26f4 |
| Plaid readiness | 107914d | a3b2dfd |
| Ledger budget | fd0c006 | 64a129e |
| Shopping handoff schema | 4c1e9ec | 8609fe5 |
| Web shell | 7b61719 | 116703f |
| Web types | 4708370 | 3eb327b |
| Web validation | a0219cd | d237fcb |
| Web HTTP | 839a1de | d31a21e |
| Web polling | f3c02fe | 05aed39 |
| Exact money input | c33da24 | b3611aa |
| Meal controls | 6c0edef | 731806b |
| Estimate view | fd87231 | 8ef230d |
| Conversation status | 83c10fd | aba6e8a |
| Web request state | 33f0173 | 80b7d24 |
| Instacart development HTTP | 2a78f40 | Pending |

Each code layer is at most 150 added source lines. Tests and documentation
travel with their layer. Preserve every wiki entry during cherry-picks.
Root passed 793 backend tests with PostgreSQL enabled, Ruff, formatting, and
strict mypy. The provider branch passed 518 tests and migration 0006 on the
isolated PostgreSQL database. The integrated frontend passed 56 tests and its build.
The runtime branch passed a real PostgreSQL-to-Floci-to-estimate probe.
These checks are local. No CI, deployment, browser, or live provider claim follows.

## Work in progress

- Root: immutable evidence schema.
- `/private/tmp/fewia-job-consumer-runtime`: background heartbeat verification; continuous worker follows.
- `/private/tmp/fewia-grocery-budget`: deterministic shopping payload; durable dispatch follows.
- `/private/tmp/fewia-grocery-web`: App wiring and responsive styles.

The coordinator classifies each writer task as `simple`, `standard`,
`complex`, `exceptional`, or `maximum`. Those values map to `low`,
`medium`, `high`, `xhigh`, and `max`. Grok 4.6 uses `low` for simple
tasks. Grok 4.6 has a hard `medium` ceiling. Spark uses its CLI default.
Luna and Sol support selection through `max`. Writers use file tools
only. The coordinator runs commands and mechanical formatting.
Independent read-only Codex or Grok review remains authorized. The
separate workflow task owns supervisor changes.

## Remaining delivery sequence

1. Complete the bounded chat loop and job/API integration.
2. Add durable Instacart intent, cache, retry, and payload handling.
3. Connect the web app and run desktop/mobile browser checks.
4. Add continuous worker, heartbeat, Compose, and demo bootstrap.
5. Store immutable evidence revisions and run 30 scenarios three times.
6. Obtain Plaid Sandbox, Instacart development, and real Bedrock evidence.

The UI concept contains illustrative data. Render actual planner output.
Bean tacos for two estimate to $17.03 before pantry exclusions. Never label
fixtures as live provider evidence. Existing user containers remain untouched.

## 2026-09-07 continuation

The user checkpoint `84355a2` remains intact. The integrated backend passed
1,176 tests before the current HTTP work. The meal-control frontend passed
72 tests; its chat transport branch now passes 90 tests. Native Codex review
hit an account usage limit, so separate Grok source reviews now follow writers.
The coordinator runs all commands and verification gates.

The Compose snapshot at `/private/tmp/fewia-compose-check` runs as project
`fewia-grocery-b7d4`. Web: 127.0.0.1:5173. API: 127.0.0.1:8010. PostgreSQL:
127.0.0.1:55435. Floci: 127.0.0.1:4567. Bootstrap applied migration 0007 and
seeded User1. Browser requests passed through the continuous worker: bean tacos
for two cost 17.03 dollars; explicit olive-oil pantry stock reduced that to
11.04 dollars. The desktop and mobile checks had no console errors after repair.
The isolated emulator dead-lettered a probe after three deliveries.

Current work: chat HTTP routes and configured spending, a snapshot-backed
handoff API, worker routing for recorded chat and Plaid sync, and the remaining
chat UI. The 30-case corpus exists with three repeats declared; its schema tests
pass, but the 90-run evaluation has not run. Live provider credentials and
quality evidence remain pending. No push, merge, or live provider call occurred.

### Local verification checkpoint

The runtime slice is committed at `e903d81` on `codex/runtime-provider-jobs`.
It adds 139 application and Compose lines above `94f3db9`. A separate Grok
source review approved it. All backend gates passed, including 1,187 tests with
PostgreSQL enabled. An isolated worker consumed a queued 1,703-cent plan and
saved its matching owner-scoped evidence snapshot. Unconfigured chat and sync
jobs failed without fabricated results. Both test workers exited with code 0.

The web client is committed in two layers: `ffe729c` for HTTP and `ca49a01`
for polling. Independent Grok source review approved both. The coordinator ran
100 frontend tests and a successful production build. An earlier build exposed
two typed mock errors; the writer repaired them.

The repaired HTTP work passes 1,221 PostgreSQL-enabled backend tests. Its
configured-spending layer also passes alone with 1,197 tests. Final source
review remains in progress. Handoff API checks passed 14 tests and strict typing;
its source layers and standalone tests remain in progress. These slices still
need integration into this checkout. No push, merge, or live provider call ran.

### Integrated snapshot b7880e5

Spending and chat HTTP layers are saved at `7c6493e` and `473f1c5`. The reviewed
runtime and chat client layers are integrated. The checkout passes 1,232 backend
tests with PostgreSQL enabled, 100 frontend tests, and the production build. The
running local Compose snapshot is `/private/tmp/fewia-compose-current`. Its real
HTTP path returned a 1,703-cent plan, stored evidence, and an idempotent replay.
Provider configuration remains unset. Handoff API layers, evidence reads, frontend
provider configuration, and chat presentation are the next active work.

### Shopping routes checkpoint

Snapshot `84a145c` passes 1,276 PostgreSQL-enabled backend tests and all static
gates. It runs in `/private/tmp/fewia-compose-shopping`. Real local HTTP checks
passed for stored evidence, malformed revisions, and an unconfigured handoff
that preserves its prepared intent without dispatch. The sync API branch passes
1,228 tests and awaits review. The frontend branch passes 121 tests and a build;
its composer timeout/retry states are being repaired after independent review.

## Professor feedback checkpoint — 2026-09-07

The user clarified that the next objective is professor feedback on an early MVP,
not completion of every planned feature. Feature expansion is paused. All active
writers finished. The demo remains available at http://127.0.0.1:5173 from reviewed
Compose snapshot 84a145c in `/private/tmp/fewia-compose-shopping`. It demonstrates
meal selection, budget constraints, queued processing, itemized sample estimates,
and explicit pantry changes. Free-text chat UI wiring, live provider validation,
and the 90-run evaluation remain incomplete. Present these limits clearly.

Draft workspace adapters and evaluation input/scoring changes remain in the
isolated web and budget worktrees. They have not received final verification.
The reviewed handoff browser contract and HTTP client remain uncommitted in
`/private/tmp/fewia-provider-config`. Do not resume the full feature backlog
without the user directing the next work after feedback.

## 2026-09-07 documentation handoff

The wiki now holds [grocery-mvp-checkpoint.md](../wiki/phases/grocery-mvp-checkpoint.md).
This handoff preserves the professor-feedback MVP. It does not add features.

Working local path: meal controls → API → PostgreSQL outbox → Floci SQS → worker → itemized estimate.
Bean tacos for two: 1,703 cents. Olive-oil pantry rebuild: 1,104 cents.
Sample package prices: `backend/app/domain/catalog.py`.
Ingredient quantities: `backend/app/domain/catalog_recipes.json`.
Instacart creates development shopping-list links. Those links are not verified live prices.
The monthly limit is user-set. Plaid Sandbox adapters measure posted grocery spending.
Pending spending stays separate. The system does not recommend an allowance from income or bills.
The current demo uses fixture spending. No real bank or live provider is validated.
Chat panel, controller, and API exist. They are not wired into `App`.
Manual-to-chat handoff and unsaved-form synchronization remain.
Handoff browser contract and client exist. The button flow remains.
The 30-scenario corpus and budget evaluation driver exist.
No 90-run evaluation or model-quality result exists.
Preserved workspace adapters still need consolidation checks.
This handoff does not invent a current test count. It does not claim merge or CI success.
Existing local proof remains in [wiki/log.md](../wiki/log.md).
Live Bedrock, Plaid Sandbox, Instacart, and complete browser-chat validation remain pending.

Next work after professor feedback: connect shared form, chat, and estimate.
Keep the user cap, or apply a lower explicit cap.
Transfer a saved plan safely. Wire explicit handoff retries.
Finish the evaluation runner. Run real-provider checks when configured.

Wishlist only: nutrition per recipe and per serving.
Weekly totals from consumed quantities, with pantry stock still counted.
A future cash-flow grocery allowance. Neither wishlist item is required now.

The user authorized commit, push, one large consolidation pull request, and merge.
The user then authorized Graphify and a wiki refresh.
That consolidation is a one-time exception to the 150-line source cap.
Later work keeps the small pull-request rule.
This documentation worker did not commit, push, merge, or run Graphify.
Publication evidence stays pending until the coordinator records it.

## 2026-09-07 — Published checkpoint

The consolidation pull request merged into main. Both GitHub CI jobs passed.
Combined local verification passed 1,374 PostgreSQL-enabled backend tests and 238
frontend tests, with strict typing, formatting, lint, build, and fresh migrations.
The saved main checkout is current. Graphify now covers the full scanned corpus.
Its report records unresolved external references and repeated-edge consolidation.
See [the checkpoint](../wiki/phases/grocery-mvp-checkpoint.md) for publication links,
limitations, and next work. Feature expansion remains paused for professor feedback.
