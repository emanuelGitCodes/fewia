/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SEARCH_TERMS, filterMeals, searchNote } from "./mealSearch";
import { INGREDIENTS, RECIPE_ORDER, RECIPES, mealLabels, type RecipeId } from "./prototypeData";

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
        for (const id of expected) {
          expect(found).toContain(id);
        }
        expect(found).toEqual(RECIPE_ORDER.filter((id) => found.includes(id)));
      }
    });
  }

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
  it("returns the keto and carnivore notes", () => {
    expect(searchNote("Keto")).toBe(
      "No meal in this catalog is keto. These meals have 30 g of carbs or less per serving.",
    );
    expect(searchNote("meat")).toBe("No meal is strictly carnivore. These meals include chicken.");
  });

  it("returns null for terms without a note and for plain queries", () => {
    expect(searchNote("gf")).toBeNull();
    expect(searchNote("rice")).toBeNull();
    expect(searchNote("")).toBeNull();
    expect(searchNote("constructor")).toBeNull();
  });
});
