// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KrogerCart } from "./KrogerCart";
import { initialPlanState } from "./planModel";

const ITEM = {
  ingredient_id: "beans",
  name: "Black beans",
  upc: "0001111041600",
  description: "Kroger Black Beans",
  size: "15 oz",
  quantity: 2,
};

type Calls = { url: string; init?: RequestInit }[];

function stub(addStatus: () => number | Promise<number>, preview?: unknown): Calls {
  const calls: Calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/api/grocery/plans") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ plan_revision_id: "rev-1" }),
        };
      }
      if (url === "/api/grocery/kroger/cart/preview") {
        const body = preview ?? {
          items: [ITEM],
          unmatched: [{ ingredient_id: "x", name: "Saffron" }],
          source: "live",
        };
        return { ok: true, status: 200, json: async () => body };
      }
      return { ok: false, status: await addStatus() };
    }),
  );
  return calls;
}

async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function showPreview(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
  await screen.findByRole("list", { name: "Kroger cart preview" });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("KrogerCart", () => {
  it("hides the preview button without a store or without meals", () => {
    const none = render(<KrogerCart state={initialPlanState()} locationId={null} />);
    expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
    none.unmount();
    render(<KrogerCart state={{ ...initialPlanState(), meals: [] }} locationId="01400943" />);
    expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("saves the plan, then previews, and renders items and unmatched lines", async () => {
    const calls = stub(() => 204);
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    expect(calls.map((call) => call.url)).toEqual([
      "/api/grocery/plans",
      "/api/grocery/kroger/cart/preview",
    ]);
    expect(JSON.parse(calls[1]?.init?.body as string)).toEqual({
      plan_revision_id: "rev-1",
      location_id: "01400943",
    });
    expect(screen.getByText("Black beans")).toBeTruthy();
    expect(screen.getByText("Kroger Black Beans")).toBeTruthy();
    expect(screen.getByText("15 oz")).toBeTruthy();
    expect(screen.getByText("Quantity 2")).toBeTruthy();
    expect(screen.getByText("No Kroger match: Saffron.")).toBeTruthy();
    expect(screen.getByRole("status").textContent)
      .toBe("Kroger cart preview ready: 1 item. 1 ingredient has no Kroger match.");
  });

  it.each([false, true])("announces preview progress and preserves focus when moved=%s", async (moveFocus) => {
    let finish: (value: unknown) => void = () => undefined;
    const pending = new Promise<unknown>((resolve) => { finish = resolve; });
    const calls = stub(() => 204, pending);
    render(<><KrogerCart state={initialPlanState()} locationId="01400943" /><button>Elsewhere</button></>);
    const preview = screen.getByRole("button", { name: "Preview Kroger cart" });
    const status = screen.getByRole("status");
    preview.focus();
    await act(async () => { fireEvent.click(preview); });
    expect(status.textContent).toBe("Preparing Kroger cart preview.");
    expect(preview.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(preview);
    fireEvent.click(preview);
    expect(calls.filter((call) => call.url.endsWith("/preview"))).toHaveLength(1);
    const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
    if (moveFocus) elsewhere.focus();
    await act(async () => { finish({ items: [ITEM], unmatched: [], source: "live" }); });
    expect(status.textContent).toBe("Kroger cart preview ready: 1 item.");
    expect(document.activeElement).toBe(moveFocus ? elsewhere : preview);
    expect(preview.getAttribute("aria-disabled")).toBe("false");
  });

  it("shows the unavailable line for a malformed preview", async () => {
    stub(() => 204, { items: [], unmatched: [], source: "live", extra: 1 });
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
    expect(await screen.findByText("Kroger is unavailable. Try again.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
  });

  it("sends the previewed items and hides Send after success", async () => {
    const calls = stub(() => 204);
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    fireEvent.click(screen.getByRole("button", { name: "Send 1 item to Kroger cart" }));
    expect(
      await screen.findByText("Added to your Kroger cart. Review and check out on kroger.com."),
    ).toBeTruthy();
    expect(JSON.parse(calls[2]?.init?.body as string)).toEqual({
      items: [{ upc: "0001111041600", quantity: 2 }],
    });
    expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
  });

  it("reports not connected and unavailable, keeping Send", async () => {
    let status = 409;
    stub(() => status);
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    const send = (): void => {
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
    };
    send();
    expect(
      await screen.findByText("Your Kroger sign-in expired. Disconnect, then connect Kroger again."),
    ).toBeTruthy();
    status = 503;
    send();
    expect(await screen.findByText("Kroger is unavailable. Try again.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Send/ })).toBeTruthy();
  });

  it.each([500, 501, 502, 504, 505, 599])(
    "requires an explicit Retry after an unconfirmed HTTP %s send",
    async (initialStatus) => {
      let status = initialStatus;
      const calls = stub(() => status);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      const adds = (): number => calls.filter((call) => call.url.endsWith("/cart/add")).length;
      expect(adds()).toBe(0);
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      expect(
        await screen.findByText("Kroger did not confirm. Check your Kroger cart before you retry."),
      ).toBeTruthy();
      await settle();
      expect(adds()).toBe(1);
      expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
      expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
      await settle();
      expect(adds()).toBe(1);
      status = 204;
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(
        await screen.findByText("Added to your Kroger cart. Review and check out on kroger.com."),
      ).toBeTruthy();
      await settle();
      expect(adds()).toBe(2);
      expect(screen.queryByRole("button", { name: /^(Send|Retry)/ })).toBeNull();
    },
  );

  it("guards Send and retains focus while the request runs", async () => {
    let finish: () => void = () => undefined;
    const calls = stub(
      () =>
        new Promise<number>((resolve) => {
          finish = () => {
            resolve(204);
          };
        }),
    );
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    const send = screen.getByRole("button", { name: /^Send/ });
    const status = screen.getByRole("status");
    send.focus();
    fireEvent.click(send);
    fireEvent.click(send);
    expect(send.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(send);
    expect(status.textContent).toBe("Sending items to Kroger cart.");
    expect(calls.filter((call) => call.url.endsWith("/cart/add"))).toHaveLength(1);
    await act(async () => {
      finish();
    });
    await screen.findByText(/^Added to your Kroger cart/);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Preview Kroger cart" }));
  });

  describe.each(["Send", "Retry"] as const)("focus after %s", (action) => {
    it.each([204, 422, 504])("follows the remaining action after HTTP %s", async (result) => {
      let finish: (value: number) => void = () => undefined;
      let pending = action === "Send";
      stub(() => pending ? new Promise<number>((resolve) => { finish = resolve; }) : 504);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      if (action === "Retry") {
        fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
        await screen.findByRole("button", { name: "Retry" });
        pending = true;
      }
      const button = screen.getByRole("button", { name: action === "Send" ? /^Send/ : "Retry" });
      button.focus();
      fireEvent.click(button);
      expect(document.activeElement).toBe(button);
      expect(button.getAttribute("aria-disabled")).toBe("true");
      expect(screen.getByRole("status").textContent).toBe("Sending items to Kroger cart.");
      await act(async () => { finish(result); });
      const target = screen.getByRole("button", { name: result === 504 ? "Retry" : "Preview Kroger cart" });
      expect(document.activeElement).toBe(target);
      expect(target.getAttribute("aria-disabled")).toBe("false");
    });

    it.each([204, 422, 504])("keeps user-moved focus after HTTP %s", async (result) => {
      let finish: (value: number) => void = () => undefined;
      let pending = action === "Send";
      stub(() => pending ? new Promise<number>((resolve) => { finish = resolve; }) : 504);
      render(<><KrogerCart state={initialPlanState()} locationId="01400943" /><button>Elsewhere</button></>);
      await showPreview();
      if (action === "Retry") {
        fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
        await screen.findByRole("button", { name: "Retry" });
        pending = true;
      }
      const button = screen.getByRole("button", { name: action === "Send" ? /^Send/ : "Retry" });
      button.focus();
      fireEvent.click(button);
      const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
      elsewhere.focus();
      await act(async () => { finish(result); });
      expect(document.activeElement).toBe(elsewhere);
    });
  });

  it.each(["store", "no-store", "plan"] as const)("resets actions and keeps local focus during a pending send across a %s change", async (change) => {
    let finish: () => void = () => undefined;
    const calls = stub(() => new Promise<number>((resolve) => { finish = () => { resolve(204); }; }));
    const state = initialPlanState();
    const view = render(<KrogerCart state={state} locationId="01400943" />);
    await showPreview();
    const send = screen.getByRole("button", { name: /^Send/ });
    send.focus();
    fireEvent.click(send);
    view.rerender(<KrogerCart
      state={change === "plan" ? { ...state, meals: [] } : state}
      locationId={change === "no-store" ? null : "01400944"}
    />);
    const preview = screen.queryByRole("button", { name: "Preview Kroger cart" });
    const target = change === "store" ? preview : screen.getByRole("group", { name: "Kroger cart" });
    expect(document.activeElement).toBe(target);
    expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
    expect(screen.queryByRole("list", { name: "Kroger cart preview" })).toBeNull();
    if (change === "store") {
      expect(preview?.getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(preview as HTMLButtonElement);
    } else {
      expect(preview).toBeNull();
    }
    expect(calls.filter((call) => call.url.endsWith("/preview"))).toHaveLength(1);
    await act(async () => { finish(); });
    expect(document.activeElement).toBe(target);
    if (change === "store") {
      expect(preview?.getAttribute("aria-disabled")).toBe("false");
    } else {
      expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
    }
  });

  describe.each(["no-store", "empty-plan"] as const)("after a %s change", (change) => {
    it.each([false, true])("hides a used Preview and preserves focus when moved=%s", async (moveFocus) => {
      stub(() => 204);
      const state = initialPlanState();
      const view = render(<><KrogerCart state={state} locationId="01400943" /><button>Elsewhere</button></>);
      await showPreview();
      const preview = screen.getByRole("button", { name: "Preview Kroger cart" });
      const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
      preview.focus();
      if (moveFocus) elsewhere.focus();
      view.rerender(<><KrogerCart
        state={change === "empty-plan" ? { ...state, meals: [] } : state}
        locationId={change === "no-store" ? null : "01400943"}
      /><button>Elsewhere</button></>);
      expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
      expect(screen.queryByRole("button", { name: /^(Send|Retry)/ })).toBeNull();
      expect(screen.queryByRole("list", { name: "Kroger cart preview" })).toBeNull();
      expect(screen.getByRole("status").textContent).toBe("");
      expect(document.activeElement).toBe(moveFocus ? elsewhere : screen.getByRole("group", { name: "Kroger cart" }));
    });
  });

  it("drops the preview when the store changes", async () => {
    stub(() => 204);
    const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    view.rerender(<KrogerCart state={initialPlanState()} locationId="01400944" />);
    expect(screen.queryByRole("list", { name: "Kroger cart preview" })).toBeNull();
  });

  it("drops the preview when the plan changes", async () => {
    stub(() => 204);
    const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    view.rerender(
      <KrogerCart
        state={{ ...initialPlanState(), budgetCents: 12345 }}
        locationId="01400943"
      />,
    );
    expect(screen.queryByRole("list", { name: "Kroger cart preview" })).toBeNull();
  });

  it("aborts the preview requests on unmount", async () => {
    const calls = stub(() => 204);
    const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    const signal = calls[0]?.init?.signal;
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("rejected adds ask for a new preview and offer no Retry", async () => {
    stub(() => 422);
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
    expect(
      await screen.findByText("Kroger could not take these items. Preview the cart again."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^(Send|Retry)/ })).toBeNull();
  });

  describe("a send that settles after the plan or store changed", () => {
    const adds = (calls: Calls): number =>
      calls.filter((call) => call.url.endsWith("/cart/add")).length;
    const previewButton = (): HTMLButtonElement =>
      screen.getByRole("button", {
        name: "Preview Kroger cart",
      }) as HTMLButtonElement;
    const other = <KrogerCart state={initialPlanState()} locationId="01400944" />;

    // Each add waits for release(status); calls are released in order.
    function gated(): {
      release: (status: number) => Promise<void>;
      calls: Calls;
    } {
      const pending: ((status: number) => void)[] = [];
      const calls = stub(
        () =>
          new Promise<number>((resolve) => {
            pending.push(resolve);
          }),
      );
      return {
        calls,
        release: async (status) => {
          await act(async () => {
            pending.shift()?.(status);
          });
          await settle();
        },
      };
    }

    it("keeps every button disabled until it settles, and never resends", async () => {
      const { release, calls } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      view.rerender(other);
      expect(previewButton().getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(previewButton());
      expect(calls.filter((call) => call.url.endsWith("/preview")).length).toBe(1);
      await release(204);
      expect(previewButton().getAttribute("aria-disabled")).toBe("false");
      expect(adds(calls)).toBe(1);
    });

    it("shows the added line for a late added", async () => {
      const { release } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      view.rerender(other);
      await release(204);
      expect(screen.getByText(/^Added to your Kroger cart/)).toBeTruthy();
      expect(screen.queryByRole("button", { name: /^(Send|Retry)/ })).toBeNull();
    });

    it("shows the unknown line for a late unknown, without Retry", async () => {
      const { release } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      view.rerender(other);
      await release(504);
      expect(screen.getByText(/^Kroger did not confirm/)).toBeTruthy();
      expect(screen.queryByRole("button", { name: /^(Send|Retry)/ })).toBeNull();
    });

    it("shows nothing for a late not_connected", async () => {
      const { release } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      view.rerender(other);
      await release(409);
      expect(screen.getByRole("status").textContent).toBe("");
      expect(previewButton().getAttribute("aria-disabled")).toBe("false");
    });

    it("does not overwrite a newer send's line", async () => {
      const { release } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      view.rerender(other);
      await release(204);
      fireEvent.click(previewButton());
      await screen.findByRole("list", { name: "Kroger cart preview" });
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      await release(504);
      expect(screen.getByText(/^Kroger did not confirm/)).toBeTruthy();
      expect(screen.queryByText(/^Added to your Kroger cart/)).toBeNull();
    });

    it("makes no further request and throws nothing when it settles after unmount", async () => {
      const { release, calls } = gated();
      const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      await showPreview();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      const before = calls.length;
      view.unmount();
      await expect(release(204)).resolves.toBeUndefined();
      expect(calls.length).toBe(before);
      expect(screen.queryByRole("status")).toBeNull();
    });
  });

  it("says so when the preview has no items and no unmatched lines", async () => {
    stub(() => 204, { items: [], unmatched: [], source: "live" });
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
    expect(await screen.findByText("No Kroger items found for this plan.")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("No Kroger items found for this plan.");
    expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
  });

  describe("fixture source", () => {
    const FIXTURE = { items: [ITEM], unmatched: [], source: "fixture" };

    it("labels a fixture preview and keeps the live text away", async () => {
      stub(() => 204, FIXTURE);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
      await screen.findByRole("list", { name: "Fixture cart preview" });
      expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
      expect(screen.getByRole("status").textContent).toBe("Fixture cart preview ready: 1 item.");
      expect(screen.getByRole("button", { name: "Send 1 item to fixture cart" })).toBeTruthy();
    });

    it("shows the fixture success text after a fixture preview is added", async () => {
      const calls = stub(() => 204, FIXTURE);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
      await screen.findByRole("list", { name: "Fixture cart preview" });
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      const line = await screen.findByText("Added to the fixture cart. No Kroger cart changed.");
      expect(line.textContent).not.toContain("kroger.com");
      expect(calls.filter((call) => call.url.endsWith("/cart/add"))).toHaveLength(1);
      expect(screen.queryByText(/kroger\.com/)).toBeNull();
    });

    it("labels from the preview, not the capability", async () => {
      stub(() => 204, FIXTURE);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" krogerMode="live" />);
      fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
      await screen.findByRole("list", { name: "Fixture cart preview" });
      expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
    });

    it("shows no fixture label for a live preview even in fixture mode", async () => {
      stub(() => 204);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" krogerMode="fixture" />);
      fireEvent.click(screen.getByRole("button", { name: "Preview fixture cart" }));
      await screen.findByRole("list", { name: "Kroger cart preview" });
      expect(screen.queryByText("FIXTURE, NOT KROGER")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      expect(
        await screen.findByText("Added to your Kroger cart. Review and check out on kroger.com."),
      ).toBeTruthy();
    });

    it("says so when a fixture send is not confirmed", async () => {
      stub(() => 504, FIXTURE);
      render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
      fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
      await screen.findByRole("list", { name: "Fixture cart preview" });
      fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
      expect(
        await screen.findByText("The fixture cart did not confirm. No Kroger cart changed."),
      ).toBeTruthy();
    });
  });

  it("shows the save line, not the Kroger line, when the plan save fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 })));
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
    expect(await screen.findByText("Could not save the plan. Try again.")).toBeTruthy();
    expect(screen.queryByText("Kroger is unavailable. Try again.")).toBeNull();
  });
});
