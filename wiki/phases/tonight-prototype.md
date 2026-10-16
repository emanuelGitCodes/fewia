# Tonight prototype

This page indexes the approved local prototype on
`codex/impeccable-young-adult-mocks`. The recorded baseline is `b30858e`.
The Plan page stack `claude/tonight-plan-page-01` to `-06` builds on that
branch. The stack `claude/tonight-to-main-01` to `-05` brings the branch
into `main`. The [Main stack](#main-stack) section records it. The existing
`/` application, providers, retailer data, and deployment stay outside this
record.

## Audience and task

The audience is adults aged 18 to 25.
The task is to plan one to three meals on one page.
The page shows each meal with its servings, the grocery total against the
plan cap, the plan nutrition, and one combined shopping list.

## Approved direction

The user selected Familiar plus Pantry Edit.
Familiar supplies forest-green controls and pale-sage selection.
Pantry Edit supplies type, separators, and the compact photo-and-facts layout.
One navigation area serves Plan and Pantry. It sits at the bottom on every
screen width.

The [direction plan](../../docs/design/tonight-prototype-plan.md) states the
contract. The [mock brief](../../docs/design/tonight-mock-brief.md) records
the static concepts. The [prototype design system](../../docs/design/tonight-design.md)
holds the prototype tokens. The root `DESIGN.md` describes the `/` application.
[PRODUCT.md](../../PRODUCT.md) names the 18 to 25 audience and `/prototype`.

## Route and local run

The prototype uses local demo data.
Open `http://127.0.0.1:5317/prototype`. The existing application stays at `/`.

From the repository root:

```bash
cd frontend
npm ci
npm run dev -- --port 5317 --strictPort
```

The [run guide](../../docs/design/tonight-prototype.md) describes the flow.

## Demo meals and limits

The demo offers bean tacos, egg fried rice, and chickpea curry.
A plan holds 1 to 3 meals. The picker adds or removes a meal, and a name
filter narrows the picker. Each meal accepts 1 to 8 servings.
A value outside that range shows `Each meal uses 1 to 8 servings.` inside
that meal's card.

The plan sums each ingredient across the meals, then rounds to whole
packages once. A shared package is bought once.

| Plan | Total |
| --- | --- |
| Tacos, 2 servings | $8.06 |
| Tacos 2 and egg fried rice 2 | $18.41 |
| Egg fried rice 2 and chickpea curry 2 | $17.91 (priced apart: $22.08) |
| All three meals, 2 servings each | $24.68 |

The initial plan is tacos at 2 servings with a $40 plan cap.
Olive oil, salt, and ground cumin start in the pantry.
Four taco servings need a second bean package. That plan costs $9.35.

The pantry is one list per ingredient. A meal card's "Already at home"
checkbox and the Pantry view change the same list. An item at home leaves
the shopping list and stays in the nutrition.

A shopping check stays while its line still needs the same package count.
A meal, serving, or pantry change drops only the checks it invalidates.
Shopping checks leave the grocery total unchanged.
State resets when the page reloads.

The plan cap keeps the last valid budget while the draft is invalid.
The summary shows the amount left under the cap or the amount over it.

Grocery cost uses whole packages in integer cents.
Each card shows nutrition per serving. The summary shows the plan total:
each per-serving value times the servings, summed over the meals.
Nutrition values are static copies of the USDA per-serving values that
`backend/app/services/meal_nutrition.py` computes.

On phones, a pinned bar shows the total and the fit line while the page
scrolls. From 720 px, the meals sit in the left column, and the summary
and the shopping list sit in a sticky right column.
One hidden atomic status is the only `role="status"` region on the Plan page.
When the name filter hides every meal, the status text starts with
"No meals match.".
The serving error and the plan cap error use `role="alert"`.
Every estimate shows this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Source map

| Path | Role |
| --- | --- |
| `frontend/src/main.tsx` | Renders `selectRoot(window.location.pathname)`. |
| `frontend/src/rootView.tsx` | Loads `TonightPrototype` lazily on `/prototype`. |
| `frontend/src/prototype/prototypeData.ts` | Demo catalog, recipes, notices, serving bounds, and `MAX_MEALS`. |
| `frontend/src/prototype/planModel.ts` | Plan state, combined lines, cost, nutrition, budget gap, and check retention. |
| `frontend/src/prototype/prototypeModel.ts` | Shared helpers: `packageCount`, `withBudgetInput`, and `formatMacro`. |
| `frontend/src/prototype/TonightPrototype.tsx` | Local state, view shell, and view-change focus. |
| `frontend/src/prototype/PrototypePanels.tsx` | Plan page, Pantry view, pinned bar, and navigation. |
| `frontend/src/prototype/PlanMeals.tsx` | Meal picker, name filter, and meal cards with ingredients. |
| `frontend/src/prototype/PlanSummary.tsx` | Plan summary and the combined shopping list. |
| `frontend/src/prototype/tonight.css` | Prototype styles. |
| `frontend/src/money.ts` | Dollar parse and format in integer cents. |
| `frontend/src/prototype/planModel.test.ts` | Plan arithmetic, retention, and validation. |
| `frontend/src/prototype/prototypeModel.test.ts` | Shared helper behavior. |
| `frontend/src/prototype/TonightPrototype.test.tsx` | Interaction and accessibility behavior. |
| `frontend/public/prototype/` | Generated meal images and adjacent prompt JSON. |

## Plan page stack

Each item stacks on the item before it. Item 01 stacks on
`codex/impeccable-young-adult-mocks` at `07aec4f`. A Sonnet writer made each
code item through `dev_supervisor`, and the Opus review approved its head.

| Item | Head | Work | Gate lines | Review |
| --- | --- | --- | --- | --- |
| 01 | `779cc4a` | Multi-meal plan model | 217 | APPROVE, round 1 |
| 02 | `b0dcd44` | Plan page with meal picker and meal cards | 249 | APPROVE, round 1 |
| 03 | `b322530` | Summary and combined shopping list | 190 | APPROVE, round 1 |
| 04 | `141ff8d` | Ingredient "Already at home" toggles and cleanup | 84 | APPROVE, round 1 |
| 05 | `11ff7d5` | Pinned bar, two columns, and name filter | 163 | APPROVE, round 3 |

The frontend suite grew from 521 to 561 tests.
The [Main stack](#main-stack) fixes the two open items of this stack: the
unannounced empty filter result (4.1.3) and the phone scroll padding at
320 px with 200% text (2.4.11). No screen-reader run covers the Plan page.

## Main stack

The stack brings `codex/impeccable-young-adult-mocks` at `f81188d` into
`main`. Item 01 stacks on `main` at `43c46a7`, and each item stacks on the
item before it. Each item copies its files from `f81188d` in its first
commit. Fixes follow in later commits. A Sonnet writer made each code fix
through `dev_supervisor`, and the Opus review approved each code head.

| Item | Code head | Work | Gate lines | Review |
| --- | --- | --- | --- | --- |
| 01 | `cc6fc30` | Plan model and sample data | 366 | APPROVE, round 1 |
| 02 | `f7a2fa4` | Styles and meal photos; drop `.tonight-primary`; pinned scroll padding variable | 704 | APPROVE, round 1 |
| 03 | `f4fbc59` | Plan page UI and `/prototype` route; empty filter status; pinned bar measure; nginx route | 596 | APPROVE, round 2 |
| 04 | — | Design docs, audits, evidence, this phase page, and `PRODUCT.md` | 869 | prose |
| 05 | — | Wiki log, index, and graph artifact | 166 | prose |

The styles come before the UI, because `TonightPrototype.tsx` imports
`tonight.css` and the two together exceed 1000 lines. The repository
counter counts `.json` files, so `results.json` and the graph artifact
count as code lines.

`main` already holds a root `DESIGN.md` for the `/` application. The
prototype design system is `docs/design/tonight-design.md`.

The `frontend/public/prototype/` folder made the Compose nginx answer
`/prototype` with a redirect to the container port and `/prototype/` with
`403`. Item 03 rewrites both paths to `index.html`. The Playwright suite
passed 16 of 16 on the item 03 head against the Compose stack.

## Image and prompt provenance

The built-in image tool created the three meal photos.
WebP files live in `frontend/public/prototype/` with adjacent `.webp.json`
prompt files. The [asset prompt record](../../docs/design/tonight-asset-prompts.md)
reproduces the generation text. The photos are generated illustrations.

## Chronological implementation commits

These SHAs come from the Tonight entries in [log.md](../log.md).

| SHA | Work |
| --- | --- |
| `20da5d8` | Demo data and grocery calculations. |
| `a018a0c` | Route, components, and styles. |
| `519b49b`, `6c34842` | Layout, focus, and mobile navigation repairs. |
| `741c491` | WCAG repairs and meal-photo sizing repair. |
| `22d3560` | One atomic meal, servings, cost, and estimate status. |
| `f20eef9` | Clear a transient serving error on a real view change. |
| `b30858e` | Recorded baseline for this index. |

The independent review for `b30858e` is `APPROVE`. Its gates `PASS`.
The [Main stack](#main-stack) publishes the branch to `main`.

## WCAG record and photo repair

The [WCAG 2.2 AA audit](../../docs/design/tonight-wcag-audit.md) evaluates
55 Level A and AA criteria. The recorded counts are 36 checked, 18 N/A,
and one partial. The partial criterion is 4.1.3 Status Messages.

Commit `741c491` repairs pantry label names, input-border contrast,
non-color selection cues, and 200% text clipping.
A layout repair exposed a photo-sizing overlap. Visual inspection caught it.
The photo stays in its grid column in the repaired source.

The 46 axe scans belong to revision `741c491` only.
The WCAG record makes no complete conformance claim.

## VoiceOver record

The [VoiceOver audit](../../docs/design/tonight-voiceover-audit.md) records
15/15 focused UI tests. Commits `22d3560` and `f20eef9` repair the two
screen-reader findings.

On the last edge sequence, a heading return succeeded once.
Authentication then interrupted the repeat of that sequence.
VoiceOver was stopped. Scripting permission reset is unconfirmed.
No VoiceOver run covers the Plan page. Browser checks of the Plan page
are in [Scope and remaining checks](#scope-and-remaining-checks).

## Scope and remaining checks

The prototype route uses local demo data in the React app.
The prototype route MUST NOT call Bedrock, Plaid, Instacart, PostgreSQL, SQS, or S3.
Provider credentials MUST NOT appear in frontend source.

No VoiceOver run covers the Plan page. The coordinator checked the Plan
page layout and focus in a browser at 375 px and 1200 x 850. In the main
stack, a Playwright script checked the pinned bar at 320 px with 200% text:
the scroll padding follows the 177 px bar, and no focused control is fully
hidden. At that size, the "Remove" button text wraps one letter per line.
This page records existing audits. The coordinator owns graph refresh,
`wiki/log.md`, and any evidence snapshot. The graph snapshot
`wiki/artifacts/tonight-prototype-graph-20261016.json` predates the main
stack, so its testing status is out of date.
