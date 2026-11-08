# 0029 — `make up` starts Kroger in fixture mode

- Date: 2026-11-08
- Status: accepted
- Amends: [0027 — GPT-6 Luna is the default local chat provider](0027-luna-default-chat-provider.md)

## Decision

`make up` starts GPT-6 Luna and the Kroger fixture mode. The fixture mode
sets `FEWIA_KROGER_MODE=fixture` through `compose.kroger-fixture.yaml`.

In fixture mode, the real `KrogerClient` runs over an `httpx.MockTransport`.
The transport serves invented stores, products, prices, and tokens. It makes
no network call. A local route stands in for the Kroger sign-in page. It
redirects only to `FEWIA_KROGER_REDIRECT_URI`.

Every fixture result carries `source: "fixture"` or the quote kind
`store_fixture`. The `/prototype` page shows `FIXTURE, NOT KROGER` next to
each fixture result. A fixture cart add changes no Kroger cart.

Live Kroger stays the explicit `compose.kroger.yaml` command in
[LOCAL_GROCERY_DEMO.md](../../docs/LOCAL_GROCERY_DEMO.md). Fixture mode
with any Kroger credential file fails closed, and the Kroger routes return
503.

## Options considered

1. Keep `make up` without Kroger. The grader then cannot reach the cart,
   because the Kroger terms forbid shipping the client ID.
2. Add a separate target for fixture Kroger. The README quick start would
   then need a second command for the grader.
3. Add fixture Kroger to `make up`. Chosen. The grader runs one command with
   one OpenAI key and reaches the full plan-to-cart path.

## Reason

The owner chose this on 2026-11-08. The course rubric gives 30% to code
runnability, and the grader runs the code ZIP. Fixture data is invented,
because the Kroger terms forbid copies of real responses.

## Consequences

- A fixture result is not Kroger evidence. Evaluation records and the demo
  MUST label it `fixture`.
- The fixture token key derives from a fixed label. It protects only fake
  tokens.
- The live demo command does not change.
