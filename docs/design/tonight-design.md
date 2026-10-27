---
name: FEWIA Tonight
description: The local Tonight prototype's green meal-planning design system.
colors:
  forest-green: "#165641"
  pale-sage: "#edf6ed"
  ink: "#17221e"
  muted-green: "#3a4d46"
  divider: "#dce4df"
  control-border: "#5c6f67"
  white: "#ffffff"
  error: "#8b2e1f"
typography:
  display:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.55rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Source Sans 3, sans-serif"
    fontWeight: 400
  label:
    fontFamily: "Source Sans 3, sans-serif"
    fontWeight: 600
rounded:
  control: "12px"
  image: "10px"
spacing:
  compact: "0.25rem"
  canvas-top: "0.7rem"
  canvas-mobile-inline: "1rem"
  canvas-desktop-inline: "1.5rem"
components:
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "44px"
  input-text:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  navigation-active:
    textColor: "{colors.forest-green}"
    typography: "{typography.label}"
---

# Design System: FEWIA Tonight

## Overview

**Creative North Star: "The Familiar Table"**

The Tonight prototype puts a plan of one to three meals on one page with its grocery total, plan cap, nutrition, and combined shopping list. Familiar supplies the forest-green selection and focus color and the pale-sage selection surface. Pantry Edit supplies Source Sans 3 and the compact, direct layout.

This system applies only to `/prototype`. It does not restyle the existing `/` application. The Plan page keeps the meal cards, the package-based estimate, the budget fit, and the shopping list together. The Pantry view is the only other view.

**Key Characteristics:**
- One card per planned meal, with its image, servings, and ingredients together.
- Green controls on white, with sage for selected meal choices.
- One bottom navigation area on compact screens.
- Fine borders carry separation; surfaces stay flat.

## Colors

The palette uses forest green for selected, hover, and active states, with quiet green neutrals on white.

### Primary
- **Forest Green:** Selected outlines, hover borders, keyboard focus, and the active navigation item.
- **Pale Sage:** Selected meal-choice surfaces and image fallback surfaces.

### Neutral
- **Ink:** Headings and primary text.
- **Muted Green:** Supporting text and inactive navigation.
- **Divider:** Decorative separators.
- **Control Border:** Input, serving, and pantry boundaries with 5.35:1 contrast on white.
- **White:** Main and control surfaces.

### Status
- **Error:** Validation and error messages.

## Typography

**Display Font:** Source Sans 3 (with sans-serif fallback)
**Body Font:** Source Sans 3 (with sans-serif fallback)
**Label/Mono Font:** Source Sans 3 for labels; no mono face is used.

**Character:** A clean grotesque keeps meal names and grocery facts readable. The same family carries headings, controls, and supporting copy.

### Hierarchy
- **Headline** (600, 1.55rem mobile / 1.8rem at 720px, 1.2 line-height): The page heading.
- **Title** (600, 1.3rem mobile / 1.45rem at 720px, 1.2 line-height): Meal and section headings.
- **Body** (400, inherited size): Instructions and supporting text.
- **Label** (600): Meal choices and navigation labels.
- **Price** (600, 2.5rem, -0.03em letter spacing): The grocery estimate.

## Layout

The canvas is centered and capped at 1000px; from 1180px the cap is 1360px. On compact screens, it uses 1rem inline padding and scrolls within a 100dvh frame. Navigation stays below the canvas. At 720px, the canvas uses 1.5rem inline padding, wider gaps, and taller meal thumbnails. Meal choices, meal cards, and nutrition values adapt their columns to text size. Below 360px, the nutrition values stack. Long text wraps without truncation. Navigation remains a single bottom row.

Each meal card holds its image, servings stepper, per-serving nutrition, and a collapsed ingredient list. Users adjust servings from one to eight per meal. Pantry choices change which whole packages FEWIA includes in the estimate; they do not change nutrition. On compact screens, a pinned bar at the top of the canvas shows the total and the fit line. The canvas `scroll-padding-top` reads the measured bar height from `--tonight-pinned-height`, so focused controls stay below the bar when it wraps. From 720px, the Plan page uses two columns: meals on the left, and a sticky summary and shopping list on the right. The sticky bottom navigation is 4.5rem tall. The window `scroll-padding-bottom` and the side column's maximum height (through `--tonight-nav-height`) both reserve that height. Change both values together.

