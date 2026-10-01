/** @vitest-environment jsdom */

import { createElement } from "react";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HandoffControls, type HandoffControlsProps } from "./HandoffControls";
import type { HandoffView } from "./handoffTypes";

const ID = "00000000-0000-0000-0000-000000000001";
const SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
const STAMP = "2026-09-06T15:00:00+00:00";
const RAW_CODE = "do-not-echo-this";
const DUMMY_ERROR = "https://example.com/raw-error-url";

function renderedText(node: HTMLElement): string {
  return node.textContent ?? "";
}

function view(overrides: Partial<HandoffView> = {}): HandoffView {
  return {
    id: ID,
    state: "prepared",
    attempts: 0,
    url: null,
    error_code: null,
    expires_at: null,
    retry_allowed: false,
    ...overrides,
  };
}

function buttonNamed(root: HTMLElement, name: string): HTMLButtonElement {
  return within(root).getByRole("button", { name, exact: true }) as HTMLButtonElement;
}

function mount(
  props: Partial<Pick<HandoffControlsProps, "view" | "error" | "pending" | "canStart">> = {},
): {
  rendered: RenderResult;
  onStart: ReturnType<typeof vi.fn<() => void>>;
  onRetry: ReturnType<typeof vi.fn<() => void>>;
} {
  const onStart = vi.fn<() => void>();
  const onRetry = vi.fn<() => void>();
  const rendered = render(
    createElement(HandoffControls, {
      view: props.view ?? null,
      error: props.error ?? null,
      pending: props.pending ?? false,
      canStart: props.canStart ?? false,
      onStart,
      onRetry,
    }),
  );
  return { rendered, onStart, onRetry };
}

afterEach(cleanup);

describe("HandoffControls", () => {
  it("shows start when canStart is true and view is null", () => {
    const { rendered, onStart, onRetry } = mount({ canStart: true });
    const start = buttonNamed(rendered.container, "Create shopping list");
    expect(start.type).toBe("button");
    expect(start.className).toBe("rebuild-estimate");
    expect(start.disabled).toBe(false);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(1);
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onRetry).not.toHaveBeenCalled();
    rendered.unmount();
  });

  it("hides start when canStart is false and view is null", () => {
    const { rendered } = mount({ canStart: false });
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(0);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(renderedText(rendered.container)).not.toContain("Create shopping list");
    rendered.unmount();
  });

  it("disables start while pending and shows pending status", () => {
    const { rendered, onStart } = mount({ canStart: true, pending: true });
    const start = buttonNamed(rendered.container, "Create shopping list");
    expect(start.disabled).toBe(true);
    expect(renderedText(rendered.container)).toContain("The shopping link request is in progress.");
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(onStart).not.toHaveBeenCalled();
    rendered.unmount();
  });

  it("shows retry for an uncertain view and does not start", () => {
    const { rendered, onStart, onRetry } = mount({
      view: view({
        state: "uncertain",
        attempts: 1,
        error_code: RAW_CODE,
        retry_allowed: true,
      }),
    });
    const retry = buttonNamed(rendered.container, "Retry shopping list");
    expect(retry.type).toBe("button");
    expect(retry.className).toBe("rebuild-estimate");
    expect(retry.disabled).toBe(false);
    expect(renderedText(rendered.container)).toContain(
      "The shopping link is uncertain. Retry only if you choose to.",
    );
    expect(renderedText(rendered.container)).not.toContain(RAW_CODE);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(1);
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onStart).not.toHaveBeenCalled();
    rendered.unmount();
  });

  it("shows retry for a failed view and hides the link", () => {
    const { rendered } = mount({
      view: view({
        state: "failed",
        attempts: 1,
        error_code: RAW_CODE,
        retry_allowed: true,
      }),
    });
    buttonNamed(rendered.container, "Retry shopping list");
    expect(renderedText(rendered.container)).toContain("The shopping link request failed.");
    expect(renderedText(rendered.container)).not.toContain(RAW_CODE);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(
      within(rendered.container).queryAllByRole("button", { name: "Create shopping list" }),
    ).toHaveLength(0);
    rendered.unmount();
  });

  it("shows one shopping link for a succeeded view", () => {
    const { rendered } = mount({
      view: view({
        state: "succeeded",
        attempts: 1,
        url: SUCCESS_URL,
        expires_at: STAMP,
        retry_allowed: false,
      }),
    });
    const links = within(rendered.container).queryAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]?.getAttribute("href")).toBe(SUCCESS_URL);
    expect(links[0]?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(links[0]?.getAttribute("target")).toBe("_blank");
    expect(links[0]?.className).toBe("handoff-link");
    expect(renderedText(links[0] as HTMLElement)).toBe("Open shopping list");
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(0);
    rendered.unmount();
  });

  it("shows retry for a succeeded view that allows retry", () => {
    const { rendered } = mount({
      view: view({ state: "succeeded", attempts: 1, retry_allowed: true }),
    });
    buttonNamed(rendered.container, "Retry shopping list");
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(
      within(rendered.container).queryAllByRole("button", { name: "Create shopping list" }),
    ).toHaveLength(0);
    rendered.unmount();
  });

  it("shows dispatching status without start, retry, or a link", () => {
    const { rendered } = mount({
      view: view({ state: "dispatching", attempts: 1 }),
    });
    expect(renderedText(rendered.container)).toContain("The shopping link request is in progress.");
    expect(within(rendered.container).queryAllByRole("button")).toHaveLength(0);
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    rendered.unmount();
  });

  it("renders the error string unchanged", () => {
    const { rendered } = mount({ error: DUMMY_ERROR, canStart: true });
    expect(renderedText(rendered.container)).toContain(DUMMY_ERROR);
    const errors = rendered.container.querySelectorAll<HTMLElement>(".form-error");
    expect(errors).toHaveLength(1);
    expect(errors[0]?.className).toBe("form-error");
    expect(renderedText(errors[0] as HTMLElement)).toBe(DUMMY_ERROR);
    expect(errors[0]?.getAttribute("role")).toBe("status");
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    rendered.unmount();
  });

  it("disables retry while pending", () => {
    const { rendered, onRetry } = mount({
      view: view({
        state: "uncertain",
        attempts: 1,
        retry_allowed: true,
      }),
      pending: true,
    });
    const retry = buttonNamed(rendered.container, "Retry shopping list");
    expect(retry.disabled).toBe(true);
    expect(renderedText(rendered.container)).toContain("The shopping link request is in progress.");
    expect(within(rendered.container).queryAllByRole("link")).toHaveLength(0);
    expect(onRetry).not.toHaveBeenCalled();
    rendered.unmount();
  });
});
