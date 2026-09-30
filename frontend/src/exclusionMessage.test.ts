/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import type { GroceryJob } from "./apiTypes";
import { exclusionMessage } from "./exclusionMessage";

const recipes = [{ id: "vegetable_pasta", name: "vegetable pasta" }];
const ingredients = [{ id: "onion", name: "onion" }];

function failed(overrides: Partial<GroceryJob> = {}): GroceryJob {
  return {
    id: "job-1",
    status: "failed",
    result: null,
    error_code: "exclusion_reject",
    error_detail: { recipe_id: "vegetable_pasta", ingredient_id: "onion" },
    ...overrides,
  };
}

describe("exclusionMessage", () => {
  it("returns the exclusion sentence for a failed exclusion_reject job", () => {
    expect(exclusionMessage(failed(), recipes, ingredients)).toBe(
      "The grocery request failed. Vegetable pasta needs onion, which is excluded. Clear the onion exclusion or choose another meal, then rebuild.",
    );
  });

  it("falls back to raw ids when the catalog has no match", () => {
    expect(exclusionMessage(failed(), [], [])).toBe(
      "The grocery request failed. vegetable_pasta needs onion, which is excluded. Clear the onion exclusion or choose another meal, then rebuild.",
    );
  });

  it("returns null for another error_code", () => {
    expect(exclusionMessage(failed({ error_code: "tool" }), recipes, ingredients)).toBeNull();
  });

  it("returns null when error_detail is missing or null", () => {
    expect(exclusionMessage(failed({ error_detail: null }), recipes, ingredients)).toBeNull();
    const missingDetail: GroceryJob = {
      id: "job-1",
      status: "failed",
      result: null,
      error_code: "exclusion_reject",
    };
    expect(exclusionMessage(missingDetail, recipes, ingredients)).toBeNull();
  });

  it("returns null for a non-failed job", () => {
    expect(
      exclusionMessage(
        { id: "job-1", status: "queued", result: null, error_code: null },
        recipes,
        ingredients,
      ),
    ).toBeNull();
    expect(exclusionMessage(null, recipes, ingredients)).toBeNull();
  });
});
