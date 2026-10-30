// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KrogerConnect } from "./KrogerConnect";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("KrogerConnect", () => {
  it("renders nothing while loading, when not configured, and for a malformed body", async () => {
    stub(() => new Promise(() => undefined));
    const { container, unmount } = render(<KrogerConnect />);
    expect(container.firstChild).toBeNull();
    unmount();

    stub(async () => ({ ok: false, status: 503 }));
    const off = render(<KrogerConnect />);
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
      const bad = render(<KrogerConnect />);
      await settle();
      expect(bad.container.firstChild).toBeNull();
      bad.unmount();
    }
  });

  it("links to the connect route when not connected", async () => {
    stub(() => status(false));
    render(<KrogerConnect />);
    const link = await screen.findByRole("link", { name: "Connect Kroger" });
    expect(link.getAttribute("href")).toBe("/api/grocery/kroger/connect");
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
    render(<KrogerConnect />);
    expect(await screen.findByText("Kroger account connected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("link", { name: "Connect Kroger" })).toBeTruthy();
  });

  it("keeps the button and explains when disconnect fails", async () => {
    stub(async (_url, init) =>
      init?.method === "DELETE" ? { ok: false, status: 500 } : status(true),
    );
    render(<KrogerConnect />);
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
    render(<KrogerConnect />);
    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    expect((screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { finish(); });
    expect((screen.getByRole("button", { name: "Disconnect" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows the sign-in result and removes only the kroger parameter", async () => {
    window.history.replaceState(null, "", "/prototype?a=1&kroger=error&b=2");
    stub(() => status(false));
    render(<KrogerConnect />);
    const note = await screen.findByText("Kroger sign-in did not finish. Try again.");
    expect(note.getAttribute("aria-live")).toBe("polite");
    expect(window.location.pathname + window.location.search).toBe("/prototype?a=1&b=2");
  });

  it("shows the connected message and ignores other values", async () => {
    window.history.replaceState(null, "", "/prototype?kroger=connected");
    stub(() => status(true));
    const first = render(<KrogerConnect />);
    expect(await screen.findByText("Kroger account connected.")).toBeTruthy();
    expect(window.location.search).toBe("");
    first.unmount();

    window.history.replaceState(null, "", "/prototype?kroger=other");
    stub(() => status(false));
    render(<KrogerConnect />);
    await screen.findByRole("link", { name: "Connect Kroger" });
    expect(screen.queryByText(/sign-in did not finish/)).toBeNull();
    expect(window.location.search).toBe("");
  });
});
