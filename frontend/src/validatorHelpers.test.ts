/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { hasExactKeys } from "./apiTypes";
import { KROGER_LOCATION_ID } from "./krogerApi";
import { INGREDIENTS, isKnownIngredient } from "./prototype/prototypeData";

describe("hasExactKeys", () => {
  it("accepts an exact match", () => {
    expect(hasExactKeys({ a: 1, b: 2 }, ["a", "b"])).toBe(true);
  });

  it("rejects a missing key", () => {
    expect(hasExactKeys({ a: 1 }, ["a", "b"])).toBe(false);
    expect(hasExactKeys({ a: 1, c: 2 }, ["a", "b"])).toBe(false);
  });

  it("rejects an extra key", () => {
    expect(hasExactKeys({ a: 1, b: 2, c: 3 }, ["a", "b"])).toBe(false);
  });

  it("rejects an inherited key", () => {
    const inherited: Record<string, unknown> = Object.create({ a: 1 });
    expect(hasExactKeys(inherited, ["a"])).toBe(false);
  });

  it("accepts an empty object with an empty key list", () => {
    expect(hasExactKeys({}, [])).toBe(true);
  });

  it("counts a duplicate entry in the key list toward the length", () => {
    expect(hasExactKeys({ a: 1, b: 2 }, ["a", "a"])).toBe(true);
    expect(hasExactKeys({ a: 1 }, ["a", "a"])).toBe(false);
  });
});

describe("isKnownIngredient", () => {
  it("accepts a catalog id", () => {
    expect(isKnownIngredient(Object.keys(INGREDIENTS)[0])).toBe(true);
  });

  it("rejects unknown and inherited names", () => {
    expect(isKnownIngredient("not-an-ingredient")).toBe(false);
    expect(isKnownIngredient("toString")).toBe(false);
    expect(isKnownIngredient("__proto__")).toBe(false);
  });
});

describe("KROGER_LOCATION_ID", () => {
  it("accepts exactly eight alphanumeric characters", () => {
    expect(KROGER_LOCATION_ID.test("01400943")).toBe(true);
    expect(KROGER_LOCATION_ID.test("abCD12xY")).toBe(true);
  });

  it("rejects seven or nine characters", () => {
    expect(KROGER_LOCATION_ID.test("0140094")).toBe(false);
    expect(KROGER_LOCATION_ID.test("014009431")).toBe(false);
  });

  it("rejects a dash", () => {
    expect(KROGER_LOCATION_ID.test("0140-943")).toBe(false);
  });
});
