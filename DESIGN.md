---
name: FEWIA
description: A budget-aware grocery planner that keeps the arithmetic honest.
colors:
  paper-white: "#ffffff"
  forest-ink: "#183f30"
  ledger-green: "#20553d"
  sage-slate: "#456357"
  pale-sage-rule: "#aabbb2"
  sage-wash: "#f1f5ef"
  brick-red: "#8a1f1f"
  ochre-rule: "#8a5a12"
  dark-ochre: "#5c3d0a"
typography:
  display:
    fontFamily: "Lora, serif"
    fontSize: "clamp(2.4rem, 6vw, 3.7rem)"
    fontWeight: 400
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  wordmark:
    fontFamily: "Lora, serif"
    fontSize: "clamp(1.8rem, 4vw, 2.35rem)"
    fontWeight: 400
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
  figure:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.85rem"
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  empty-title:
    fontFamily: "Lora, serif"
    fontSize: "1.35rem"
    fontWeight: 400
  note:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.5
  estimate-note:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "0.92rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  md: "6px"
  lg: "12px"
spacing:
  xs: "0.35rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1.25rem"
  xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.ledger-green}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.md}"
    padding: "0.45rem 0.75rem"
    height: "44px"
  button-primary-disabled:
    backgroundColor: "{colors.sage-slate}"
    textColor: "{colors.paper-white}"
  button-secondary:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ledger-green}"
    rounded: "{rounded.md}"
    padding: "0.45rem 0.75rem"
    height: "44px"
  input:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.md}"
    padding: "0.45rem 0.75rem"
    height: "44px"
  panel:
    backgroundColor: "{colors.paper-white}"
    rounded: "{rounded.md}"
    padding: "clamp(1.25rem, 3vw, 2rem)"
  message:
    backgroundColor: "{colors.sage-wash}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.md}"
    padding: "0.75rem 0.9rem"
  dialog:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.forest-ink}"
    rounded: "{rounded.lg}"
    padding: "1.5rem"
---

# Design System: FEWIA

## Overview

**Creative North Star: "The Market Ledger"**

The interface reads like a calm, exact ledger. Green ink sits on white
paper. Fine rules separate each line. Numbers are plain, large where they
matter, and always labeled with their source. The look supports the product
position: the model talks, but the code does the arithmetic, and the page
shows that arithmetic without ornament.

Density is moderate. A shopper plans a few meals at a time, so each panel
holds one job: the conversation, the chat, or the budget and estimate.
Surfaces are flat. Depth comes from 1 px rules and one pale sage wash, not
from shadows. The mood is calm, exact, and trustworthy.

**Key Characteristics:**

- White paper, forest-green ink, one green accent.
- Flat panels with 1 px pale sage borders and 6 px corners.
- A Lora serif only for the wordmark, the page heading, and empty-state titles.
- Source Sans 3 for every control, label, and number.
- Every estimate carries a visible notice and source label.

## Colors

A single-hue green palette on white, with red and ochre reserved for problems.

### Primary

- **Ledger Green** (`ledger-green`): the one action color. Primary buttons,
  the wordmark, totals, speaker names in chat, focus rings, and text selection.

### Neutral

- **Paper White** (`paper-white`): the page and every panel background.
- **Forest Ink** (`forest-ink`): body text and headings.
- **Sage Slate** (`sage-slate`): secondary text, status lines, notices, and
  the disabled primary button.
- **Pale Sage Rule** (`pale-sage-rule`): panel borders, list dividers, the
  header and footer rules, and control borders.
- **Sage Wash** (`sage-wash`): chat messages, status boxes, and the empty
  conversation card.

### Status

- **Brick Red** (`brick-red`): error text and the "plan changed" warning.
- **Ochre Rule** (`ochre-rule`) and **Dark Ochre** (`dark-ochre`): the left
  rule and text of an estimate warning, such as stale spending.

### Named Rules

**The One Ink Rule.** Ledger Green is the only accent. A new feature MUST NOT
add a second accent hue. Red and ochre appear only for errors and warnings.

## Typography

**Display Font:** Lora (with serif)
**Body Font:** Source Sans 3 (with sans-serif)

**Character:** A quiet book serif names the product and the page. A clear
humanist sans carries every task, label, and figure.

### Hierarchy

