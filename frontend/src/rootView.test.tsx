/** @vitest-environment jsdom */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { selectRoot } from "./rootView";

vi.mock("./App", () => ({
  default: () => <p>App stub</p>,
}));

afterEach(() => {
  cleanup();
});

describe("selectRoot", () => {
  it("suspends then resolves the lazy Tonight prototype at /prototype", async () => {
    render(selectRoot("/prototype"));
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "Your plan" })).toBeTruthy();
    expect(screen.queryByText("App stub")).toBeNull();
  });

  it("ignores a trailing slash on /prototype/", async () => {
    render(selectRoot("/prototype/"));
    expect(await screen.findByRole("heading", { name: "Your plan" })).toBeTruthy();
  });

  it("renders the App at /", () => {
    render(selectRoot("/"));
    expect(screen.getByText("App stub")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
  });
});
