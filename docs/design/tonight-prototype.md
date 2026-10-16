# Run the Tonight prototype

The prototype implements the user-selected Familiar and Pantry Edit design.
It uses local demo data and does not call the FEWIA backend.

From the repository root:

```bash
cd frontend
npm ci
npm run dev -- --port 5317 --strictPort
```

Open `http://127.0.0.1:5317/prototype`.
The existing application stays at `/` and still needs its backend.
The Compose web image also serves the prototype at
`http://127.0.0.1:5173/prototype`.

## Try the flow

1. Add up to three meals with the picker. Type in "Find a meal" to filter it.
2. Set each meal's servings from one to eight on its card.
3. Open a card's Ingredients and mark items already at home. The Pantry
   view changes the same list.
4. Set the plan cap in the summary and read the amount left or over.
5. Read the plan nutrition total and each card's per-serving values.
6. Check items on the combined shopping list. Each item names the meals
   that use it.

State resets when the page reloads. Checking a shopping item does not
change the grocery total. A check stays while its item needs the same
package count. A change that alters that count drops the check.

## Data boundaries

Package sizes, ingredient quantities, and prices mirror the repository's
sample catalog for these three recipes. All arithmetic uses integer cents.
The estimate covers whole packages still needed. It is not cost per serving
or a verified retailer quote. Pantry ingredients remain in nutrition.

Nutrition values per serving mirror the USDA values that
`backend/app/services/meal_nutrition.py` computes for the same recipes.
They are static copies, not a fresh USDA response or verified cooking
results. The photos are generated illustrations. No purchases or
reservations occur.

The initial plan is bean tacos with two servings and a $40 plan cap. Olive
oil, salt, and ground cumin start in the pantry. Remaining packages cost
$8.06. Four servings require a second bean package and cost $9.35.

The plan sums each ingredient across its meals before it rounds to whole
packages. Egg fried rice and chickpea curry at two servings each cost
$17.91 together. Priced one meal at a time, they cost $22.08.

## Files

- `frontend/src/prototype/` contains the UI, fixtures, calculations, and tests.
- `frontend/public/prototype/` contains the generated food images and provenance.
- [Design system](tonight-design.md)
- [Approved direction and scope](tonight-prototype-plan.md)
- [Image generation prompts](tonight-asset-prompts.md)
- [Phase record](../../wiki/phases/tonight-prototype.md)
- [WCAG 2.2 AA audit](tonight-wcag-audit.md)
- [VoiceOver audit](tonight-voiceover-audit.md)

## Verification scope

Frontend gates cover lint, unit and interaction tests, and the production
build. Browser checks cover the demo route and its controls. Live backend,
provider behavior, production hosting, and cross-browser coverage are outside
this prototype's verification scope. No VoiceOver run covers the Plan page.
The phase record links the existing audits and the Plan page browser checks.
