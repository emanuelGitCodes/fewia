---
name: FEWIA Tonight
description: The local Tonight prototype's green meal-planning design system.
colors:
  forest-green: "#165641"
  forest-green-hover: "#124a37"
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
  button-primary:
    backgroundColor: "{colors.forest-green}"
    textColor: "{colors.white}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    height: "2.75rem"
    width: "100%"
  button-primary-hover:
    backgroundColor: "{colors.forest-green-hover}"
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

The Tonight prototype puts one meal choice beside its grocery estimate and nutrition facts. Familiar supplies the forest-green actions and pale-sage selection. Pantry Edit supplies Source Sans 3 and the compact, direct layout.

This system applies only to `/prototype`. It does not restyle the existing `/` application. The page keeps the chosen meal, package-based grocery estimate, and declared pantry context together, then gives pantry, budget, and shopping tasks their own views.

**Key Characteristics:**
- One selected meal with its image and facts together.
- Green controls on white, with sage for selected meal choices.
- One bottom navigation area on compact screens.
- Fine borders carry separation; surfaces stay flat.

## Colors

The palette uses forest green for action and active states, with quiet green neutrals on white.

### Primary
- **Forest Green:** Primary actions, selected outlines, keyboard focus, and the active navigation item.
- **Forest Green Hover:** The primary action's hover state.
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
- **Label** (600): Meal choices, primary action, and navigation labels.
- **Price** (600, 2.5rem, -0.03em letter spacing): The grocery estimate.

## Layout

The canvas is centered and capped at 1000px. On compact screens, it uses 1rem inline padding and scrolls within a 100dvh frame. Navigation stays below the canvas. At 720px, the canvas uses 1.5rem inline padding, wider gaps, and taller meal thumbnails. Meal choices, the compact hero, and nutrition values adapt their columns to text size. Below 360px, the hero and nutrition values stack. Long text wraps without truncation. Navigation remains a single bottom row.

The selected meal's image and facts update together. Users adjust servings from one to eight. Pantry choices change which whole packages FEWIA includes in the estimate; they do not change the nutrition panel. The shopping checklist, budget feedback, and all-items-at-home state use the same compact canvas.

## Elevation & Depth

White surfaces and fine borders define groups. Selected items use inset bars and underlined labels, with green and pale sage as additional cues. Keyboard focus uses a green outline with a 3px stroke and 3px offset. Navigation draws the focus outline inside each button to keep it within the viewport.

## Shapes

Controls and meal-choice cards use gently rounded 12px corners. Meal photos and thumbnails clip to 10px corners. One-pixel dividers separate lists and navigation. The form stays flat, with no pill-shaped controls.

## Components

### Buttons
- **Shape:** Rounded control corners (12px).
- **Primary:** Forest green with white text; full width and at least 2.75rem tall.
- **Hover / Focus:** Hover darkens the green. Keyboard focus uses the shared 3px green outline with a 3px offset. No button transition is defined.
- **Secondary / Ghost:** Back and stepper controls use transparent backgrounds with ink text.

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
- **Style:** Three equal-width items in a white bottom row with a top divider. Each item has a 22px icon above a semibold label and a 3.5rem minimum height.
- **States:** Inactive labels and icons use muted green. The current section has an underline and inset bar as well as forest green.
- **Behavior:** The Tonight item remains current while the shopping list is open.

### Meal Selection
Meal choices pair an image with a name. Selection adds an inset bar and underlined label, plus a green outline and pale-sage surface. The underline remains visible in forced-color mode. The meal image fades in over 220ms with ease-out timing; reduced-motion preference disables that fade.

## Do's and Don'ts

### Do:
- **Do** keep these tokens and components scoped to `/prototype`.
- **Do** keep the selected meal image beside the facts it describes.
- **Do** use one bottom navigation area on compact screens.

### Don't:
- **Don't** apply this prototype system to the existing `/` application.
- **Don't** duplicate navigation at both the top and bottom.
- **Don't** add shadows or remove the estimate's sample-data context.
