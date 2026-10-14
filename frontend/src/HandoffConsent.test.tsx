/** @vitest-environment jsdom */

import { createElement, StrictMode, useState, type JSX, type MouseEvent } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffConsent } from "./HandoffConsent";

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement): void {
      this.open = true;
      this.querySelector<HTMLButtonElement>("button")?.focus();
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement): void {
      this.open = false;
    },
  });
});

afterEach(cleanup);

function mount(): { onConfirm: ReturnType<typeof vi.fn<() => void>>; trigger: HTMLElement } {
  const onConfirm = vi.fn<() => void>();
  function Host(): JSX.Element {
    const [open, setOpen] = useState(false);
    return createElement(
      "div",
      null,
      createElement(
        "button",
        {
          type: "button",
          onClick: (event: MouseEvent<HTMLButtonElement>) => {
            event.currentTarget.focus();
            setOpen(true);
          },
        },
        "Create shopping list",
      ),
      open ? createElement(HandoffConsent, { onConfirm, onCancel: () => setOpen(false) }) : null,
    );
  }
  render(createElement(StrictMode, null, createElement(Host)));
  const trigger = screen.getByRole("button", { name: "Create shopping list" });
  fireEvent.click(trigger);
  return { onConfirm, trigger };
}

describe("HandoffConsent", () => {
  it("opens a labelled native dialog with disclosure and Cancel focused", () => {
    const { onConfirm } = mount();
    const dialog = screen.getByRole("dialog", { name: "Create shopping list?" });
    expect((dialog as HTMLDialogElement).open).toBe(true);
    expect(dialog.getAttribute("aria-describedby")).toBe("handoff-consent-description");
    expect(dialog.textContent).toContain("ingredients and quantities with Instacart");
    expect(dialog.textContent).toContain("This creates no purchase.");
    expect(dialog.textContent).toContain("Store prices are not verified.");
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it.each(["Cancel", "Escape"])("closes on %s and returns focus without confirmation", (action) => {
    const { onConfirm, trigger } = mount();
    const dialog = screen.getByRole("dialog");
    if (action === "Cancel") {
      fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    } else {
      fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));
    }
    expect(screen.queryByRole("dialog")).toBeNull();
    expect((dialog as HTMLDialogElement).open).toBe(false);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(trigger);
  });

  it("does not focus a trigger that is disabled when the dialog closes", () => {
    const { trigger } = mount();
    const dialog = screen.getByRole("dialog");
    (trigger as HTMLButtonElement).disabled = true;
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).not.toBe(trigger);
  });

  it("confirms once and closes even if the same control is clicked again", () => {
    const { onConfirm } = mount();
    const button = screen.getByRole("button", { name: "Confirm shopping list" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
