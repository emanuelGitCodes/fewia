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
  });

  it("shows the unavailable line for a malformed preview", async () => {
    stub(() => 204, { items: [], unmatched: [], extra: 1 });
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

  it("disables Send while the request runs", async () => {
    let finish: () => void = () => undefined;
    stub(
      () =>
        new Promise<number>((resolve) => {
          finish = () => {
            resolve(204);
          };
        }),
    );
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
    expect((screen.getByRole("button", { name: /^Send/ }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      finish();
    });
    await screen.findByText(/^Added to your Kroger cart/);
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
      expect(previewButton().disabled).toBe(true);
      fireEvent.click(previewButton());
      expect(calls.filter((call) => call.url.endsWith("/preview")).length).toBe(1);
      await release(204);
      expect(previewButton().disabled).toBe(false);
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
      expect(previewButton().disabled).toBe(false);
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
    stub(() => 204, { items: [], unmatched: [] });
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
    expect(await screen.findByText("No Kroger items found for this plan.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Send/ })).toBeNull();
  });

  it("shows the save line, not the Kroger line, when the plan save fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500 })));
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Kroger cart" }));
    expect(await screen.findByText("Could not save the plan. Try again.")).toBeTruthy();
    expect(screen.queryByText("Kroger is unavailable. Try again.")).toBeNull();
  });
});
