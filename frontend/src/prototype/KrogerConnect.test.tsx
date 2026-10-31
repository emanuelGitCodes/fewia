// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KrogerConnect } from "./KrogerConnect";
import { initialPlanState } from "./planModel";
import { PLAN_CHECKPOINT_KEY, PLAN_SAVE_WARNING, readReturnPlan } from "./planCheckpoint";

type Handler = (url: string, init?: RequestInit) => Promise<Partial<Response>>;

function stub(handler: Handler): void {
  vi.stubGlobal("fetch", vi.fn(handler));
}

function status(connected: unknown): Promise<Partial<Response>> {
  return Promise.resolve({ ok: true, status: 200, json: async () => ({ connected }) });
}

// A macrotask turn drains every pending promise, so the read has settled afterwards.
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("KrogerConnect", () => {
  it("renders nothing while loading, when not configured, and for a malformed body", async () => {
    stub(() => new Promise(() => undefined));
    const { container, unmount } = render(<KrogerConnect plan={initialPlanState()} />);
    expect(container.firstChild).toBeNull();
    unmount();

    stub(async () => ({ ok: false, status: 503 }));
    const off = render(<KrogerConnect plan={initialPlanState()} />);
    await settle();
    expect(off.container.firstChild).toBeNull();
    off.unmount();

    for (const body of ["yes", undefined]) {
      stub(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => (body === undefined ? { connected: false, extra: 1 } : { connected: body }),
        }),
      );
      const bad = render(<KrogerConnect plan={initialPlanState()} />);
      await settle();
      expect(bad.container.firstChild).toBeNull();
      bad.unmount();
    }
  });

  it("links to the connect route when not connected", async () => {
    stub(() => status(false));
    render(<KrogerConnect plan={initialPlanState()} />);
    const link = await screen.findByRole("link", { name: "Connect Kroger" });
    expect(link.getAttribute("href")).toBe("/api/grocery/kroger/connect");
  });

  it("saves and verifies the current plan synchronously before permitting navigation", async () => {
    stub(() => status(false));
    const plan = { ...initialPlanState(), meals: [], budgetInput: "25", budgetCents: 2500 };
    render(<KrogerConnect plan={plan} />);
    const link = await screen.findByRole("link", { name: "Connect Kroger" });
    let allowed = false;
    const stopNavigation = (event: MouseEvent): void => {
      allowed = !event.defaultPrevented;
      expect(window.sessionStorage.getItem(PLAN_CHECKPOINT_KEY)).not.toBeNull();
      event.preventDefault();
    };
    document.addEventListener("click", stopNavigation, { once: true });
    fireEvent.click(link);
    expect(allowed).toBe(true);
    window.history.replaceState(null, "", "/prototype?kroger=connected");
    expect(readReturnPlan().state).toEqual(plan);
  });

  it.each(["write", "read", "mismatch", "access"])("warns once after a storage %s failure, then permits sign-in", async (failure) => {
    stub(() => status(false));
    render(<KrogerConnect plan={initialPlanState()} />);
    const link = await screen.findByRole("link", { name: "Connect Kroger" });
    const storage = window.sessionStorage;
    if (failure === "access") {
      vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => { throw new Error("private"); });
    } else {
      vi.stubGlobal("sessionStorage", {
        setItem: (key: string, value: string): void => {
          if (failure === "write") throw new Error("private");
          storage.setItem(key, value);
        },
        getItem: (key: string): string | null => {
          if (failure === "read") throw new Error("private");
          return failure === "mismatch" ? null : storage.getItem(key);
        },
      });
    }
    let prevented = false;
    document.addEventListener("click", (event) => {
      prevented = event.defaultPrevented;
      event.preventDefault();
    }, { once: true });
    fireEvent.click(link);
    expect(prevented).toBe(true);
    const warning = screen.getByText(PLAN_SAVE_WARNING);
    expect(warning.getAttribute("aria-live")).toBe("polite");
    expect(warning.textContent).not.toContain("private");
    // Storage still fails, yet the next click follows the link.
    let allowed = false;
    document.addEventListener("click", (event) => {
      allowed = !event.defaultPrevented;
      event.preventDefault();
    }, { once: true });
    fireEvent.click(link);
    expect(allowed).toBe(true);
  });

  it("shows the cart preview button only while connected", async () => {
    const plan = initialPlanState();
    stub(() => status(false));
    const off = render(<KrogerConnect plan={plan} locationId="01400943" />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
    off.unmount();

    stub(() => status(true));
    render(<KrogerConnect plan={plan} locationId="01400943" />);
    expect(await screen.findByRole("button", { name: "Preview Kroger cart" })).toBeTruthy();
  });

  it("shows the connected state and disconnects", async () => {
    let connected = true;
    stub(async (_url, init) => {
      if (init?.method === "DELETE") {
        connected = false;
        return { ok: true, status: 204 };
      }
      return status(connected);
    });
    render(<KrogerConnect plan={initialPlanState()} />);
    expect(await screen.findByText("Kroger account connected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("link", { name: "Connect Kroger" })).toBeTruthy();
  });

  it("keeps the button and explains when disconnect fails", async () => {
    stub(async (_url, init) =>
      init?.method === "DELETE" ? { ok: false, status: 500 } : status(true),
    );
    render(<KrogerConnect plan={initialPlanState()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect(await screen.findByText("Could not disconnect Kroger. Try again.")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it("disables Disconnect while the request is in flight", async () => {
    let finish: () => void = () => undefined;
    stub((_url, init) =>
      init?.method === "DELETE"
        ? new Promise((resolve) => {
            finish = () => { resolve({ ok: false, status: 500 }); };
          })
        : status(true),
    );
    render(<KrogerConnect plan={initialPlanState()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect((screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { finish(); });
    expect((screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("clears the return message when Disconnect starts", async () => {
    let connected = true;
    stub(async (_url, init) => {
      if (init?.method === "DELETE") {
        connected = false;
        return { ok: true, status: 204 };
      }
      return status(connected);
    });
    render(<KrogerConnect plan={initialPlanState()} returnStatus="connected" />);
    expect(await screen.findByText("Kroger account connected.")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("link", { name: "Connect Kroger" })).toBeTruthy();
    expect(screen.queryByText("Kroger account connected.")).toBeNull();
  });

  it("does not read the status again when Disconnect finishes after unmount", async () => {
    let finish: () => void = () => undefined;
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "DELETE"
        ? new Promise<Partial<Response>>((resolve) => {
            finish = () => { resolve({ ok: true, status: 204 }); };
          })
        : status(true),
    );
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<KrogerConnect plan={initialPlanState()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    view.unmount();
    const calls = fetchMock.mock.calls.length;
    await act(async () => { finish(); });
    await settle();
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("shows the sign-in result from the prop and leaves the URL alone", async () => {
    window.history.replaceState(null, "", "/prototype?a=1&kroger=error&b=2");
    stub(() => status(false));
    render(<KrogerConnect plan={initialPlanState()} returnStatus="error" />);
    const note = await screen.findByText("Kroger sign-in did not finish. Try again.");
    expect(note.getAttribute("aria-live")).toBe("polite");
    expect(window.location.pathname + window.location.search).toBe("/prototype?a=1&kroger=error&b=2");
  });

  it("shows the connected message and no message without a return status", async () => {
    stub(() => status(true));
    const first = render(<KrogerConnect plan={initialPlanState()} returnStatus="connected" />);
    expect(await screen.findByText("Kroger account connected.")).toBeTruthy();
    first.unmount();

    stub(() => status(false));
    render(<KrogerConnect plan={initialPlanState()} returnStatus={null} />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.queryByText(/sign-in did not finish/)).toBeNull();
  });
});
