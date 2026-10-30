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
        return { ok: true, status: 200, json: async () => ({ plan_revision_id: "rev-1" }) };
      }
      if (url === "/api/grocery/kroger/cart/preview") {
        const body = preview ?? { items: [ITEM], unmatched: [{ ingredient_id: "x", name: "Saffron" }] };
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
    expect(await screen.findByText("Connect Kroger again.")).toBeTruthy();
    status = 503;
    send();
    expect(await screen.findByText("Kroger is unavailable. Try again.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Send/ })).toBeTruthy();
  });

  it("offers Retry after an unconfirmed send and resends once per click", async () => {
    const calls = stub(() => 504);
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
    expect(
      await screen.findByText("Kroger did not confirm. Check your Kroger cart before you retry."),
    ).toBeTruthy();
    await settle();
    const adds = (): number => calls.filter((call) => call.url.endsWith("/cart/add")).length;
    expect(adds()).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await settle();
    expect(adds()).toBe(2);
  });

  it("disables Send while the request runs", async () => {
    let finish: () => void = () => undefined;
    stub(() => new Promise<number>((resolve) => { finish = () => { resolve(204); }; }));
    render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    fireEvent.click(screen.getByRole("button", { name: /^Send/ }));
    expect((screen.getByRole("button", { name: /^Send/ }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { finish(); });
    await screen.findByText(/^Added to your Kroger cart/);
  });

  it("drops the preview when the store changes", async () => {
    stub(() => 204);
    const view = render(<KrogerCart state={initialPlanState()} locationId="01400943" />);
    await showPreview();
    view.rerender(<KrogerCart state={initialPlanState()} locationId="01400944" />);
    expect(screen.queryByRole("list", { name: "Kroger cart preview" })).toBeNull();
  });
});
