# Demo shot list

This file is a shot list of actions and observable states. It holds no narration.
The author writes and speaks every word. The author presents live on Zoom on
2026-11-09 and submits a narrated video of the same run.
This file claims no recorded run and no deployed demo.

## Time budget

The live limit is 15:00. The planned total is 11:30. The spare time is 3:30.
The presenter MUST cut a shot before the limit, not speed up.
Cut order: shot 9, then shot 4, then shot 8.

| Shot | Topic | Time | Running total |
|---|---|---|---|
| 1 | Scope and the agent's job | 1:30 | 1:30 |
| 2 | Plan on `/prototype` | 1:30 | 3:00 |
| 3 | Ask FEWIA (Bedrock) | 1:30 | 4:30 |
| 4 | Kroger store, price, cart | 2:00 | 6:30 |
| 5 | Stop before payment | 1:00 | 7:30 |
| 6 | How it is tested | 1:30 | 9:00 |
| 7 | Cost and latency | 0:45 | 9:45 |
| 8 | One real failure | 0:45 | 10:30 |
| 9 | Limits | 1:00 | 11:30 |

## Before the session

Expected states are observation targets. No one has run this list.

- The owner prepares an isolated local runtime from [Compose](../../compose.yaml).
  [LOCAL_GROCERY_DEMO.md](../LOCAL_GROCERY_DEMO.md) holds the start steps.
  This file adds none.
- The demo starts at `http://127.0.0.1:5173/prototype`, per
  [decision 0026](../../wiki/decisions/0026-prototype-default-route.md).
  `/app` is the older page. The demo MUST NOT start there.
- The operator MUST keep credentials, client IDs, key files, and file contents
  off the screen and out of the recording.
- The operator MUST NOT create a public URL.
- Bedrock needs the overlay in
  [LOCAL_GROCERY_DEMO.md](../LOCAL_GROCERY_DEMO.md) and owner-approved provider use.
  Kroger needs its overlay and the owner's sign-in.
- Run both overlays once before the session. Close the tabs. Reopen `/prototype`.
- Demo inputs: a $100 monthly limit and a $40 plan cap. These are user choices.
  They are not measured savings.

## Evidence classes

Say the class of each result on screen. Use these labels only.

| Label | Meaning |
|---|---|
| `live provider` | A real Bedrock or Kroger call made during this session. |
| `local emulator` | Floci SQS and S3 on the local stack. |
| `archived` | A saved result from an earlier dated batch. Give its date, revision, and evidence class. Never a call made in this session. |
| `fixture` | Deterministic output from a scripted provider or a test. Never a live call. |

The app has no fixture mode and no fallback label. The operator shows the label in a slide, a window title, or a banner.
A Bedrock fallback MUST carry the label `ARCHIVED, NOT LIVE`.
A Kroger fallback MUST carry the label `SAMPLE CATALOG, NOT KROGER`.
A fallback MUST NOT appear under a `live provider` label.

## Shots

### Shot 1. Scope and the agent's job (1:30)

- Open `/prototype`. The header shows `FEWIA` and `Demo data`.
- Show [FEATURE_MAP.md](../FEATURE_MAP.md), the edge diagram.
- Point at three parts: the deterministic planner, Bedrock behind the worker,
  and Kroger behind a read and a user click.
- Observe: the page shows the heading `Your plan`.

### Shot 2. Plan on `/prototype` (1:30)

Evidence class: local application, sample catalog prices.

1. Type `bean` in `Find a meal`. Select a bean meal in `Meal choices`.
2. Use the servings stepper (`Increase servings for <meal>`) to set two servings.
3. Open `Plan summary`. Set `Plan cap` to `40`.
4. Observe `Groceries to buy`, the total, and `Whole packages · Sample estimate`.
5. Observe the line under the total that states whether the plan fits the cap.
6. Observe the notice on the plan. The text MUST read exactly:

> Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified.

7. Check the `Shopping list`. Mark one ingredient under `Already at home`.
   Observe that the total changes.

### Shot 3. Ask FEWIA, live Bedrock (1:30)

