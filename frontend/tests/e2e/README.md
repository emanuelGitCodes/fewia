# FEWIA browser tests

These Playwright tests drive the real local stack. They do not mock the
network. The grocery journeys use the live API, worker, and database.

CI does not run this suite. The coordinator or a developer MUST run it by hand.

## Start the stack

From the repository root:

```sh
docker compose up -d
docker compose ps
```

Wait until `postgres`, `floci`, and `api` show `healthy`, and `web`,
`worker`, and `sync-worker` show `running`. The `bootstrap` service is a
one-shot job. It exits with code 0 after it runs the migrations, so
`docker compose ps` does not list it. If a service is not healthy, read its
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

## Files

- `grocery.pw.ts` holds the tests. The `.pw.ts` suffix keeps them out of
  vitest. Do not rename it to `.spec.ts`.
- `test-results/` and `playwright-report/` hold run output. Git ignores them.

## Scope

This suite does not cover chat sends, Spoonacular, or the Instacart handoff.
