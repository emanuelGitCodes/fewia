# 0002 — Frontend after the MVP checkpoint

- **Date**: 2026-08-31
- **Status**: accepted

## Decision

Phases 1–6 are backend-only. The React + TypeScript frontend enters in
Phase 7, after the MVP checkpoint in the plan holds.

## Options considered

1. Frontend after the MVP checkpoint — chosen.
2. Frontend in parallel from the start.
3. No frontend.

## Reason

The MVP plan states that a REST request from `curl` or the FastAPI
documentation page is enough for the first demo. A parallel frontend
adds coordination cost before the backend contract is stable.

## Consequences

- The frontend-dev agent stays idle until Phase 7.
- The first demo uses `POST /agent/analyze` directly.

Related: [0001](0001-real-bedrock-from-day-one.md).