### Ask FEWIA placement

The "Ask FEWIA" panel is one `aside` in the shell, after `main` and before the footer. It shows on the Plan and Pantry views. Its placement follows the width:

- **1180px and wider:** a persistent, sticky third column, 23rem wide and the full height between the top and the navigation. The canvas cap grows to 1360px, the nutrition grid minimum is 4.4rem, and there is no dock bar.
- **720px to 1179px:** a dock bar sits above the navigation and reads "Ask FEWIA for a meal idea". It opens the panel as a sheet over the meals column; the Plan summary stays visible. The side column's maximum height and `scroll-padding-bottom` subtract `--tonight-dock-height` as well as `--tonight-nav-height`.
- **Below 720px:** the dock bar sits between the canvas and the navigation. The open sheet starts below the pinned total bar, using `--tonight-pinned-height`, so the total stays visible.

`--tonight-dock-height` is 3.75rem (the dock bar height). It is 0 from 1180px, where there is no dock. The dock button has `aria-expanded` and `aria-controls`. Opening the sheet focuses the textarea. "Hide chat" and Escape close it and return focus to the dock button. While the sheet is open, the content it covers is `inert`: the whole plan below 720px, the meals column from 720px to 1179px. A reply that arrives while the sheet is closed shows "1 new reply" as text in the dock bar; opening the sheet clears it. Reduced motion removes the sheet slide. At large text sizes the idea card puts its photo above the text.

## Elevation & Depth

White surfaces and fine borders define groups. Selected items use inset bars and underlined labels, with green and pale sage as additional cues. Keyboard focus uses a green outline with a 3px stroke and 3px offset. Navigation draws the focus outline inside each button to keep it within the viewport.

## Shapes

Controls and meal-choice cards use gently rounded 12px corners. Meal photos and thumbnails clip to 10px corners. One-pixel dividers separate lists and navigation. The form stays flat, with no pill-shaped controls.

## Components

### Buttons
- **Shape:** Rounded control corners (12px).
- **Primary:** The Plan page has no primary button. Each action belongs to a meal choice, a meal card, or the navigation.
- **Hover / Focus:** Hover gives the Remove button a forest-green border and a pale-sage surface. Keyboard focus uses the shared 3px green outline with a 3px offset. No button transition is defined.
- **Secondary:** The Remove button has a white surface, a one-pixel control border, ink text, and a 44px minimum height.
- **Ghost:** Back and stepper controls use transparent backgrounds with ink text.

### Cards / Containers
- **Corner Style:** Meal choices use 12px corners; their images use 10px corners.
- **Background:** White at rest; pale sage on the selected meal choice.
- **Selection:** An inset bar and underlined label identify the selected meal without color alone.
- **Border:** Two-pixel divider at rest; forest green on hover or selection.
- **Internal Padding:** Meal choices use 0.3rem on compact screens and 0.4rem from 720px.

### Inputs / Fields
- **Style:** White text field with a one-pixel control border, 12px corners, and 2.75rem minimum height.
- **Focus:** Green caret and the shared 3px green focus outline with a 3px offset.
- **Error:** Error text uses the error color; budget input exposes its invalid state.

### Navigation
- **Style:** Two equal-width items, Plan and Pantry, in a white bottom row with a top divider. Each item has a 22px icon above a semibold label and a 3.5rem minimum height. From 720px, the row is sticky at the bottom of the window and centered to the canvas width.
- **States:** Inactive labels and icons use muted green. The current section has an underline and inset bar as well as forest green.
- **Behavior:** The navigation follows the canvas in the DOM, so its visual position and its tab order agree.

### Meal Selection
Meal choices pair an image with a name. Selection adds an inset bar and underlined label, plus a green outline and pale-sage surface. The underline remains visible in forced-color mode. The meal image fades in over 220ms with ease-out timing; reduced-motion preference disables that fade.

## Do's and Don'ts

### Do:
- **Do** keep these tokens and components scoped to `/prototype`.
- **Do** keep each meal image beside the facts it describes.
- **Do** use one bottom navigation area on compact screens.

### Don't:
- **Don't** apply this prototype system to the existing `/` application.
- **Don't** duplicate navigation at both the top and bottom.
- **Don't** add shadows or remove the estimate's sample-data context.
