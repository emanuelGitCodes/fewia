# Browser tests

These tests drive the local Vite app on `http://127.0.0.1:5180`.

## Commands

Run this from `frontend`:

```bash
npm run test:browser
```

`test:browser` type-checks `tsconfig.e2e.json`. It then runs Playwright.

Install Chromium before the first run:

```bash
npx playwright install --with-deps chromium
```

CI runs the same install in the frontend job, then `npm run test:browser`.

## Evidence boundary

The tests intercept every browser call to `/api/**`.

Unknown `/api/**` paths MUST fail the test. They MUST NOT reach a real backend.

`frontend/e2e/fixtures/plans.json` is a deterministic browser fake.

The fake provider flags are chat true, Plaid false, and Instacart false.

The tests MUST NOT call Bedrock, Plaid, Instacart, or Spoonacular.

Chat answers in this suite are mock strings. They are not quality evidence.

The Spoonacular overlay is an opt-in fake. It MUST NOT replace the sample catalog total.

The sample estimate notice MUST stay:

Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.
