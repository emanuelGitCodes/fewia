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
    expect(screen.queryByRole("heading", { name: "What sounds good?" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "What sounds good?" })).toBeTruthy();
    expect(screen.queryByText("App stub")).toBeNull();
  });

  it("ignores a trailing slash on /prototype/", async () => {
    render(selectRoot("/prototype/"));
    expect(screen.queryByRole("heading", { name: "What sounds good?" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "What sounds good?" })).toBeTruthy();
  });

  it("renders the App at /", () => {
    render(selectRoot("/"));
    expect(screen.getByText("App stub")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "What sounds good?" })).toBeNull();
  });
});
