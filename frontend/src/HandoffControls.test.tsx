/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { describe, expect, it, vi } from "vitest";
import { HandoffControls, type HandoffControlsProps } from "./HandoffControls";
import type { HandoffView } from "./handoffTypes";

const ID = "00000000-0000-0000-0000-000000000001";
const SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
const STAMP = "2026-09-06T15:00:00+00:00";
const RAW_CODE = "do-not-echo-this";
const DUMMY_ERROR = "https://example.com/raw-error-url";

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
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

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
}

function mount(
  props: Partial<Pick<HandoffControlsProps, "view" | "error" | "pending" | "canStart">> = {},
): {
  renderer: ReactTestRenderer;
  onStart: ReturnType<typeof vi.fn<() => void>>;
  onRetry: ReturnType<typeof vi.fn<() => void>>;
} {
  const onStart = vi.fn<() => void>();
  const onRetry = vi.fn<() => void>();
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(
      createElement(HandoffControls, {
        view: props.view ?? null,
        error: props.error ?? null,
        pending: props.pending ?? false,
        canStart: props.canStart ?? false,
        onStart,
        onRetry,
      }),
    );
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return { renderer, onStart, onRetry };
}

describe("HandoffControls", () => {
  it("shows start when canStart is true and view is null", () => {
    const { renderer, onStart, onRetry } = mount({ canStart: true });
    const start = buttonNamed(renderer.root, "Create shopping list");
    expect(start.props.type).toBe("button");
    expect(start.props.className).toBe("rebuild-estimate");
    expect(start.props.disabled).toBe(false);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(renderer.root.findAllByType("button")).toHaveLength(1);
    act(() => {
      (start.props.onClick as (() => void) | undefined)?.();
    });
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(onRetry).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("hides start when canStart is false and view is null", () => {
    const { renderer } = mount({ canStart: false });
    expect(renderer.root.findAllByType("button")).toHaveLength(0);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(childText(renderer.root)).not.toContain("Create shopping list");
    renderer.unmount();
  });

  it("disables start while pending and shows pending status", () => {
    const { renderer, onStart } = mount({ canStart: true, pending: true });
    const start = buttonNamed(renderer.root, "Create shopping list");
    expect(start.props.disabled).toBe(true);
    expect(childText(renderer.root)).toContain("The shopping link request is in progress.");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(onStart).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows retry for an uncertain view and does not start", () => {
    const { renderer, onStart, onRetry } = mount({
      view: view({
        state: "uncertain",
        attempts: 1,
        error_code: RAW_CODE,
        retry_allowed: true,
      }),
    });
    const retry = buttonNamed(renderer.root, "Retry shopping list");
    expect(retry.props.type).toBe("button");
    expect(retry.props.className).toBe("rebuild-estimate");
    expect(retry.props.disabled).toBe(false);
    expect(childText(renderer.root)).toContain(
      "The shopping link is uncertain. Retry only if you choose to.",
    );
    expect(childText(renderer.root)).not.toContain(RAW_CODE);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(renderer.root.findAllByType("button")).toHaveLength(1);
    act(() => {
      (retry.props.onClick as (() => void) | undefined)?.();
    });
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onStart).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("shows retry for a failed view and hides the link", () => {
    const { renderer } = mount({
      view: view({
        state: "failed",
        attempts: 1,
        error_code: RAW_CODE,
        retry_allowed: true,
      }),
    });
    buttonNamed(renderer.root, "Retry shopping list");
    expect(childText(renderer.root)).toContain("The shopping link request failed.");
    expect(childText(renderer.root)).not.toContain(RAW_CODE);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(renderer.root.findAll((node) => childText(node) === "Create shopping list")).toHaveLength(
      0,
    );
    renderer.unmount();
  });

  it("shows one shopping link for a succeeded view", () => {
    const { renderer } = mount({
      view: view({
        state: "succeeded",
        attempts: 1,
        url: SUCCESS_URL,
        expires_at: STAMP,
        retry_allowed: false,
      }),
    });
    const links = renderer.root.findAllByType("a");
    expect(links).toHaveLength(1);
    expect(links[0]?.props.href).toBe(SUCCESS_URL);
    expect(links[0]?.props.rel).toBe("noopener noreferrer");
    expect(links[0]?.props.target).toBe("_blank");
    expect(links[0]?.props.className).toBe("handoff-link");
    expect(childText(links[0] as ReactTestInstance)).toBe("Open shopping list");
    expect(renderer.root.findAllByType("button")).toHaveLength(0);
    renderer.unmount();
  });

  it("shows retry for a succeeded view that allows retry", () => {
    const { renderer } = mount({
      view: view({ state: "succeeded", attempts: 1, retry_allowed: true }),
    });
    buttonNamed(renderer.root, "Retry shopping list");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(renderer.root.findAll((node) => childText(node) === "Create shopping list")).toHaveLength(
      0,
    );
    renderer.unmount();
  });

  it("shows dispatching status without start, retry, or a link", () => {
    const { renderer } = mount({
      view: view({ state: "dispatching", attempts: 1 }),
    });
    expect(childText(renderer.root)).toContain("The shopping link request is in progress.");
    expect(renderer.root.findAllByType("button")).toHaveLength(0);
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("renders the error string unchanged", () => {
    const { renderer } = mount({ error: DUMMY_ERROR, canStart: true });
    expect(childText(renderer.root)).toContain(DUMMY_ERROR);
    const errors = renderer.root.findAll(
      (node) => node.type === "p" && (node.props as { className?: string }).className === "form-error",
    );
    expect(errors).toHaveLength(1);
    expect(childText(errors[0] as ReactTestInstance)).toBe(DUMMY_ERROR);
    expect(errors[0]?.props.role).toBe("status");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    renderer.unmount();
  });

  it("disables retry while pending", () => {
    const { renderer, onRetry } = mount({
      view: view({
        state: "uncertain",
        attempts: 1,
        retry_allowed: true,
      }),
      pending: true,
    });
    const retry = buttonNamed(renderer.root, "Retry shopping list");
    expect(retry.props.disabled).toBe(true);
    expect(childText(renderer.root)).toContain("The shopping link request is in progress.");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
    expect(onRetry).not.toHaveBeenCalled();
    renderer.unmount();
  });
});
