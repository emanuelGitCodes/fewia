/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR } from "./apiTypes";
import { parseConfig, parseJob } from "./apiValidation";
import { budget, config, job, jobResult, line, plan } from "../tests/apiFixtures";

const NOTICE = SAMPLE_ESTIMATE_NOTICE;

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
});

describe("parseConfig", () => {
  it("accepts signed posted and pending cents", () => {
    const parsed = parseConfig(config({ posted_cents: -10, pending_cents: -3 }));
    expect(parsed.posted_cents).toBe(-10);
    expect(parsed.pending_cents).toBe(-3);
    expect(parsed.source).toBe("fixture");
    expect(parsed.notice).toBe(NOTICE);
  });

  it("rejects fractional posted cents", () => {
    expect(() => parseConfig(config({ posted_cents: 1.5 }))).toThrow(SHAPE_ERROR);
  });
});
