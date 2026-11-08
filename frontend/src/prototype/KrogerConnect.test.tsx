// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState, type JSX } from "react";
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

  it("shows FIXTURE, NOT KROGER in fixture mode, even before the connection loads", async () => {
    stub(() => new Promise(() => undefined));
    render(<KrogerConnect plan={initialPlanState()} krogerMode="fixture" />);
    expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
  });

  it("shows the label beside the connect link in fixture mode only", async () => {
    stub(() => status(false));
    const fixture = render(<KrogerConnect plan={initialPlanState()} krogerMode="fixture" />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
    fixture.unmount();
    render(<KrogerConnect plan={initialPlanState()} krogerMode="live" />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.queryByText("FIXTURE, NOT KROGER")).toBeNull();
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
    expect(screen.getByText(PLAN_SAVE_WARNING)).toBeTruthy();
  });

  it("tries the save on every click and clears the warning when it succeeds", async () => {
    stub(() => status(false));
    render(<KrogerConnect plan={initialPlanState()} />);
    const link = await screen.findByRole("link", { name: "Connect Kroger" });
    const storage = window.sessionStorage;
    let failing = true;
    vi.stubGlobal("sessionStorage", {
      setItem: (key: string, value: string): void => {
        if (failing) throw new Error("private");
        storage.setItem(key, value);
      },
      getItem: (key: string): string | null => storage.getItem(key),
      removeItem: (key: string): void => { storage.removeItem(key); },
    });
    const outcomes: boolean[] = [];
    const record = (event: MouseEvent): void => {
      outcomes.push(event.defaultPrevented);
      event.preventDefault();
    };
    document.addEventListener("click", record);
    fireEvent.click(link);
    expect(screen.getByText(PLAN_SAVE_WARNING)).toBeTruthy();
    failing = false;
    fireEvent.click(link);
    document.removeEventListener("click", record);
    expect(outcomes).toEqual([true, false]);
    expect(screen.queryByText(PLAN_SAVE_WARNING)).toBeNull();
    expect(storage.getItem(PLAN_CHECKPOINT_KEY)).not.toBeNull();
  });

  it("shows the return line once when the component remounts", async () => {
    stub(() => status(false));
    function Host(props: { shown: boolean }): JSX.Element | null {
      const [returnStatus, setReturnStatus] = useState<"connected" | null>("connected");
      return props.shown ? (
        <KrogerConnect
          plan={initialPlanState()}
          returnStatus={returnStatus}
          onReturnShown={() => { setReturnStatus(null); }}
        />
      ) : null;
    }
    const view = render(<Host shown />);
    expect(await screen.findByText("Kroger account connected.")).toBeTruthy();
    view.rerender(<Host shown={false} />);
    view.rerender(<Host shown />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.queryByText("Kroger account connected.")).toBeNull();
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
    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    disconnect.focus();
    fireEvent.click(disconnect);
    expect(await screen.findByText("Could not disconnect Kroger. Try again.")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement;
    expect(button.getAttribute("aria-disabled")).toBe("false");
    expect(document.activeElement).toBe(button);
    expect(screen.queryByText("Kroger account disconnected.")).toBeNull();
  });

  it("guards Disconnect and keeps focus while the request is in flight", async () => {
    let finish: () => void = () => undefined;
    let deletes = 0;
    stub((_url, init) =>
      init?.method === "DELETE"
        ? new Promise((resolve) => {
            deletes += 1;
            finish = () => { resolve({ ok: false, status: 500 }); };
          })
        : status(true),
    );
    render(<KrogerConnect plan={initialPlanState()} />);
    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    const note = screen.getByRole("status", { name: "Kroger account status" });
    disconnect.focus();
    fireEvent.click(disconnect);
    fireEvent.click(disconnect);
    expect(disconnect.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(disconnect);
    expect(note.textContent).toBe("Disconnecting Kroger account.");
    expect(deletes).toBe(1);
    await act(async () => { finish(); });
    expect(disconnect.getAttribute("aria-disabled")).toBe("false");
    expect(document.activeElement).toBe(disconnect);
    expect(note.textContent).toBe("Could not disconnect Kroger. Try again.");
  });

  it.each([false, true])("waits for confirmed disconnect and preserves focus when moved=%s", async (moveFocus) => {
    let finishDelete: () => void = () => undefined;
    let finishRead: () => void = () => undefined;
    let reads = 0;
    let deletes = 0;
    stub((_url, init) => {
      if (init?.method === "DELETE") {
        deletes += 1;
        return new Promise<Partial<Response>>((resolve) => {
          finishDelete = () => { resolve({ ok: true, status: 204 }); };
        });
      }
      reads += 1;
      if (reads === 1) return status(true);
      return new Promise<Partial<Response>>((resolve) => {
        finishRead = () => { resolve({ ok: true, status: 200, json: async () => ({ connected: false }) }); };
      });
    });
    render(<><KrogerConnect plan={initialPlanState()} /><button>Elsewhere</button></>);
    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    const note = screen.getByRole("status", { name: "Kroger account status" });
    disconnect.focus();
    fireEvent.click(disconnect);
    expect(note.textContent).toBe("Disconnecting Kroger account.");
    await act(async () => { finishDelete(); });
    expect(disconnect.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(disconnect);
    expect(note.textContent).toBe("Disconnecting Kroger account.");
    expect(screen.queryByRole("link", { name: "Connect Kroger" })).toBeNull();
    fireEvent.click(disconnect);
    expect(deletes).toBe(1);
    const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
    if (moveFocus) elsewhere.focus();
    await act(async () => { finishRead(); });
    const connect = screen.getByRole("link", { name: "Connect Kroger" });
    expect(document.activeElement).toBe(moveFocus ? elsewhere : connect);
    expect(note.textContent).toBe("Kroger account disconnected.");
    expect(note.getAttribute("aria-live")).toBe("polite");
  });

  it("keeps connected controls when confirmation still reports a connection", async () => {
    stub(async (_url, init) => {
      if (init?.method === "DELETE") return { ok: true, status: 204 };
      return status(true);
    });
    render(<KrogerConnect plan={initialPlanState()} locationId="01400943" />);
    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    disconnect.focus();
    fireEvent.click(disconnect);
    await screen.findByText("Could not disconnect Kroger. Try again.");
    expect(document.activeElement).toBe(disconnect);
    expect(disconnect.getAttribute("aria-disabled")).toBe("false");
    expect(screen.getByRole("button", { name: "Preview Kroger cart" })).toBeTruthy();
    expect(screen.queryByText("Kroger account disconnected.")).toBeNull();
  });

  describe.each(["unavailable", "malformed", "network"])("after a %s confirmation", (result) => {
    it.each([false, true])("hides connected controls and preserves focus when moved=%s", async (moveFocus) => {
      let reads = 0;
      let finishRead: () => void = () => undefined;
      stub((_url, init) => {
        if (init?.method === "DELETE") return Promise.resolve({ ok: true, status: 204 });
        reads += 1;
        if (reads === 1) return status(true);
        return new Promise<Partial<Response>>((resolve, reject) => {
          finishRead = () => {
            if (result === "network") {
              reject(new Error("Synthetic failure"));
            } else if (result === "unavailable") {
              resolve({ ok: false, status: 503 });
            } else {
              resolve({ ok: true, status: 200, json: async () => ({ connected: "unknown" }) });
            }
          };
        });
      });
      render(<><KrogerConnect plan={initialPlanState()} locationId="01400943" /><button>Elsewhere</button></>);
      const disconnect = await screen.findByRole("button", { name: "Disconnect" });
      const note = screen.getByRole("status", { name: "Kroger account status" });
      disconnect.focus();
      await act(async () => { fireEvent.click(disconnect); });
      expect(disconnect.getAttribute("aria-disabled")).toBe("true");
      const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
      if (moveFocus) elsewhere.focus();
      await act(async () => { finishRead(); });
      expect(screen.queryByRole("button", { name: "Disconnect" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Preview Kroger cart" })).toBeNull();
      expect(screen.queryByText("Kroger account connected")).toBeNull();
      expect(screen.queryByRole("link", { name: "Connect Kroger" })).toBeNull();
      expect(screen.queryByText("Kroger account disconnected.")).toBeNull();
      expect(screen.getByRole("status", { name: "Kroger account status" })).toBe(note);
      expect(note.textContent).toBe("Could not verify the current Kroger connection. Reload to check.");
      expect(note.getAttribute("aria-live")).toBe("polite");
      const target = moveFocus ? elsewhere : screen.getByRole("group", { name: "Kroger account" });
      expect(document.activeElement).toBe(target);
      expect(target.contains(note)).toBe(!moveFocus);
      expect(target.getAttribute("role")).not.toBe("status");
    });
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