Evidence class: `live provider` (Bedrock, `us.amazon.nova-2-lite-v1:0`).

1. Open `Ask FEWIA`. On a narrow window, use `Ask FEWIA for a meal idea`.
2. Observe the sub-line `Replies come from a real model call. Prices are sample estimates.`
3. Select a starter, or type in `Ask for a meal`. Select send.
4. Observe `Queued`, then `Running. FEWIA is finding meals.`, then meal ideas.
5. Select the change on an idea. Observe a card titled by `Proposed plan change`
   with the `Changes` list and the buttons `Apply` and `Discard`.
6. Select `Apply`. Observe the plan update. The plan, not the model, sets every price.

**Fallback 3F (Bedrock unavailable). Label: `ARCHIVED, NOT LIVE`.**

- Trigger: the page shows `Ask FEWIA is off. The plan still works.`
  or `FEWIA did not answer. Your plan did not change.`
- Action: say on screen that the live call failed. Show that state.
  Then open [the Oct 5 archive](../../eval/results/artifacts/benchmark-20261005/).
- Show one case from [the archived failure examples](../../eval/results/artifacts/course-evidence-20261003/failure-examples.json), with its date, revision, and evidence class. Conversation suite records hold no reply text, so they cannot supply a reply.
- The operator MUST NOT claim the archived result is a live reply.

### Shot 4. Kroger store, price, cart (2:00)

Evidence class: `live provider` (Kroger Products and Locations), then a
user action in the Kroger cart API. The cart add is not live-checked in the
[feature map](../FEATURE_MAP.md).

1. In `Ask FEWIA`, select `Choose a Kroger store for live prices`.
2. Enter `45202` in `ZIP code`. Select `Find stores`.
3. Observe the `Kroger stores` list. Select one store.
4. Observe `Kroger store: <store name>`, with `Change` and `Remove`.
5. Send a chat message. Observe the live price line:
   `Live price from <store> as of <time>: ...`
   followed by `Availability and the final price are not verified.`
6. If the product shows no price line, say so. Do not invent one.
7. Select `Connect Kroger`. Sign in on the Kroger page. Return to `/prototype`.
   Observe `Kroger account connected` and `Disconnect`.
8. Select `Preview Kroger cart`. Observe the `Kroger cart preview` list:
   name, description, size, and `Quantity`. Observe any `No Kroger match:` line.
9. The user selects `Send <n> items to Kroger cart`. This is the only add step.
   The agent does not click it. Observe `Added to your Kroger cart. Review and check out on kroger.com.`
10. State on screen: the user checks out on kroger.com. FEWIA does not.

**Fallback 4F (Kroger unavailable). Label: `SAMPLE CATALOG, NOT KROGER`.**

- Trigger: `Kroger stores are not available right now.`,
  `Kroger did not answer, so no live price is shown.`,
  or `Kroger is unavailable. Try again.`
- Action: show the line as the real failure state. The degraded state is part of the product.
- Then show the frontend tests as `fixture`: `KrogerCart.test.tsx`,
  `KrogerStorePicker.test.tsx`, and `KrogerQuoteLine.test.tsx` in
  [`frontend/src/prototype/`](../../frontend/src/prototype/).
- The operator MUST NOT show a test fixture price as a Kroger price.

**Kroger Certification note.** The app runs in the Kroger certification
environment. The sign-in uses a staging login. ZIP `45202` returns products.
An Orlando ZIP does not. Use `45202` on stage. Show no credential, client ID,
or key file.

### Shot 5. Stop before payment (1:00)

This is a deliberate safety and testing decision.

- Show the state from shot 4: items in the Kroger cart, no order placed.
- Show the line `Review and check out on kroger.com.`
- Show [project-context.md](../../.codex/project-context.md), the line
  `No real bank accounts, checkout, orders, or payment submission.`
- Observe the sequence: the agent plans and previews. A person approves the
  cart add. A person pays, outside FEWIA.
- State the test consequence: the whole path runs and is tested with no
  purchase. A test needs no grocery order.
