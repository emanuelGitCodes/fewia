# Tonight meal concepts

The audience is adults aged 18 to 25. The user wants to pick a meal for
tonight and see its cost and nutrition facts. These images explore that
screen. They do not implement a new application flow.

The first screen shows a meal, servings, groceries to buy, and nutrition
per serving. Pantry ingredients affect the grocery estimate. Price labels
state that the estimate uses sample prices and whole packages.

## Shared demonstration

All concepts use bean tacos for two servings. Oil, salt, and cumin are
already at home. The remaining sample packages total $8.06: black beans
$1.29, onion $1.29, salsa $2.49, and corn tortillas $2.99.

Illustrative nutrition per serving is 379 kcal, 14.5 g protein, 55.8 g
carbohydrate, and 13.7 g fat. These figures come from the saved mobile
estimate in `wiki/artifacts/backlog-resume-20261003/browser/mobile-estimate.png`.
They are design examples, not a fresh provider response. The first action
is to view the shopping list. The screen offers another meal choice.

## Direction study

Impeccable seed `79386d0c` assigned candidate five. The ranked candidates
cover campus food, print, sport, music, retail, travel, and shared cooking.

1. Shared Table: campus cafe menus. Tomato red, cream, rounded grotesque
   type, and an appetizing meal photograph make dinner feel approachable.
2. Study Break: library notices. White, yellow, and charcoal support quiet
   labels and a compact nutrition table.
3. Rec Club: recreational sports graphics. Blue, cream, and citrus give
   meal selection energy while numeric columns retain clarity.
4. Record Shop: independent record sleeves. Lilac, ink, and orange support
   photo browsing and compact meal details.
5. Corner Market: neighborhood grocery graphics. Cobalt, lime, and ivory
   make the grocery price prominent beside a direct nutrition summary.
6. Day Pass: city travel graphics. Teal and vermilion support clear labels
   and a compact meal-to-shopping path.
7. Potluck: shared cooking invitations. Terracotta and pale pink support
   warm photography and simple ingredient groups.

Corner Market is the lead. Shared Table is the preferred grounded alternate.
Pantry Edit adapts the design annual challenger into a calm meal screen.
The familiar category direction remains available as a fourth comparison.

## Challenger judgments

These judgments compare audience identification and task clarity.
They are design hypotheses, not findings from user research.

- Split-flap board: declined on both axes. Keep stable numeric alignment.
- Design annual: competitive on clarity. Show it as Pantry Edit.
- Star atlas: declined on both axes. Keep explicit information hierarchy.
- Character catalog: declined on clarity and broad audience fit. Keep a
  finite meal selection.
- Factory Records: declined on both axes. Keep disciplined color use.
- Botanical folio: declined on both axes. Keep comparable serving details.

## Boundaries

The mock images contain illustrative food photography. The user selected
a combination of Familiar and Pantry Edit. The revised screen awaits user
feedback. The application and data contracts remain unchanged.

Prototype checks cover desktop and mobile layout, keyboard access, serving
labels, cost meaning, and nutrition units. FEWIA gates and independent
review apply to any later implementation.

## Review files

- [Familiar and Pantry Edit combination](tonight-mocks/familiar-pantry.png)
- [Corner Market](tonight-mocks/corner-market.png)
- [Shared Table](tonight-mocks/shared-table.png)
- [Pantry Edit](tonight-mocks/pantry-edit.png)
- [Familiar recipe app](tonight-mocks/familiar.png)
- [Exact generation prompts](tonight-mock-prompts.md)

The images are static concepts. Some generated food photos include garnish
outside the priced recipe. Corner Market uses illustrative alternative meal
names. A production version MUST use catalog names and matching food assets.
Pantry Edit repeats navigation and pantry text. A prototype SHOULD remove
that repetition unless usability checks show a need for both controls.
Fine-print contrast and touch targets need browser verification.

The comparison-page writer returned `no_edits`. The images were presented
inline. No comparison page or application code was created.

## Selected combination

The revised mock keeps Familiar's forest-green palette, pale-green
selection, food photography, and standard controls. Pantry Edit supplies
clean type, fine separators, and the compact photo-and-facts layout.
One bottom navigation area replaces the duplicated navigation. The pantry
field lists its ingredients once. A single nutrition row replaces nested
panels. The sample price, serving count, and nutrition values stay the same.

This selection does not approve application implementation. The revised
image is a static design artifact. Browser checks remain open.
