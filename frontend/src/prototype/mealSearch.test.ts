/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SEARCH_TERMS, filterMeals, searchNote } from "./mealSearch";
import {
  CATALOG_SEARCH_TERMS,
  INGREDIENTS,
  RECIPE_ORDER,
  RECIPES,
  mealLabels,
  type RecipeId,
} from "./prototypeData";

function withTag(tag: string): RecipeId[] {
  return RECIPE_ORDER.filter((id) => (RECIPES[id].tags as readonly string[]).includes(tag));
}

describe("SEARCH_TERMS", () => {
  const groups: Array<[string[], RecipeId[]]> = [
    [["keto", "low carb", "lowcarb", "low-carb"], withTag("lower_carb")],
    [["carnivore", "meat"], withTag("chicken")],
    [["gf", "gluten free", "gluten-free", "celiac"], withTag("gluten_free_ingredients")],
    [["plant based", "plant-based"], RECIPE_ORDER.filter((id) => RECIPES[id].diets.includes("vegan"))],
    [["veggie"], RECIPE_ORDER.filter((id) => RECIPES[id].diets.includes("vegetarian"))],
    [["protein"], withTag("high_protein")],
  ];

  for (const [terms, expected] of groups) {
    it(`maps ${terms.join(", ")} to its target recipes`, () => {
      expect(expected.length).toBeGreaterThan(0);
      for (const term of terms) {
        expect(SEARCH_TERMS[term]).toBeDefined();
        const found = filterMeals(term);
        expect(found).toEqual(expected);
      }
    });
  }

  it("is read from the backend search terms in their order", () => {
    expect(Object.keys(SEARCH_TERMS)).toEqual(Object.keys(CATALOG_SEARCH_TERMS));
    expect(Object.keys(SEARCH_TERMS)).toHaveLength(14);
    for (const [term, { target, note }] of Object.entries(CATALOG_SEARCH_TERMS)) {
      expect(SEARCH_TERMS[term].target).toBe(target);
      expect(SEARCH_TERMS[term].note).toBe(note ?? undefined);
    }
  });

  it("returns the exact counts for keto and meat", () => {
    expect(filterMeals("keto")).toHaveLength(8);
    expect(filterMeals("meat")).toHaveLength(12);
  });
});

describe("filterMeals", () => {
  it("normalizes case, edge spaces and repeated spaces", () => {
    expect(filterMeals("  GLUTEN   free ")).toEqual(filterMeals("gluten free"));
  });

  it("matches by name, label and ingredient name", () => {
    expect(filterMeals("curry")).toContain("chicken_curry");
    expect(filterMeals("high protein")).toEqual(withTag("high_protein"));
    const rice = RECIPE_ORDER.filter((id) =>
      RECIPES[id].ingredients.some(([ingredientId]) =>
        INGREDIENTS[ingredientId].name.toLowerCase().includes("rice"),
      ),
    );
    expect(rice.length).toBeGreaterThan(0);
    expect(filterMeals("rice")).toEqual(
      RECIPE_ORDER.filter(
        (id) => rice.includes(id) || RECIPES[id].name.toLowerCase().includes("rice"),
      ),
    );
  });

  it("matches the label text of every recipe", () => {
    for (const id of RECIPE_ORDER) {
      for (const label of mealLabels(RECIPES[id])) {
        expect(filterMeals(label.toLowerCase())).toContain(id);
      }
    }
  });

  it("returns all meals for an empty query and none for nonsense", () => {
    expect(filterMeals("")).toEqual([...RECIPE_ORDER]);
    expect(filterMeals("zzz")).toEqual([]);
    expect(filterMeals("constructor")).toEqual([]);
  });
});

describe("searchNote", () => {
  const ketoNote =
    "No meal in this catalog is keto. These meals have 30 g of carbs or less per serving.";
  const carnivoreNote = "No meal is strictly carnivore. These meals include chicken.";

  it("returns the note for every term that has one", () => {
    for (const term of ["keto", "low carb", "lowcarb", "low-carb"]) {
      expect(searchNote(term)).toBe(ketoNote);
    }
    for (const term of ["carnivore", "meat"]) {
      expect(searchNote(term)).toBe(carnivoreNote);
    }
    expect(searchNote("Keto")).toBe(ketoNote);
  });

  it("returns null for every other term and for plain queries", () => {
    const noted = new Set(["keto", "low carb", "lowcarb", "low-carb", "carnivore", "meat"]);
    for (const term of Object.keys(SEARCH_TERMS)) {
      if (!noted.has(term)) {
        expect(searchNote(term)).toBeNull();
      }
    }
    expect(searchNote("rice")).toBeNull();
    expect(searchNote("")).toBeNull();
    expect(searchNote("constructor")).toBeNull();
  });
});
