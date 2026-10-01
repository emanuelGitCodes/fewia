/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type CatalogItem, type GroceryJob } from "./apiTypes";
import { sampleNutrition } from "../tests/apiFixtures";
import { Conversation, type ExampleKind } from "./Conversation";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name }) as HTMLButtonElement;
}

function job(status: GroceryJob["status"], accepted = true, total: number | null = 478): GroceryJob {
  return {
    id: "job-1",
    status,
    error_code: status === "failed" ? "tool" : null,
    result:
      status === "succeeded"
        ? {
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
                  cost_cents: total,
                  from_pantry: false,
                },
              ],
              total_cents: total,
              accepted,
              warnings: [],
              catalog_version: "sample-prices-v1",
              notice: NOTICE,
            },
          }
        : null,
  };
}

function mount(
  props: Partial<{
    job: GroceryJob | null;
    error: string | null;
    pending: boolean;
    freshRequestsDisabled: boolean;
    recipes: CatalogItem[];
    ingredients: CatalogItem[];
  }> = {},
  extras: { children?: JSX.Element } = {},
): {
  rendered: RenderResult;
  onExample: ReturnType<typeof vi.fn<(kind: ExampleKind) => void>>;
  onRetry: ReturnType<typeof vi.fn<() => void>>;
  onNewRequest: ReturnType<typeof vi.fn<() => void>>;
} {
  const onExample = vi.fn<(kind: ExampleKind) => void>();
  const onRetry = vi.fn<() => void>();
  const onNewRequest = vi.fn<() => void>();
  const rendered = render(
    createElement(
      Conversation,
      {
        job: props.job ?? null,
        error: props.error ?? null,
        pending: props.pending ?? false,
        freshRequestsDisabled: props.freshRequestsDisabled,
        recipes: props.recipes,
        ingredients: props.ingredients,
        onExample,
        onRetry,
        onNewRequest,
      },
      extras.children,
    ),
  );
  return { rendered, onExample, onRetry, onNewRequest };
}

afterEach(cleanup);

