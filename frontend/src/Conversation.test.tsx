/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, type GroceryJob } from "./apiTypes";
import { Conversation } from "./Conversation";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
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
  }> = {},
  extras: { children?: JSX.Element } = {},
): {
  renderer: ReactTestRenderer;
  onExample: ReturnType<typeof vi.fn>;
  onRetry: ReturnType<typeof vi.fn>;
  onNewRequest: ReturnType<typeof vi.fn>;
} {
  const onExample = vi.fn();
  const onRetry = vi.fn();
  const onNewRequest = vi.fn();
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
      createElement(
        Conversation,
        {
          job: props.job ?? null,
          error: props.error ?? null,
          pending: props.pending ?? false,
          onExample,
          onRetry,
          onNewRequest,
        },
        extras.children,
      ),
    );
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return { renderer, onExample, onRetry, onNewRequest };
}

describe("Conversation", () => {
  it("renders the welcome, example labels, and no fake send control", () => {
    const { renderer, onExample } = mount();
    expect(childText(renderer.root)).toContain("Your conversation");
    expect(childText(renderer.root)).toContain("Use the meal controls to choose 1 to 3 meals and 1 to 8 servings.");
    expect(childText(renderer.root)).toContain("Sample estimates use the demo price catalog.");
    expect(buttonNamed(renderer.root, "Bean tacos for two").props.disabled).toBe(false);
    expect(buttonNamed(renderer.root, "Three vegan dinners (2 servings each)").props.disabled).toBe(false);
    act(() => {
      (buttonNamed(renderer.root, "Bean tacos for two").props.onClick as () => void)();
    });
    act(() => {
      (buttonNamed(renderer.root, "Three vegan dinners (2 servings each)").props.onClick as () => void)();
    });
    expect(onExample).toHaveBeenCalledWith("beans");
    expect(onExample).toHaveBeenCalledWith("vegan");
    expect(renderer.root.findAllByType("button").every((node) => node.props.type === "button")).toBe(true);
    expect(renderer.root.findAllByType("button").some((node) => childText(node) === "Send")).toBe(false);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("disables examples while pending and reports submitting, queued, and running", () => {
    const submitting = mount({ pending: true });
    expect(buttonNamed(submitting.renderer.root, "Bean tacos for two").props.disabled).toBe(true);
    expect(buttonNamed(submitting.renderer.root, "Three vegan dinners (2 servings each)").props.disabled).toBe(
      true,
    );
    expect(childText(submitting.renderer.root)).toContain("Submitting your grocery request.");
    submitting.renderer.unmount();
    const queued = mount({ job: job("queued"), pending: true });
    expect(childText(queued.renderer.root)).toContain("Your grocery request is queued.");
    queued.renderer.unmount();
    const running = mount({ job: job("running") });
    expect(childText(running.renderer.root)).toContain("Your grocery request is running.");
    running.renderer.unmount();
  });

  it("summarizes accepted, over-budget, and incomplete results", () => {
    const accepted = mount({ job: job("succeeded", true, 478) });
    expect(childText(accepted.renderer.root)).toContain("The estimate is within the plan budget.");
    accepted.renderer.unmount();
    const over = mount({ job: job("succeeded", false, 9000) });
    expect(childText(over.renderer.root)).toContain("The plan is over budget.");
    over.renderer.unmount();
    const incomplete = mount({ job: job("succeeded", false, null) });
    expect(childText(incomplete.renderer.root)).toContain("The plan is incomplete.");
    incomplete.renderer.unmount();
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
    expect(childText(missingLine.renderer.root)).toContain("The plan is incomplete.");
    expect(childText(missingLine.renderer.root)).not.toContain("The estimate is within the plan budget.");
    missingLine.renderer.unmount();
  });

  it("uses Check progress, Start a new request, and Retry request by job state", () => {
    const progress = mount({ job: job("queued"), error: "still processing", pending: true });
    expect(childText(progress.renderer.root)).toContain("still processing");
    expect(progress.renderer.root.findAllByProps({ className: "conversation-status" })).toHaveLength(0);
    expect(childText(progress.renderer.root)).not.toContain("Your grocery request is queued.");
    act(() => {
      (buttonNamed(progress.renderer.root, "Check progress").props.onClick as () => void)();
    });
    expect(progress.onRetry).toHaveBeenCalledTimes(1);
    expect(progress.onNewRequest).not.toHaveBeenCalled();
    progress.renderer.unmount();
    const failed = mount({ job: job("failed") });
    expect(childText(failed.renderer.root)).toContain("Check meals, servings, and budget, then retry.");
    act(() => {
      (buttonNamed(failed.renderer.root, "Start a new request").props.onClick as () => void)();
    });
    expect(failed.onNewRequest).toHaveBeenCalledTimes(1);
    expect(failed.onRetry).not.toHaveBeenCalled();
    failed.renderer.unmount();
    const failedWithError = mount({ job: job("failed"), error: "The grocery request failed." });
    expect(childText(failedWithError.renderer.root)).toContain("The grocery request failed.");
    expect(failedWithError.renderer.root.findAllByProps({ className: "conversation-status" })).toHaveLength(0);
    expect(childText(failedWithError.renderer.root)).not.toContain("Check meals, servings, and budget, then retry.");
    act(() => {
      (buttonNamed(failedWithError.renderer.root, "Start a new request").props.onClick as () => void)();
    });
    expect(failedWithError.onNewRequest).toHaveBeenCalledTimes(1);
    failedWithError.renderer.unmount();
    const retry = mount({ error: "The grocery request failed." });
    act(() => {
      (buttonNamed(retry.renderer.root, "Retry request").props.onClick as () => void)();
    });
    expect(retry.onRetry).toHaveBeenCalledTimes(1);
    expect(retry.onNewRequest).not.toHaveBeenCalled();
    retry.renderer.unmount();
  });

  it("places children in the composer slot", () => {
    const { renderer } = mount({}, { children: createElement("textarea", { "aria-label": "Message" }) });
    const composer = renderer.root.findByProps({ className: "conversation-composer" });
    expect(composer.findByType("textarea").props["aria-label"]).toBe("Message");
    renderer.unmount();
  });
});
