# Tonight prototype

## Approved direction

The user approved the combined Familiar and Pantry Edit direction for a
working prototype on `codex/impeccable-young-adult-mocks`.
The user selected self-contained demo data. No backend connection is part
of this prototype. The existing application remains available at `/`.
The prototype opens at `/prototype`.

## Direction contract

Audience: adults aged 18 to 25 choosing dinner and checking grocery cost
and nutrition. Mode: operate. Build path: code-led.
Impeccable direction seed: `79386d0c`; user-selected combination overrides
the original assigned direction.
Reference: `docs/design/tonight-mocks/familiar-pantry.png`.

THESIS: choose dinner and read its grocery cost and nutrition together.
The screen replaces the existing long stack of planning controls with one
meal decision followed by its facts.

STORY: choose a meal, adjust servings, declare pantry ingredients, read
the grocery estimate, and open the shopping list.

FIRST VIEWPORT: a compact FEWIA header; three photo meal choices; a selected
meal photo beside servings, grocery cost, and pantry context; a nutrition
row; a shopping-list action; one bottom navigation area.

OWN-WORLD: white surfaces, forest-green controls, pale-sage selection,
clean grotesque type, fine separators, and warm food photography.

SIGNATURE INTERACTION: changing the selected meal replaces its image and
facts together. The price reflects whole packages and declared pantry items.
The selected outline and a short image fade provide feedback. Reduced-motion
preferences suppress the fade.

LAYOUT: retain the compact reference on mobile. Use the same meal-and-facts
composition with a bounded content width on desktop. Keep nutrition readable
and navigation out of the content. No duplicated top and bottom navigation.

CONTENT: bean tacos, egg fried rice, and chickpea curry. Prices use the
repository sample catalog. Nutrition uses explicit illustrative fixtures.
Grocery cost is the price of whole packages still needed, not cost per serving.

STATE: support servings 1–8, explicit pantry toggles, a shopping checklist,
manual budget editing, over-budget feedback, all-items-at-home state, and
clear validation errors. Pantry changes do not remove food from nutrition.

FORM: Familiar supplies palette and controls. Pantry Edit supplies type
and layout. This user-selected combination replaces grounded candidate
five from seed `79386d0c`.

FINISH: unreviewed and undocumented is unfinished; this build ends with
the finish review, the verdict, DESIGN.md, and every shipping raster
carrying its provenance.

## Implementation

One Tier M junior owns the prototype, model, fixtures, styles, tests, and
route entry. The coordinator owns generated food assets and design records.
A Luna junior runs Grok 4.6 at medium. Luna at xhigh records the final
design tokens. A separate Sol review checks the completed revision so
the reviewer differs from both writers. No provider or infrastructure
changes are needed.

The source is split into two local commits: data/calculation with model
tests, then interface/route/styles with interaction tests. A future
publication needs a two-PR stack in that order to meet the per-PR size cap.
The current request does not include publication. Final gates still run
against main and report the aggregate line count.

## Verification

Run frontend lint, tests, and production build through FEWIA gates.
Exercise meal changes, serving limits, package boundaries, pantry edits,
shopping-list checks, budget validation, and reduced motion.
Inspect 390px mobile, 1440px desktop, and the visible browser width.
Use two bounded visual inspection rounds, with one batch of fixes between.
The Browser plugin is absent. Use Playwright for browser verification.

The user approved this build. The next user decision is feedback on the
working prototype. Publication and backend integration remain outside scope.
