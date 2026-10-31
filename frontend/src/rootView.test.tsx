/** @vitest-environment jsdom */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { selectRoot } from "./rootView";

vi.mock("./App", () => ({
  default: () => <p>App stub</p>,
}));

// A cold import of the lazy Tonight chunk can exceed the 1000 ms findBy default.
const LAZY_LOAD_WAIT = { timeout: 10_000 };

afterEach(() => {
  cleanup();
});

describe("selectRoot", () => {
  it("suspends then resolves the lazy Tonight prototype at /prototype", async () => {
    render(selectRoot("/prototype"));
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
    expect(
      await screen.findByRole("heading", { name: "Your plan" }, LAZY_LOAD_WAIT),
    ).toBeTruthy();
    expect(screen.queryByText("App stub")).toBeNull();
  }, 15_000);

  it("ignores a trailing slash on /prototype/", async () => {
    render(selectRoot("/prototype/"));
    expect(
      await screen.findByRole("heading", { name: "Your plan" }, LAZY_LOAD_WAIT),
    ).toBeTruthy();
  }, 15_000);

  it("renders the App at /", () => {
    render(selectRoot("/"));
    expect(screen.getByText("App stub")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
  });
});
