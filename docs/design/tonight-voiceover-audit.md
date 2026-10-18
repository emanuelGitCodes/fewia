# Tonight prototype VoiceOver audit

Date: 2026-10-16. Scope: `/prototype` on
`codex/impeccable-young-adult-mocks`. Baseline: `4537776`.
Environment: macOS 27.0.1, VoiceOver, and Chrome 155.0.8059.84.

This audit found two screen-reader issues. Commits `22d3560` and `f20eef9`
repair them. The record covers the observed flows and does not claim full
WCAG conformance or support across every browser and assistive technology.

## Method

The user approved temporary VoiceOver AppleScript control. Tests used
VoiceOver's own cursor movement, activation, heading, and landmark commands.
The evidence below comes from VoiceOver's `content of last phrase` property.
It is actual screen-reader output, not a browser accessibility-tree transcript.
Audio pronunciation and speech quality were not assessed.

A separate Chrome tab used demo data. Native browser controls initially
caused focus handoffs to a system control. The direct Chrome connection later
supplied budget input and prepared edge states without that handoff.
VoiceOver then supplied the spoken results. No provider or backend was used.

## Findings and repairs

| Finding | Evidence | Repair |
| --- | --- | --- |
| Competing, incomplete meal updates | Selecting rice spoke `selected`, then only `$11.64`. Reducing tacos from four to three servings changed $9.35 to $8.06, but VoiceOver spoke only `3 servings`. | One stable, polite, atomic status contains the meal, servings, grocery cost, and estimate qualifier. Visible serving and price text no longer have separate live roles. |
| Old serving error interrupts navigation | After an upper-limit error, returning from Pantry focused the Tonight heading but spoke `Each meal uses 1 to 8 servings.` | An actual view change clears the transient serving error. A same-view action preserves it. Serving counts, pantry state, shopping checks, and budget validation remain intact. |

The first finding concerns status-message context under 4.1.3. The second
concerns status timing and the spoken context after a focus transition.

## Observed VoiceOver results

These excerpts retain the wording that VoiceOver returned. Whitespace is
normalized. Native button feedback can precede a live-region announcement.

| Flow | Spoken evidence | Result |
| --- | --- | --- |
| Meal names and selection | `Bean tacos selected toggle button`; `Egg fried rice toggle button` | Names and selection are exposed. |
| Rice selection after repair | `Egg fried rice, 2 servings. Groceries to buy $11.64. Whole packages · Sample estimate.` | The update has cost context. |
| Serving change with the same cost | `Bean tacos, 3 servings. Groceries to buy $8.06. Whole packages · Sample estimate.` | The count changes without losing cost context. |
| Package boundary | `Bean tacos, 4 servings. Groceries to buy $9.35. Whole packages · Sample estimate.` | Count and cost are announced together. |
| Original failing decrease | `Bean tacos, 3 servings. Groceries to buy $8.06. Whole packages · Sample estimate.` | The previously omitted cost is announced. |
| Serving bounds | `Each meal uses 1 to 8 servings.` | Fresh lower- and upper-bound errors are announced. |
| Pantry toggle | `olive oil checked checkbox 6 of 15`, then `unchecked` | Label and changed state are exposed. |
| Shopping toggle | `black beans 1 package · $1.29 unchecked checkbox 1 of 5`, then `checked` | Name, package count, price, and state are exposed. |
| Empty shopping list | `Nothing to buy. Every ingredient is marked at home.`; `Total $0.00` | The empty state and total can be read. |
| Invalid budget | `Enter a non-negative dollar amount with at most two decimal places.` | The validation alert is spoken automatically. |
| Invalid field revisited | `12.345 Insertion at end of text. Plan cap Enter a non-negative dollar amount with at most two decimal places. invalid data edit text` | Label, value, invalid state, and correction are associated. |
| Recovery to zero | `This meal is over the $0.00 plan cap.` | The changed budget result is spoken automatically. |
| Recovery to forty | `This meal fits the $40.00 plan cap.` | Valid recovery is spoken automatically. |
| Landmark and heading commands | `footer link Existing app`; `Prototype sections navigation`; `heading level 1 Shopping list` | VoiceOver can move by landmark and heading. |
| Return after the transient-error repair | `heading level 1 What sounds good? What sounds good? region` | Returning to Tonight announces the heading without the old error. |

Sequential reading also exposed the main landmark, meal heading, per-serving
nutrition heading, nutrition values, and their adjacent labels. Pantry,
Shopping list, and Budget transitions announced their destination headings.

## Checks and limits

The focused prototype tests pass 15/15. They cover one contextual status,
recipe changes, unchanged package costs, package boundaries, unchanged
selection, rejected bounds, view changes, heading focus, and retained invalid
budget descriptions. The source gates pass frontend lint, the full frontend
test suite, and production build. Both source commits passed gitleaks.

After the heading-return check passed, an extra repetition started a fresh
upper-bound error and entered Pantry. An authentication-screen interruption
stopped that repetition before its final return. Automatic approval review
then blocked browser access. The user paused browser testing. That extra
repetition remains incomplete; it is not reported as a pass.

No Safari, Firefox, NVDA, JAWS, braille display, physical mobile device, or
speech-input test was performed. The previous 46 axe scans belong to the
earlier WCAG audit revision; this session does not claim a new axe run.
The existing `/` application, live services, and deployment are outside scope.

The temporary browser tab contains only disposable demo state. VoiceOver was
confirmed off during cleanup. The scripting-control restoration still needs
confirmation because the settings window stopped responding.

## Review record

The independent review and final committed gates are stored under
`.fewia-supervisor-reviews/` and `.fewia-supervisor-gates/`, keyed by SHA.
The review scope starts at `4537776`. The final handoff identifies the
approved SHA and reports any review or gate failure.
