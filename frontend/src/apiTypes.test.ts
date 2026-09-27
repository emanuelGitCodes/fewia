/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import {
  SHAPE_ERROR,
  isRecord,
  isSafeInteger,
  isSpendingSource,
  isStatus,
  sourceLabel,
} from "./apiTypes";
import { parseConfig, parseJob } from "./apiValidation";
import { parseProviders } from "./providerApi";
import { config, job, manualConfig, manualJobResult } from "../tests/apiFixtures";

describe("isRecord", () => {
  it("accepts a plain object", () => {
    expect(isRecord({})).toBe(true);
    expect(isRecord({ id: "bean_tacos" })).toBe(true);
  });

  it("rejects null, arrays, and primitives", () => {
    expect(isRecord(null)).toBe(false);
    expect(isRecord([])).toBe(false);
    expect(isRecord("queued")).toBe(false);
    expect(isRecord(1)).toBe(false);
    expect(isRecord(undefined)).toBe(false);
  });
});

describe("isSafeInteger", () => {
  it("accepts safe integers including zero and negatives", () => {
    expect(isSafeInteger(0)).toBe(true);
    expect(isSafeInteger(-10)).toBe(true);
    expect(isSafeInteger(Number.MAX_SAFE_INTEGER)).toBe(true);
    expect(isSafeInteger(Number.MIN_SAFE_INTEGER)).toBe(true);
  });

  it("rejects fractional and unsafe numbers", () => {
    expect(isSafeInteger(1.5)).toBe(false);
    expect(isSafeInteger(10.25)).toBe(false);
    expect(isSafeInteger(Number.MAX_SAFE_INTEGER + 1)).toBe(false);
    expect(isSafeInteger(Number.NaN)).toBe(false);
    expect(isSafeInteger(Number.POSITIVE_INFINITY)).toBe(false);
  });

  it("rejects non-number values", () => {
    expect(isSafeInteger("1")).toBe(false);
    expect(isSafeInteger(true)).toBe(false);
    expect(isSafeInteger(null)).toBe(false);
    expect(isSafeInteger(undefined)).toBe(false);
    expect(isSafeInteger({})).toBe(false);
  });
});

describe("isStatus", () => {
  it("accepts queued, running, succeeded, and failed", () => {
    expect(isStatus("queued")).toBe(true);
    expect(isStatus("running")).toBe(true);
    expect(isStatus("succeeded")).toBe(true);
    expect(isStatus("failed")).toBe(true);
  });

  it("rejects other values", () => {
    expect(isStatus("pending")).toBe(false);
    expect(isStatus("")).toBe(false);
    expect(isStatus(0)).toBe(false);
    expect(isStatus(null)).toBe(false);
    expect(isStatus({ status: "queued" })).toBe(false);
  });
});

describe("isSpendingSource", () => {
  it("accepts manual, fixture, and plaid_sandbox", () => {
    expect(isSpendingSource("manual")).toBe(true);
    expect(isSpendingSource("fixture")).toBe(true);
    expect(isSpendingSource("plaid_sandbox")).toBe(true);
  });

  it("rejects unknown source strings", () => {
    expect(isSpendingSource("bedrock")).toBe(false);
    expect(isSpendingSource("plaid")).toBe(false);
    expect(isSpendingSource("")).toBe(false);
    expect(isSpendingSource(null)).toBe(false);
  });

  it("lets config, provider, and job validators accept manual and reject unknown sources", () => {
    const catalog = {
      catalog_version: "sample-prices-v1",
      spending_refreshed_at: "2026-09-07T16:00:00Z",
    };
    expect(parseConfig(manualConfig(catalog)).source).toBe("manual");
    expect(
      parseProviders({
        chat_configured: true,
        plaid_configured: false,
        instacart_configured: false,
        spending_source: "manual",
      }).spending_source,
    ).toBe("manual");
    expect(parseJob(job({ result: manualJobResult() })).result?.spending_source).toBe("manual");
    expect(() => parseConfig(config({ ...catalog, source: "bedrock" }))).toThrow(SHAPE_ERROR);
    expect(() =>
      parseProviders({
        chat_configured: true,
        plaid_configured: false,
        instacart_configured: false,
        spending_source: "bedrock",
      }),
    ).toThrow(SHAPE_ERROR);
  });
});

describe("sourceLabel", () => {
  it("labels known sources and marks unknown sources", () => {
    expect(sourceLabel("manual")).toBe("Your entered budget");
    expect(sourceLabel("fixture")).toBe("Demo spending");
    expect(sourceLabel("plaid_sandbox")).toBe("Plaid Sandbox");
    expect(sourceLabel("live")).toBe("Unverified spending source");
  });
});
