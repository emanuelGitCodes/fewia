# Live demo rehearsal checklist

The owner presents FEWIA by Zoom on 2026-11-09. The limit is 15 minutes. The
professor requires that the demo works live. Every box below is unchecked. No
step has run live under this checklist. Check a box only after you watch the
state on screen.

Sources: [LOCAL_GROCERY_DEMO.md](../LOCAL_GROCERY_DEMO.md),
[infra/bedrock/README.md](../../infra/bedrock/README.md),
[compose.yaml](../../compose.yaml),
[compose.bedrock.yaml](../../compose.bedrock.yaml),
[compose.kroger.yaml](../../compose.kroger.yaml),
[decision 0026](../../wiki/decisions/0026-prototype-default-route.md).

## 1. Startup

Run every command from the repository root of the checkout that holds `.env`.
A new worktree has no `.env`.

- [ ] Docker Desktop runs. `docker info` prints server details.
- [ ] `.env` exists with mode `600`.
- [ ] `.env` sets `FEWIA_BEDROCK_MODEL_ID`, `FEWIA_BEDROCK_REGION`,
  `FEWIA_AWS_PROFILE`, and `FEWIA_BEDROCK_CREDENTIALS_FILE`.
- [ ] Set `FEWIA_KROGER_CLIENT_ID_FILE`, `FEWIA_KROGER_SECRET_FILE`, and
  `FEWIA_KROGER_TOKEN_KEY_FILE` in `.env` or in the shell. Each value MUST be
  an absolute path. `FEWIA_KROGER_ENVIRONMENT` defaults to `certification`.
  Leave it at the default.

Start the full stack with both overlays
(LOCAL_GROCERY_DEMO.md, "Both overlays together"):

```bash
docker compose --env-file .env -f compose.yaml -f compose.bedrock.yaml -f compose.kroger.yaml up -d
```

Confirm each service:

- [ ] `docker compose ps` lists `postgres`, `floci`, `api`, `worker`,
  `sync-worker`, and `web` as running.
- [ ] `postgres` and `api` report healthy. `floci` has no health flag in the
  Compose file, so check that it runs.
- [ ] `bootstrap` exited with code 0. It is not a failure.
- [ ] `http://127.0.0.1:5173/api/healthz` returns success through the web port.
- [ ] `http://127.0.0.1:5173/api/grocery/providers` shows Bedrock and Kroger
  as configured. This response is a configuration flag, not proof that a
  provider answers.
- [ ] `http://127.0.0.1:5173/prototype` opens. `/` redirects to `/prototype`
  (decision 0026). Do not open `/app` for the demo.
- [ ] The chat panel does not show "Ask FEWIA is off. The plan still works." That text means
  Bedrock is not configured.

Stop the stack only after the demo: `docker compose down`. Never add `-v`.

## 2. Credentials

Check existence and mode only. Never open, print, or screen-share these files.

| Variable | Needs | Mode |
| --- | --- | --- |
| `FEWIA_BEDROCK_CREDENTIALS_FILE` | The Bedrock session file from the host MFA helper | 600 |
| `FEWIA_KROGER_CLIENT_ID_FILE` | Kroger client ID file | 600 |
| `FEWIA_KROGER_SECRET_FILE` | Kroger client secret file | 600 |
| `FEWIA_KROGER_TOKEN_KEY_FILE` | Fernet key for stored customer tokens | 600 |

- [ ] Each file exists and has mode `600`: `test -f <path>` and
  `stat -f %Lp <path>`.
- [ ] The Kroger Certification app lists
  `http://localhost:8010/grocery/kroger/callback` as a redirect URI.
- [ ] The owner has a Kroger staging shopper account. The developer portal
  account does not work on the staging login.

The Bedrock session lasts at most one hour
(`infra/bedrock/README.md`, "Temporary role credentials"). The helper
`infra/bedrock_session.py` sets `DURATION_SECONDS = 3600`. It prints the expiry
time when it finishes.

- [ ] Refresh the Bedrock session shortly before the presentation. Target: 10
  to 20 minutes before the start. A session from the rehearsal will expire.
