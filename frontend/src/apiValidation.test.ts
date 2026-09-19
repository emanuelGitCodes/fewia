/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR, SPOONACULAR_COST_NOTICE } from "./apiTypes";
import { parseConfig, parseJob } from "./apiValidation";
import { budget, config, job, jobResult, line, plan } from "../tests/apiFixtures";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const CATALOG = "sample-prices-v1";
const STAMP = "2026-09-07T16:00:00Z";

function groceryConfig(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return config({
    catalog_version: CATALOG,
    spending_refreshed_at: STAMP,
    ...overrides,
  });
}

describe("parseJob", () => {
  it("accepts an incomplete plan with a null total and accepted false", () => {
    const parsed = parseJob(
      job({
        result: jobResult({
          plan: plan({
            lines: [line({ cost_cents: null })],
            total_cents: null,
            accepted: false,
            warnings: ["Missing sample price"],
          }),
        }),
      }),
    );

    expect(parsed.result?.plan.total_cents).toBeNull();
    expect(parsed.result?.plan.accepted).toBe(false);
    expect(parsed.result?.plan.notice).toBe(NOTICE);
    expect(parsed.result?.spending_source).toBe("fixture");
  });

  it("rejects an incomplete plan when accepted is true", () => {
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            plan: plan({
              lines: [line({ cost_cents: null })],
              total_cents: null,
              accepted: true,
            }),
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
  });

  it("rejects fractional and unsafe cents", () => {
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ total_cents: 1.5 }) }) }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() =>
      parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ cost_cents: 1.5 })] }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(job({ result: jobResult({ budget: budget({ available_cents: 10.25 }) }) })),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({ plan: plan({ total_cents: Number.MAX_SAFE_INTEGER + 1 }) }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ packages: 1.5 })] }) }) }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() => parseJob(job({ result: jobResult({ plan: plan({ lines: [line({ quantity: 0 })] }) }) }))).toThrow(
      SHAPE_ERROR,
    );
  });

  it("rejects a succeeded job with a null result", () => {
    expect(() => parseJob(job({ status: "succeeded", result: null }))).toThrow(SHAPE_ERROR);
  });

  it("accepts a queued job with a null result", () => {
    const parsed = parseJob(job({ status: "queued", result: null }));
    expect(parsed.result).toBeNull();
    expect(parsed.status).toBe("queued");
  });

  it("accepts a result with no overlay", () => {
    const parsed = parseJob(job());
    expect(parsed.result?.plan.total_cents).toBe(129);
    expect(parsed.result?.supermarket_estimate).toBeUndefined();
  });

  it("accepts overlay 1299 with the Spoonacular notice", () => {
    const request = { meals: [{ recipe_id: "bean_tacos", servings: 2 }] };
    const parsed = parseJob(
      job({
        result: jobResult({
          supermarket_estimate: { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE },
          evidence_revision_id: "rev-1",
          request,
          answer: "Bean tacos fit the budget.",
        }),
      }),
    );
    const extra = parsed.result as
      | { evidence_revision_id?: unknown; request?: unknown; answer?: unknown }
      | null
      | undefined;
    expect(parsed.result?.plan.total_cents).toBe(129);
    expect(parsed.result?.supermarket_estimate).toBeUndefined();
    expect(extra?.evidence_revision_id).toBe("rev-1");
    expect(extra?.request).toEqual(request);
    expect(extra?.answer).toBe("Bean tacos fit the budget.");
  });

  it("rejects overlay notice store price and a negative overlay total", () => {
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            supermarket_estimate: { total_cents: 1299, notice: "store price" },
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
    expect(() =>
      parseJob(
        job({
          result: jobResult({
            supermarket_estimate: { total_cents: -1, notice: SPOONACULAR_COST_NOTICE },
          }),
        }),
      ),
    ).toThrow(SHAPE_ERROR);
  });
});

describe("parseConfig", () => {
  it("accepts signed posted and pending cents", () => {
    const parsed = parseConfig(groceryConfig({ posted_cents: -10, pending_cents: -3 }));
    expect(parsed.posted_cents).toBe(-10);
    expect(parsed.pending_cents).toBe(-3);
    expect(parsed.source).toBe("fixture");
    expect(parsed.notice).toBe(NOTICE);
  });

  it("rejects fractional posted cents", () => {
    expect(() => parseConfig(groceryConfig({ posted_cents: 1.5 }))).toThrow(SHAPE_ERROR);
  });

  it("accepts plaid_sandbox, catalog_version, and a timezone timestamp or null", () => {
    const parsed = parseConfig(
      groceryConfig({ source: "plaid_sandbox", spending_refreshed_at: "2026-09-07T12:00:00-04:00" }),
    );
    expect(parsed.source).toBe("plaid_sandbox");
    expect(parsed.catalog_version).toBe(CATALOG);
    expect(parsed.spending_refreshed_at).toBe("2026-09-07T12:00:00-04:00");
    expect(parseConfig(groceryConfig({ spending_refreshed_at: null })).spending_refreshed_at).toBeNull();
  });

  it("rejects unknown sources, empty catalog versions, and naive timestamps", () => {
    expect(() => parseConfig(groceryConfig({ source: "bedrock" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(groceryConfig({ catalog_version: "" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(groceryConfig({ spending_refreshed_at: "2026-09-07T16:00:00" }))).toThrow(
      SHAPE_ERROR,
    );
    expect(() => parseConfig(groceryConfig({ spending_refreshed_at: "" }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(config({ catalog_version: CATALOG }))).toThrow(SHAPE_ERROR);
    expect(() => parseConfig(config({ spending_refreshed_at: STAMP }))).toThrow(SHAPE_ERROR);
  });
});
