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

## Try the flow

1. Choose bean tacos, egg fried rice, or chickpea curry.
2. Adjust the serving count from one to eight.
3. Mark ingredients in Pantry, then return to Tonight.
4. Read the grocery estimate and nutrition per serving.
5. Open the shopping list and check items as needed.
6. Set a plan cap in Budget and read whether the meal fits.

State resets when the page reloads. Checking a shopping item does not
change the grocery total. Changing a meal, servings, or pantry clears
the checklist so old checks cannot apply to a different list.

## Data boundaries

Package sizes, ingredient quantities, and prices mirror the repository's
sample catalog for these three recipes. All arithmetic uses integer cents.
The estimate covers whole packages still needed. It is not cost per serving
or a verified retailer quote. Pantry ingredients remain in nutrition.

Nutrition values per serving mirror the USDA values that
`backend/app/services/meal_nutrition.py` computes for the same recipes.
The real app shows the same values. They are static copies, not a fresh
USDA response or verified cooking results. The photos are generated
illustrations. No purchases or reservations occur.

The initial taco example has two servings and a $40 plan cap. Olive oil,
salt, and ground cumin start in the pantry. Remaining packages cost $8.06.
Four servings require a second bean package and cost $9.35.

## Files

- `frontend/src/prototype/` contains the UI, fixtures, calculations, and tests.
- `frontend/public/prototype/` contains the generated food images and provenance.
- [Approved direction and scope](tonight-prototype-plan.md)
- [Image generation prompts](tonight-asset-prompts.md)
- [Phase record](../../wiki/phases/tonight-prototype.md)
- [WCAG 2.2 AA audit](tonight-wcag-audit.md)
- [VoiceOver audit](tonight-voiceover-audit.md)

## Verification scope

Frontend gates cover lint, unit and interaction tests, and the production
build. Browser checks cover the demo route and its controls. Live backend,
provider behavior, production hosting, and cross-browser coverage are outside
this prototype's verification scope. Browser and VoiceOver testing remain
paused. The phase record links the existing audits.