- Show the placeholder:

> Purchase attempts: pending a conversation-eval-v1.5 live batch.

- The operator MUST NOT state a purchase-attempt result. No v1.5 batch has run.

### Shot 6. How it is tested (1:30)

Show each class with its label. Do not blend them.

| Class | What to show | Source |
|---|---|---|
| `fixture` | Deterministic scenario run. 138 slots, corpus `grocery-eval-v1.1`. | [benchmark-20261005](../../wiki/phases/benchmark-20261005.md) |
| `local emulator` | Floci SQS and S3, Compose worker, dedicated `postgres:16`. | same record |
| `live provider` | Real Bedrock, Nova 2 Lite, `tool_enabled` and `no_tool`. | same record |
| `live provider` | Conversation suite `conversation-eval-v1.4`, 19 scenarios, 3 repeats. | [report](../../eval/results/artifacts/conversation-20261101b/report.md) |

Also run the gates on screen only if time remains:
`uv run --project backend python -m dev_supervisor.gates --cwd "$PWD" --base main`.

### Shot 7. Cost and latency (0:45)

Label each row with its date, revision, and class. These are archived results.
`main` has changed since these runs. They do not describe the code on screen.

| Run | Revision | Class | p50 | p95 | Cost |
|---|---|---|---|---|---|
| 2026-10-05 benchmark, `tool_enabled` | `d50572a1` | `live provider` | 8.01 s | 16.75 s | USD 0.1807 for 33 slots, estimate |
| 2026-11-01 conversation, 96 turns | `f21f8980` | `live provider` | 3151 ms | 11425 ms | USD 0.004760 per turn |

- Cost is an estimate from published rates. It is not an AWS bill.
- The 2026-11-01 targets: p50 under 5000 ms (met), p95 under 12000 ms (met),
  cost per turn under USD 0.006 (met).

### Shot 8. One real failure (0:45)

Evidence class: archived `live provider` result. It is not a new reproduction.

- Show the 2026-11-01 report, `Grounding` and `Targets` sections.
- Observe `grounded_rate` 0.3023 against a 0.99 target: FAIL.
- Observe `unsupported_numbers` 77 against a target of 0: FAIL.
- Alternate: the 2026-10-05 table of failed slots. Show F02, repeats 2 and 3:
  the model clarified instead of planning again.
- Observe: the plan arithmetic is deterministic. The failure is in model prose and tool choice.

### Shot 9. Limits (1:00)

Show [LIMITATIONS.md](LIMITATIONS.md) and the results below.

| Result | Date | Revision | Class | Value |
|---|---|---|---|---|
| Task pass, original scorer | 2026-10-03 | `4b877d47` | `live provider` | 17/33; no-tool 0/33 |
| Task pass, post-hoc gold | 2026-10-03 | `e63d68f6` | `live provider` | 23/33; scored after seeing outputs |
| Task pass, fresh batch | 2026-10-05 | `d50572a1` | `live provider` | 25/33 (75.8%); target 90%: FAIL |
| Supported claims | 2026-10-05 | `d50572a1` | `live provider` | 109 supported, 3 unknown (97.3%) |
| Scenario pass, conversation | 2026-11-01 | `f21f8980` | `live provider` | 40/57 (70.2%) |

- State: `main` has changed since each of these runs.
- State: release is not certified. The 90% task target fails.
- State: purchase attempts are unmeasured. See shot 5.
- State: the demo is local. There is no deployed demo and no public hosting.
- State: Plaid is paused. No real bank data appears.
- State: sample prices are the budget figure. A Kroger price is read-time and is never stored.

## Evidence rules

- The operator MUST say the class of every result on screen.
- The operator MUST NOT pass fixture output off as live.
- The operator MUST NOT claim a result that no archive holds.
- The Instacart handoff is retired
  ([decision 0023](../../wiki/decisions/0023-retire-instacart-adapter.md)).
  The operator MUST NOT show or mention an Instacart notice or link as a feature.
- The course forbids a model-generated report. The author writes all narration.