- [ ] Run the host MFA helper `infra/bedrock_session.py` with `--role-arn` and
  `--mfa-serial`. It asks for an MFA code. Do it away from the screen share.
- [ ] Recreate `api` and `worker` after each renewal. A running process keeps
  the old credentials. The documented command names the project
  `fewia-grocery-b7d4`. Use your own project name if it differs:

```bash
docker compose -p fewia-grocery-b7d4 --env-file .env -f compose.yaml -f compose.bedrock.yaml \
  up -d --no-deps --force-recreate api worker
docker exec fewia-grocery-b7d4-web-1 nginx -s reload
```

- [ ] If you run Kroger too, add `-f compose.kroger.yaml` to the recreate
  command. Without it, Compose drops the Kroger overlay from `api` and
  `worker`.
- [ ] Note the expiry time. Write it here: __________. The session MUST outlast
  the 15-minute slot.

## 3. The full path

Run these steps in order. Use short, plain prompts. Time each step.

| # | Step | Expected observable state | Pass | Fail |
| --- | --- | --- | --- | --- |
| 1 | Open `/prototype`. | The prototype page loads. No "Ask FEWIA is off. The plan still works." text. | [ ] | [ ] |
| 2 | Chat: ask for one to three meals, for example bean tacos for two. | The panel shows "Your request is in progress." Then a reply arrives with the meals. | [ ] | [ ] |
| 3 | Plan: confirm the meals and servings in the plan. | The plan lists 1-3 meals with 1-8 servings each. Meals come from the 40-meal catalog. | [ ] | [ ] |
| 4 | Budget: set the monthly limit and the plan cap. | The form starts at USD 100 per month and a USD 40 cap. The source is `manual`. | [ ] | [ ] |
| 5 | Estimate: read the estimate. | A total from the sample catalog shows. The notice reads "Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified." | [ ] | [ ] |
| 6 | Kroger sign-in: select "Connect Kroger". | The browser goes to the Kroger Certification staging login (`login-stage.kroger.com`). The owner signs in as the staging shopper. Keep the password off the shared screen. | [ ] | [ ] |
| 7 | Return from sign-in. | The browser lands on `/prototype`. "Kroger account connected" shows with a "Disconnect" button. The plan is still present. | [ ] | [ ] |
| 8 | Store selection: open the store picker, enter ZIP `45202`, select "Find stores". | A list of Kroger stores shows. The owner selects one. "No Kroger stores found near that ZIP code." is a failure. Orlando returns no products in Certification, so use `45202`. | [ ] | [ ] |
| 9 | Live price: ask the chat to swap in or look up a food that has no sample price. | The reply carries one live Kroger price for the chosen store. Plan totals still use sample catalog cents only. | [ ] | [ ] |
| 10 | Cart preview: select "Preview Kroger cart". | A list titled "Kroger cart preview" shows items with name, size, and quantity. Foods with no match appear under "No Kroger match:". | [ ] | [ ] |
| 11 | User-clicked cart add: the owner clicks "Send N items to Kroger cart". | The status line reads "Added to your Kroger cart. Review and check out on kroger.com." The product places no order and takes no payment. | [ ] | [ ] |

Notes for the path:

- Steps 9 to 11 call Kroger. Each call spends part of the 10,000-call daily
  limit. Do not loop them.
- Step 11 changes a real staging cart. Expect one item set per click. The
  "Retry" button appears only after "Kroger did not confirm." Check the Kroger
  cart before you retry.
- The application stores no Kroger content. Sign-in stores only encrypted
  tokens.
- Before the dry run, confirm the exact wording of steps 2 to 5 on the
  `/prototype` screen. This checklist took the budget and notice text from
  LOCAL_GROCERY_DEMO.md, which describes the older `/app` page.

## 4. Failure drills

Rehearse each drill once. Say aloud what failed. Never describe fixture or
archived output as live. A fallback MUST carry a visible on-screen label such
as `ARCHIVED, NOT LIVE` or `SAMPLE CATALOG, NOT KROGER`.