- **Display** (400, clamp(2.4rem, 6vw, 3.7rem), 1.08): the page heading only.
- **Wordmark** (400, clamp(1.8rem, 4vw, 2.35rem)): the header wordmark only.
- **Headline** (600, 1.5rem, 1.2): panel titles.
- **Figure** (600, 1.85rem, 1.2): the plan estimate total.
- **Title** (600, 1.15rem, 1.2): subsection titles and the overlay total.
- **Body** (400, 16px, 1.5): messages, status lines, and line items.
- **Label** (600, 16px, 1.5): form labels, legends, and line-item names.
- **Empty title** (Lora 400, 1.35rem, Ledger Green): empty-state titles.
- **Note** (400, 0.9rem, 1.5): the nutrition notices.
- **Estimate note** (400, 0.92rem, 1.5): the sample-price notice under an estimate.

### Named Rules

**The Serif Is a Signature Rule.** Lora appears in three places: the
wordmark, the page heading, and empty-state titles. Panel titles, numbers,
and controls use Source Sans 3.

## Layout

The page is a centered column, at most 80rem wide, with a 1.25rem to 3rem
side gutter. Above 70rem, the workspace is three columns: conversation,
chat, and the budget panel, in the ratio 1.1 : 1.1 : 0.85, with a 1.5rem
gap. Below 70rem, the columns stack in the order chat, conversation,
budget. Below 50rem, the page narrows to 42rem and each estimate line folds
from four columns to two. Below 32rem, the header stacks and the budget
form becomes a two-column grid. The layout MUST NOT scroll horizontally at
a 375 px width.

## Elevation & Depth

The system is flat. No surface casts a shadow. Panels separate by a 1 px
Pale Sage Rule border. Messages and status boxes separate by the Sage Wash
fill. The only overlay is the handoff consent dialog, which dims the page
with a 45% black backdrop.

### Named Rules

**The Ruled Paper Rule.** Use a 1 px rule or the Sage Wash fill to separate
content. A surface MUST NOT use a shadow, a gradient, or a second fill color.

## Shapes

Corners are gently rounded at 6 px on panels, controls, messages, and
status boxes. Only the consent dialog uses 12 px. Lists use full-width
bottom rules, not boxes. Notices use a 3 px left rule.

## Components

### Buttons

Plain and steady.

- **Shape:** gently rounded (6 px), at least 44 px tall and 44 px wide.
- **Primary:** Ledger Green fill with Paper White text. Use one primary
  button per area: build estimate, rebuild estimate, send, or retry.
- **Secondary:** Paper White fill, Ledger Green 600-weight text, Pale Sage
  Rule border. Use for example prompts and other optional actions.
- **Focus:** a 3 px Ledger Green outline, offset 3 px.
- **Disabled:** every control drops to 65% opacity with a not-allowed
  cursor. The primary also turns Sage Slate, so it renders Sage Slate at
  65% opacity.
- **Known drift:** the consent dialog buttons use a 2 px focus outline and
  both use the primary style.

### Inputs / Fields

- **Style:** Paper White fill, 1 px Pale Sage Rule border, 6 px corners,
  at least 44 px tall. The chat textarea is at least 8rem tall.
- **Labels:** always visible, 600 weight, above or beside the field.
- **Focus:** the shared 3 px Ledger Green outline.
- **Error:** a Brick Red message above the composer or form.

### Cards / Containers

- **Corner Style:** 6 px.
- **Background:** Paper White.
- **Shadow Strategy:** none; see Elevation & Depth.
- **Border:** 1 px Pale Sage Rule.
- **Internal Padding:** clamp(1.25rem, 3vw, 2rem).

### Chat Messages

Each message is a Sage Wash block with 6 px corners. The first line names
the speaker in Ledger Green at 600 weight. The message text follows in
Forest Ink.

### Estimate Ledger

The signature component. Each ingredient line is a four-column grid: name,
need, packages, and cost. A 1 px rule closes each line. The cost aligns
right. The total sits above the lines in the Figure style. The pantry
checkbox spans the full line below its item. The sample-price notice sits
directly under the estimate.

## Do's and Don'ts

### Do:

- **Do** keep Ledger Green as the only accent color.
- **Do** show the sample-price notice next to every estimate.
- **Do** keep every control at least 44 px tall with a visible label.
- **Do** use the 3 px Ledger Green focus outline on every interactive element.
- **Do** separate content with 1 px rules and the Sage Wash fill.

### Don't:

- **Don't** add shadows, gradients, or decorative charts and metrics.
- **Don't** use Lora for numbers, controls, or panel titles.
- **Don't** show a fabricated job, plan, or price on the default screen.
- **Don't** use color alone to signal an error or warning; pair it with text.
