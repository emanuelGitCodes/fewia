# Integrity check — 2026-10-04

- Main: `ed00904`, after pull requests #321 to #383 merged on 2026-10-04.
- Method: the senior coordinator reviewed every pull request with seven independent reviewers, composed all stacks locally, ran the full gates with PostgreSQL, merged in stack order, then exercised each merged subsystem on the local Compose stack with five probes and a browser session.
- GitHub Actions refused every job from 14:32 UTC because of the account spending limit. Local gates substitute: backend 9045 passed and 1 skipped, hosting 1775, tooling 359, frontend 492, Bedrock CDK 14, Compose config valid, dependency audits clean.

## What works as intended

| Subsystem | Evidence |
|---|---|
| HTTP API, 13 routes plus `/healthz` | 46 real jobs: serving scaling, shared-ingredient aggregation before package rounding, pantry lines at zero cost, typed exclusion conflicts, budget clamp with structured rejection, idempotency 202 and 409, evidence lookup, database at migration head |
| Jobs, outbox, worker, Floci queues | All jobs terminal, outbox fully published, a poison message reached the dead-letter queue after three receives, no tracebacks in any container |
| Frontend | Manual plan queued and rendered, pantry rebuild lowered the total, template picker returned ideas, mobile at 375 px has no horizontal overflow, handoff controls hidden without Instacart, chat shows the unavailable notice without Bedrock |
| Evaluation pipeline B5, C1, C2, C3 | 138 slots in matrix order, fixture slots never call a provider, no network connect, exit codes 0, 1, and 130, 135 of 138 fixture slots reproduce the archive, post-hoc rescore reproduces 23/33 |
| Job transport commands | Publish, consume, duplicate delivery, and interrupt paths behave as documented; AWS mode refuses before any socket when a profile or key is present |
| Database bootstrap, TLS settings, runtime role | Bootstrap idempotent with static output; verify-full cannot be downgraded; a password login as the constrained role allows the grocery tables and is denied DDL, DELETE, and GRANT |
| Hosting CDK, preflight CLI, runbook | Three phases synthesize; 13 of 14 security claims pass; the preflight CLI handled 13 scenarios with only allowlisted calls; runbook flags, outputs, and pricing arithmetic match |

## Findings

1. A diet conflict with a catalog recipe fails over HTTP as `handler_failed` with no detail; an exclusion conflict is typed. Owner: `backend/app/services/grocery_planner.py` and the planning tool mapping.
2. Hosting F1: every synthesized phase has placeholder availability zones and a missing context lookup. Fix: override `availability_zones` on both stack classes.
3. Hosting F2: the nginx container in `infra/hosting/app_task.py` runs as root; the other containers run as 1000:1000.
4. The P05 duplicate-delivery slots share the global `fewia-agent` queue with any running worker, so they fail when another consumer is up.
5. The host Floci port 4567 is not in the evaluation endpoint allowlist, so the benchmark cannot run from the host with `--local-services`.
6. The runtime database role grants SELECT only on the Plaid tables; the paused sync service writes them.
7. A 50 ms job takes 0.5 to 11 s because the worker publishes the outbox on the same thread as its 10 s long poll.

Cosmetic: the backlog said 12 routes, the API has 13; decision 0019 and the runbook said the hosting pull requests were unmerged.

## Backlog state

Done: A1 to A7, B1 to B6, C1 to C4, D2. Partial: D1 (task success 23/33 against a 90% target), D3 (paper and video), D5 (source merged, nothing deployed). Paused: D4.

## Side effects of the check

46 demo jobs and 2 prepared handoff rows in the local `fewia` database; orphan messages in the local dead-letter queue. All harmless.