describe("Conversation", () => {
  it("renders the welcome, example labels, and no fake send control", () => {
    const { rendered, onExample } = mount();
    expect(renderedText(rendered.container)).toContain("Your conversation");
    expect(renderedText(rendered.container)).toContain("Use the meal controls to choose 1 to 3 meals and 1 to 8 servings.");
    expect(renderedText(rendered.container)).toContain("Sample estimates use the demo price catalog.");
    expect(buttonNamed(rendered.container, "Bean tacos for two").disabled).toBe(false);
    expect(buttonNamed(rendered.container, "Three vegan dinners (2 servings each)").disabled).toBe(false);
    fireEvent.click(buttonNamed(rendered.container, "Bean tacos for two"));
    fireEvent.click(buttonNamed(rendered.container, "Three vegan dinners (2 servings each)"));
    expect(onExample).toHaveBeenCalledWith("beans");
    expect(onExample).toHaveBeenCalledWith("vegan");
    expect(
      within(rendered.container).queryAllByRole("button").every(
        (node) => (node as HTMLButtonElement).type === "button",
      ),
    ).toBe(true);
    expect(within(rendered.container).queryAllByRole("button", { name: "Send" })).toHaveLength(0);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    rendered.unmount();
  });

  it("disables examples while pending and reports submitting, queued, and running", () => {
    const submitting = mount({ pending: true });
    expect(buttonNamed(submitting.rendered.container, "Bean tacos for two").disabled).toBe(true);
    expect(buttonNamed(submitting.rendered.container, "Three vegan dinners (2 servings each)").disabled).toBe(
      true,
    );
    expect(renderedText(submitting.rendered.container)).toContain("Submitting your grocery request.");
    submitting.rendered.unmount();
    const queued = mount({ job: job("queued"), pending: true });
    expect(renderedText(queued.rendered.container)).toContain("Your grocery request is queued.");
    queued.rendered.unmount();
    const running = mount({ job: job("running") });
    expect(renderedText(running.rendered.container)).toContain("Your grocery request is running.");
    running.rendered.unmount();
  });

  it("summarizes accepted, over-budget, and incomplete results", () => {
    const accepted = mount({ job: job("succeeded", true, 478) });
    expect(renderedText(accepted.rendered.container)).toContain("The estimate is within the plan budget.");
    accepted.rendered.unmount();
    const over = mount({ job: job("succeeded", false, 9000) });
    expect(renderedText(over.rendered.container)).toContain("The plan is over budget.");
    over.rendered.unmount();
    const incomplete = mount({ job: job("succeeded", false, null) });
    expect(renderedText(incomplete.rendered.container)).toContain("The plan is incomplete.");
    incomplete.rendered.unmount();
    const base = job("succeeded", true, 478);
    const result = base.result;
    if (result === null) {
      throw new Error("expected result");
    }
    const firstLine = result.plan.lines[0];
    if (firstLine === undefined) {
      throw new Error("expected line");
    }
    const missingLine = mount({
      job: {
        ...base,
        result: {
          ...result,
          plan: {
            ...result.plan,
            accepted: true,
            total_cents: 478,
            lines: [{ ...firstLine, cost_cents: null }],
          },
        },
      },
    });
    expect(renderedText(missingLine.rendered.container)).toContain("The plan is incomplete.");
    expect(renderedText(missingLine.rendered.container)).not.toContain("The estimate is within the plan budget.");
    missingLine.rendered.unmount();
  });

  it("uses Check progress, Start a new request, and Retry request by job state", () => {
    const progress = mount({ job: job("queued"), error: "still processing", pending: true });
    expect(renderedText(progress.rendered.container)).toContain("still processing");
    expect(
      within(progress.rendered.container).queryAllByText("Your grocery request is queued."),
    ).toHaveLength(0);
    expect(renderedText(progress.rendered.container)).not.toContain("Your grocery request is queued.");
    expect(buttonNamed(progress.rendered.container, "Check progress").disabled).toBe(true);
    fireEvent.click(buttonNamed(progress.rendered.container, "Check progress"));
    expect(progress.onRetry).not.toHaveBeenCalled();
    progress.rendered.rerender(
      createElement(Conversation, {
        job: job("queued"),
        error: "still processing",
        pending: false,
        onExample: progress.onExample,
        onRetry: progress.onRetry,
        onNewRequest: progress.onNewRequest,
      }),
    );
    expect(buttonNamed(progress.rendered.container, "Check progress").disabled).toBe(false);
    fireEvent.click(buttonNamed(progress.rendered.container, "Check progress"));
    expect(progress.onRetry).toHaveBeenCalledTimes(1);
    expect(progress.onNewRequest).not.toHaveBeenCalled();
    progress.rendered.unmount();
    const failed = mount({ job: job("failed") });
    expect(renderedText(failed.rendered.container)).toContain("Check meals, servings, and budget, then retry.");
    expect(buttonNamed(failed.rendered.container, "Start a new request").disabled).toBe(false);
    fireEvent.click(buttonNamed(failed.rendered.container, "Start a new request"));
    expect(failed.onNewRequest).toHaveBeenCalledTimes(1);
    expect(failed.onRetry).not.toHaveBeenCalled();
    failed.rendered.unmount();
    const failedWithError = mount({ job: job("failed"), error: "The grocery request failed." });
    expect(renderedText(failedWithError.rendered.container)).toContain("The grocery request failed.");
    expect(
      within(failedWithError.rendered.container).queryAllByText(
        "The grocery request failed. Check meals, servings, and budget, then retry.",
      ),
    ).toHaveLength(0);
    expect(renderedText(failedWithError.rendered.container)).not.toContain("Check meals, servings, and budget, then retry.");
    fireEvent.click(buttonNamed(failedWithError.rendered.container, "Start a new request"));
    expect(failedWithError.onNewRequest).toHaveBeenCalledTimes(1);
    failedWithError.rendered.unmount();
    const retry = mount({ error: "The grocery request failed." });
    expect(buttonNamed(retry.rendered.container, "Retry request").disabled).toBe(false);
    fireEvent.click(buttonNamed(retry.rendered.container, "Retry request"));
    expect(retry.onRetry).toHaveBeenCalledTimes(1);
    expect(retry.onNewRequest).not.toHaveBeenCalled();
    retry.rendered.unmount();
    const retryPending = mount({ error: "The grocery request failed.", pending: true });
    expect(buttonNamed(retryPending.rendered.container, "Retry request").disabled).toBe(true);
    retryPending.rendered.unmount();
  });

  it("disables examples and a failed new request when freshRequestsDisabled", () => {
    const blocked = mount({ freshRequestsDisabled: true });
    expect(buttonNamed(blocked.rendered.container, "Bean tacos for two").disabled).toBe(true);
    expect(buttonNamed(blocked.rendered.container, "Three vegan dinners (2 servings each)").disabled).toBe(
      true,
    );
    blocked.rendered.unmount();
    const failed = mount({ job: job("failed"), freshRequestsDisabled: true });
    expect(buttonNamed(failed.rendered.container, "Start a new request").disabled).toBe(true);
    failed.rendered.unmount();
    const retry = mount({ error: "The grocery request failed.", freshRequestsDisabled: true });
    expect(buttonNamed(retry.rendered.container, "Retry request").disabled).toBe(false);
    retry.rendered.unmount();
    const progress = mount({
      job: job("queued"),
      error: "still processing",
      pending: false,
      freshRequestsDisabled: true,
    });
    expect(buttonNamed(progress.rendered.container, "Check progress").disabled).toBe(false);
    progress.rendered.unmount();
  });

  it("names the excluded ingredient on exclusion_reject", () => {
    const { rendered } = mount({
      job: {
        id: "job-1",
        status: "failed",
        result: null,
        error_code: "exclusion_reject",
        error_detail: { recipe_id: "vegetable_pasta", ingredient_id: "onion" },
      },
      recipes: [{ id: "vegetable_pasta", name: "vegetable pasta" }],
      ingredients: [{ id: "onion", name: "onion" }],
    });
    expect(renderedText(rendered.container)).toContain(
      "Vegetable pasta needs onion, which is excluded. Clear the onion exclusion or choose another meal, then rebuild.",
    );
    rendered.unmount();
  });

  it("keeps the generic failed text when exclusion_reject has no error_detail", () => {
    const { rendered } = mount({
      job: {
        id: "job-1",
        status: "failed",
        result: null,
        error_code: "exclusion_reject",
      },
    });
    expect(renderedText(rendered.container)).toContain(
      "The grocery request failed. Check meals, servings, and budget, then retry.",
    );
    rendered.unmount();
  });

  it("places children in the composer slot", () => {
    const { rendered } = mount({}, { children: createElement("textarea", { "aria-label": "Message" }) });
    const message = screen.getByRole("textbox", { name: "Message" });
    const composer = rendered.container.querySelector(".conversation-composer");
    expect(composer?.contains(message)).toBe(true);
    expect(message.getAttribute("aria-label")).toBe("Message");
    rendered.unmount();
  });
});
