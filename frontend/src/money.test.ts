/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { formatDollars, parseDollars } from "./money";

describe("parseDollars", () => {
  it("parses zero, one cent, and 1703 cents without rounding", () => {
    expect(parseDollars("0")).toBe(0);
    expect(parseDollars("0.00")).toBe(0);
    expect(parseDollars("0.01")).toBe(1);
    expect(parseDollars("17.03")).toBe(1703);
    expect(parseDollars("300")).toBe(30000);
    expect(parseDollars("40")).toBe(4000);
    expect(parseDollars(" 17.03 ")).toBe(1703);
  });

  it("returns null for a blank optional cap", () => {
    expect(parseDollars("", true)).toBeNull();
    expect(parseDollars("   ", true)).toBeNull();
  });

  it("rejects a blank required amount", () => {
    expect(() => parseDollars("")).toThrow();
    expect(() => parseDollars("  ")).toThrow();
    expect(() => parseDollars("", false)).toThrow();
  });

  it("rejects negatives, subcents, nonfinite strings, and unsafe integers", () => {
    expect(() => parseDollars("-1")).toThrow();
    expect(() => parseDollars("-0.01")).toThrow();
    expect(() => parseDollars("1.001")).toThrow();
    expect(() => parseDollars("17.030")).toThrow();
    expect(() => parseDollars("NaN")).toThrow();
    expect(() => parseDollars("Infinity")).toThrow();
    expect(() => parseDollars("-Infinity")).toThrow();
    expect(() => parseDollars("1e2")).toThrow();
    expect(() => parseDollars("$17.03")).toThrow();
    expect(() => parseDollars("1,703")).toThrow();
    expect(() => parseDollars("+1")).toThrow();
    expect(() => parseDollars("01")).toThrow();
    expect(parseDollars("90071992547409.91")).toBe(Number.MAX_SAFE_INTEGER);
    expect(() => parseDollars("90071992547409.92")).toThrow();
  });
});

describe("formatDollars", () => {
  it("formats zero, one cent, and 1703 cents as USD", () => {
    expect(formatDollars(0)).toBe("$0.00");
    expect(formatDollars(1)).toBe("$0.01");
    expect(formatDollars(1703)).toBe("$17.03");
  });

  it("labels a null total as an incomplete estimate", () => {
    expect(formatDollars(null)).toBe("Incomplete estimate");
  });
});
