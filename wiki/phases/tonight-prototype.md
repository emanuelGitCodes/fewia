# Tonight prototype

This page indexes the approved local prototype on
`codex/impeccable-young-adult-mocks`. The recorded baseline is `b30858e`.
The existing `/` application, providers, retailer data, and deployment stay
outside this record.

## Audience and task

The audience is adults aged 18 to 25.
The first task is to choose a meal for tonight.
The screen shows grocery cost and nutrition beside that meal.

## Approved direction

The user selected Familiar plus Pantry Edit.
Familiar supplies forest-green controls and pale-sage selection.
Pantry Edit supplies type, separators, and the compact photo-and-facts layout.
One bottom navigation area serves Tonight, Pantry, and Budget.

The [direction plan](../../docs/design/tonight-prototype-plan.md) states the
contract. The [mock brief](../../docs/design/tonight-mock-brief.md) records
the static concepts. [DESIGN.md](../../DESIGN.md) holds the prototype tokens.
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
Each meal accepts 1 to 8 servings.
A value outside that range shows: `Each meal uses 1 to 8 servings.`

The plan cap keeps the last valid budget while the draft is invalid.
The initial taco example uses 2 servings and a $40 plan cap.
Olive oil, salt, and ground cumin start in the pantry.
Remaining packages cost $8.06.
Four servings need a second bean package. That plan costs $9.35.

A meal, serving, or pantry change clears the shopping checklist.
Shopping checks leave the grocery total unchanged.
State resets when the page reloads.

Grocery cost uses whole packages in integer cents.
Nutrition stays per serving. Servings and pantry leave nutrition unchanged.
Nutrition values are static copies of the USDA per-serving values that
`backend/app/services/meal_nutrition.py` computes.
Every estimate shows this notice:

> Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.

## Source map

| Path | Role |
| --- | --- |
| `frontend/src/main.tsx` | Loads `TonightPrototype` lazily on `/prototype`. |
| `frontend/src/prototype/prototypeData.ts` | Demo catalog, recipes, notices, and serving bounds. |
| `frontend/src/prototype/prototypeModel.ts` | Servings, pantry, whole-package cost, and budget draft. |
| `frontend/src/prototype/TonightPrototype.tsx` | Local state, view shell, and view-change focus. |
| `frontend/src/prototype/PrototypePanels.tsx` | Tonight, Pantry, Shopping list, Budget, and navigation. |
| `frontend/src/prototype/tonight.css` | Prototype styles. |
| `frontend/src/money.ts` | Dollar parse and format in integer cents. |
| `frontend/src/prototype/prototypeModel.test.ts` | Model arithmetic and validation. |
| `frontend/src/prototype/TonightPrototype.test.tsx` | Interaction and accessibility behavior. |
| `frontend/public/prototype/` | Generated meal images and adjacent prompt JSON. |

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
A future publication still needs the planned two-PR stack.
No pull request, push, merge, or deploy is part of this record.

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
Browser and VoiceOver testing remain paused.

## Scope and remaining checks

The prototype route uses local demo data in the React app.
The prototype route MUST NOT call Bedrock, Plaid, Instacart, PostgreSQL, SQS, or S3.
Provider credentials MUST NOT appear in frontend source.

Browser and VoiceOver testing remain paused. This page records existing
audits. The coordinator owns graph refresh, `wiki/log.md`, and any
evidence snapshot.
