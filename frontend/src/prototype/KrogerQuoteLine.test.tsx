// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { KrogerQuote } from "../chatTypes";
import { KROGER_DEGRADED_LINE, KrogerQuoteLine } from "./KrogerQuoteLine";

const quote: KrogerQuote = {
  kind: "store_live",
  ingredient_id: "rice",
  product_label: "Long grain rice",
  brand: "Acme",
  size: "2 lb",
  regular_cents: 249,
  promo_cents: 199,
  stock_level: "TEMPORARILY_OUT_OF_STOCK",
  location_id: "01400943",
  retrieved_at: "2026-09-01T12:00:00Z",
};
const store = { locationId: "01400943", name: "Main Street" };

afterEach(cleanup);

describe("KrogerQuoteLine", () => {
  it("writes one sentence with the store, prices, and stock", () => {
    render(<KrogerQuoteLine quote={quote} degraded={false} store={store} />);
    const text = screen.getByText(/^Live price from Kroger Main Street as of /).textContent ?? "";
    expect(text).toMatch(/as of \d{1,2}:\d\d (AM|PM): Long grain rice, 2 lb, regular \$2\.49, /);
    expect(text).toContain("sale $1.99, stock temporarily out of stock. ");
    expect(text.endsWith("Availability and the final price are not verified.")).toBe(true);
  });

  it("omits a missing size, sale, and stock, and says Kroger alone without a store", () => {
    render(
      <KrogerQuoteLine
        quote={{ ...quote, size: null, promo_cents: null, stock_level: null }}
        degraded={false}
        store={null}
      />,
    );
    const text = screen.getByText(/^Live price from Kroger as of /).textContent ?? "";
    expect(text).toMatch(/: Long grain rice, regular \$2\.49\. Availability/);
  });

  it("writes a store name that already starts with Kroger alone", () => {
    render(
      <KrogerQuoteLine
        quote={quote}
        degraded={false}
        store={{ locationId: "01400943", name: "Kroger - Kroger On the Rhine" }}
      />,
    );
    expect(screen.getByText(/^Live price from Kroger - Kroger On the Rhine as of /)).toBeTruthy();
  });

  it("says Kroger alone when the quote is from an earlier store", () => {
    render(
      <KrogerQuoteLine quote={quote} degraded={false} store={{ locationId: "09999999", name: "New Place" }} />,
    );
    const text = screen.getByText(/^Live price from Kroger as of /).textContent ?? "";
    expect(text).not.toContain("New Place");
  });

  it("shows no sale part when the promotion is 0", () => {
    render(<KrogerQuoteLine quote={{ ...quote, promo_cents: 0 }} degraded={false} store={store} />);
    expect(screen.getByText(/^Live price from /).textContent).not.toContain("sale");
  });

  it("shows the fixed sentence when degraded and nothing otherwise", () => {
    const { container, rerender } = render(<KrogerQuoteLine quote={null} degraded store={store} />);
    expect(screen.getByText(KROGER_DEGRADED_LINE)).toBeTruthy();
    rerender(<KrogerQuoteLine quote={null} degraded={false} store={store} />);
    expect(container.textContent).toBe("");
  });
});
