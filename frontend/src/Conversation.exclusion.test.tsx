/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type CatalogItem, type GroceryJob } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { Conversation } from "./Conversation";
import { exclusionMessage } from "./exclusionMessage";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const GENERIC_ERROR = "The grocery request failed. Retry checks the same request.";

const recipes: CatalogItem[] = [{ id: "vegetable_pasta", name: "vegetable pasta" }];
const ingredients: CatalogItem[] = [{ id: "onion", name: "onion" }];

const exclusionJob: GroceryJob = {
  id: "job-1",
  status: "failed",
  result: null,
  error_code: "exclusion_reject",
  error_detail: { recipe_id: "vegetable_pasta", ingredient_id: "onion" },
};

const failedWithoutCode: GroceryJob = {
  id: "job-1",
  status: "failed",
  error_code: null,
  result: null,
};

const succeededJob: GroceryJob = {
  id: "job-1",
  status: "succeeded",
  error_code: null,
  result: {
    spending_source: "fixture",
    budget: { available_cents: 5000, pending_cents: 0, stale: false, warnings: [] },
    meal_nutrition: sampleNutrition(),
    plan: {
      lines: [
        {
          ingredient_id: "black_beans",
          name: "black beans",
          unit: "g",
          quantity: 425,
          packages: 1,
          cost_cents: 478,
          from_pantry: false,
        },
      ],
      total_cents: 478,
      accepted: true,
      warnings: [],
      catalog_version: "sample-prices-v1",
      notice: NOTICE,
    },
  },
};

function renderConversation(job: GroceryJob | null, error: string | null): void {
  render(
    createElement(Conversation, {
      job,
      error,
      pending: false,
      recipes,
      ingredients,
      onExample: vi.fn(),
      onRetry: vi.fn(),
      onNewRequest: vi.fn(),
    }),
  );
}

describe("Conversation exclusion error", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows the named exclusion text in place of the generic failed error", () => {
    renderConversation(exclusionJob, GENERIC_ERROR);
    const named = exclusionMessage(exclusionJob, recipes, ingredients);
    const errorNode = screen.getByRole("status");
    expect(errorNode.className).toBe("conversation-error");
    expect(errorNode.textContent).toBe(named);
    expect(errorNode.textContent).not.toContain("Retry checks the same request");
  });

  it("keeps the generic error when a failed job has no error_code", () => {
    renderConversation(failedWithoutCode, GENERIC_ERROR);
    const errorNode = screen.getByRole("status");
    expect(errorNode.className).toBe("conversation-error");
    expect(errorNode.textContent).toBe(GENERIC_ERROR);
  });

  it("keeps the success status and omits the error paragraph", () => {
    renderConversation(succeededJob, null);
    expect(document.querySelector(".conversation-error")).toBeNull();
    const statusNode = screen.getByRole("status");
    expect(statusNode.className).toBe("conversation-status");
    expect(statusNode.textContent).toBe("The estimate is within the plan budget.");
  });
});