| Drill | Visible state | Owner action and fallback |
| --- | --- | --- |
| Bedrock down | Chat shows "The chat request failed. Retry checks the same request." or no reply after the timeout. | Select Retry once. If it fails again, say that Bedrock fails. Continue with the sample-catalog estimate, which needs no model. Show the archived chat evidence from [DEMO_SCRIPT.md](DEMO_SCRIPT.md) with the label `ARCHIVED, NOT LIVE`. |
| Session expired | Chat fails as above, or the panel shows "Ask FEWIA is off. The plan still works." after a restart. | Leave the Zoom window. Run the host MFA helper, then recreate `api` and `worker` (section 2). Return and retry. If this takes more than 2 minutes, switch to the archived fallback above. |
| Kroger Certification fails | The store list is empty, the preview shows "Kroger is unavailable. Try again." or the sign-in shows "Kroger sign-in did not finish. Try again." | Retry once. Check ZIP `45202`. If the status reads "Your Kroger sign-in expired. Disconnect, then connect Kroger again.", select Disconnect, then connect again. If Kroger still fails, say so. Do not show Kroger data from memory or a screenshot as live. Keep the estimate on screen with the label `SAMPLE CATALOG, NOT KROGER`. |
| Stack slow | A spinner or "Your request is in progress." lasts more than 20 seconds. | Do not click again. Bedrock p50 was 3.4 s and p95 was 12.2 s per turn in the 2026-10-30 batch (docs/EVALUATION.md). Wait up to 30 seconds. Fill the time by explaining the budget logic. If no reply, run the Bedrock drill. |
| Cart add unconfirmed | "Kroger did not confirm. Check your Kroger cart before you retry." | Do not click Retry at once. Open the staging cart and check it. Then decide. |

- [ ] Each drill ran once in rehearsal.
- [ ] The fallback labels are ready to show: slide, window title, or banner.

## 5. Zoom

- [ ] Share one browser window, not the whole desktop. Do not share the
  terminal.
- [ ] Set the window to about 1280 by 720. Zoom the page so the text reads at
  that size.
- [ ] Close the editor, the terminal, and any `.env` or credential file view.
- [ ] Close the password manager, the AWS console, and the Kroger developer
  portal. The portal shows the client ID.
- [ ] Close mail, chat, and notification apps. Turn on Do Not Disturb.
- [ ] Clear browser autofill suggestions that show the shopper email.
- [ ] Keep the shell history closed. Commands name credential file paths.
- [ ] Join Zoom 10 minutes early. Test the share and the audio.
- [ ] Keep a second browser tab ready on the fallback evidence. Do not share it
  until you need it.
- [ ] Charge the laptop. Connect it to power and a wired network if possible.

Timed dry run. Total budget 15:00. Aim for 12:00 and keep 3:00 slack.

| Block | Target | Actual |
| --- | --- | --- |
| Intro and scope | 1:00 | |
| Steps 1-3 chat and plan | 2:30 | |
| Steps 4-5 budget and estimate | 1:30 | |
| Steps 6-7 Kroger sign-in | 2:00 | |
| Step 8-9 store and live price | 2:00 | |
| Steps 10-11 preview and cart add | 1:30 | |
| Close and limits | 1:30 | |

- [ ] Run the dry run with a timer. Stop at 15:00. Cut a block if you run over.
- [ ] Run it twice. The second run MUST fit in 15:00 with one drill included.

## 6. Rehearsal record

Record real observations only. Write `pass`, `fail`, or `skipped` per step.

| Date | Commit SHA | Steps 1-5 | Steps 6-7 | Steps 8-9 | Steps 10-11 | Elapsed | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |
| | | | | | | | |
| | | | | | | | |

## 7. Owner decisions

These questions are open. This checklist does not answer them.

1. Kroger's terms restrict distributing or publicly displaying API content to
   third parties (section 5e). Does the narrated video show Kroger product
   data? Where will the video be hosted?
2. Kroger's terms forbid credentials, client IDs included, in an open source
   repository (section 4b). Has the owner confirmed that the repository holds
   none before the graders open it?

A live Zoom share of Kroger data to the class is a related question. The
owner decides it with the same terms in view.
