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

New writers use Grok 4.6 medium with file tools only. The coordinator runs
commands and mechanical formatting. Other writer models need explicit user
approval under the updated policy. Independent read-only Codex review remains
authorized. The separate workflow task owns supervisor changes.

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
