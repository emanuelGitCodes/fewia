# FEWIA browser tests

These Playwright tests drive the real local stack. The grocery journeys use
the live API, worker, and database. Only the provider tests fake anything,
and only the three surfaces that the base stack turns off (see Scope).

CI does not run this suite. The coordinator or a developer MUST run it by hand.

## Start the stack

From the repository root:

```sh
docker compose up -d
docker compose ps
```

Wait until `postgres`, `floci`, and `api` show `healthy`, and `web`,
`worker`, and `sync-worker` show `running`. The `bootstrap` service is a
one-shot job. It exits with code 0 after it runs the migrations and seeds
the demo user, so `docker compose ps` does not list it. If a service is not healthy, read its
logs with `docker compose logs <service>` before you run the tests.

The suite uses `http://127.0.0.1:5173` by default. If you set
`WEB_HOST_PORT` for the stack, set `FEWIA_E2E_BASE_URL` to the same port.

## Install Chromium

From the `frontend` directory:

```sh
npm ci
npx playwright install chromium
```

## Run the suite

```sh
npm run test:e2e
```

The command type-checks the test files with `tsconfig.e2e.json`. Then it runs
Playwright with two projects: `desktop` (1280x800) and `mobile` (390x844).

To test a frontend on a different address, set `FEWIA_E2E_BASE_URL`:

```sh
FEWIA_E2E_BASE_URL=http://127.0.0.1:5183 npm run test:e2e
```

## What each test checks

Each test MUST finish with no console errors, no uncaught page errors, and no
horizontal overflow.

- Smoke: default budget values, catalog size, and the chat-unavailable note.
- Example: the "Bean tacos for two" estimate, source label, sample notice, and
  nutrition total.
- Live regions: the estimate section has one status node. The conversation
  status has no status role.
- Pantry rebuild: a pantry change marks the estimate stale. The rebuild
  restores the heading and updates the total.
- Manual form: the 1-3 meal limits and a submitted estimate.
- Chat success: a held chat request shows one status node with "Your request
  is in progress." The Message box keeps focus, stays enabled, and is
  read-only. The page polls the job. The release shows the answer. The posted
  body holds the grocery job id as `previous_job_id`, a monthly limit of 10000
  cents, and a plan cap of 4000 cents.
- Chat failure: a failed chat job shows "The chat request failed. Retry checks
  the same request." The keyboard retry sends a second POST with the same
  `Idempotency-Key` and an equal body. The fake returns the same failed job, as
  the API does, so both POSTs get one job ID and the page shows the failed
  status again.

## Files

- `grocery.pw.ts` holds the grocery tests. `providers.pw.ts` holds the overlay
  and chat tests. The `.pw.ts` suffix keeps them out of vitest. Do not rename
  them to `.spec.ts`.
- `fakes.ts` holds the shared `test` fixture with the console, page-error, and
  overflow guard, plus the fakes. It holds no tests.
- `test-results/` and `playwright-report/` hold run output. Git ignores them.

## Scope

The base Compose stack turns off Bedrock chat and the Kroger overlay.
`providers.pw.ts` fakes only these with `page.route`:

- The `chat_configured` flag in `GET /api/grocery/providers`. The real
  response is fetched and every other field stays unchanged.
- The `/api/grocery/chat/jobs` endpoints. Any other `/api/grocery/chat/**`
  request fails the test. The fake follows `create_chat_job`: the same
  `Idempotency-Key` with an equal body returns the existing job, and the same
  key with a different body returns 409. The chat result reuses the plan,
  budget, nutrition, and spending source of the real grocery job. Its request
  is the captured grocery POST body. It has no evidence ID and a placeholder
  revision of 64 zeros, because a grocery job result holds neither.

The suite makes no real Bedrock or Kroger call. It does not cover the
Instacart handoff.
