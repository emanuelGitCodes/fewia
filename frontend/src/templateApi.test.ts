/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR, type GroceryConfig } from "./apiTypes";
import {
  fetchTemplates,
  parseTemplateSuggestions,
  type TemplateRequest,
} from "./templateApi";

const PERIOD = "2026-09-01";
const CATALOG = "sample-prices-v1";
const NOTICE = SAMPLE_ESTIMATE_NOTICE;
const RAW = "do-not-echo-this";

function groceryConfig(overrides: Partial<GroceryConfig> = {}): GroceryConfig {
  return {
    budget_period: PERIOD,
    source: "fixture",
    catalog_version: CATALOG,
    posted_cents: 1200,
    pending_cents: -50,
    spending_refreshed_at: "2026-09-07T16:00:00Z",
    notice: NOTICE,
    recipes: [
      { id: "bean_tacos", name: "Bean tacos" },
      { id: "lentil_soup", name: "Lentil soup" },
      { id: "overnight_oats", name: "Overnight oats" },
    ],
    ingredients: [{ id: "black_beans", name: "black beans" }],
    ...overrides,
  };
}

function templateRequest(overrides: Partial<TemplateRequest> = {}): TemplateRequest {
  return {
    budget_period: PERIOD,
    monthly_limit_cents: 20000,
    plan_cap_cents: 8000,
    servings: 2,
    diet: "omnivore",
    pantry_ingredients: [],
    ingredient_exclusions: [],
    ...overrides,
  };
}

function suggestion(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    template_id: "bean_lentil_oats",
    recipe_ids: ["bean_tacos", "lentil_soup", "overnight_oats"],
    servings: 2,
    total_cents: 400,
    catalog_version: CATALOG,
    notice: NOTICE,
    ...overrides,
  };
}

function budget(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    available_cents: 5000,
    pending_cents: 200,
    stale: false,
    warnings: ["cap applied"],
    ...overrides,
  };
}

function payload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    budget_period: PERIOD,
    spending_source: "fixture",
    budget: budget(),
    catalog_version: CATALOG,
    notice: NOTICE,
    suggestions: [suggestion()],
    ...overrides,
  };
}

function parse(
  value: unknown,
  config: GroceryConfig = groceryConfig(),
  request: TemplateRequest = templateRequest(),
) {
  return parseTemplateSuggestions(value, config, request);
}

function expectShapeError(action: () => unknown): void {
  try {
    action();
    throw new Error("expected a static error");
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(SHAPE_ERROR);
    expect((error as Error).message).not.toContain(RAW);
  }
}

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: () => Promise.resolve(body),
  } as Response;
}

type FetchMock = Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>;

function lastInit(fetchMock: FetchMock): RequestInit {
  const init = fetchMock.mock.calls[0]?.[1];
  if (init === undefined) {
    throw new Error("fetch was not called");
  }
  return init;
}

async function expectStaticError(action: () => Promise<unknown>, message: string): Promise<void> {
  try {
    await action();
    throw new Error("expected a static error");
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(message);
    expect((error as Error).message).not.toContain(RAW);
  }
}

describe("parseTemplateSuggestions", () => {
  it("accepts a valid payload and an empty suggestion list", () => {
    const parsed = parse(payload());
    expect(parsed.budget_period).toBe(PERIOD);
    expect(parsed.spending_source).toBe("fixture");
    expect(parsed.catalog_version).toBe(CATALOG);
    expect(parsed.notice).toBe(NOTICE);
    expect(parsed.suggestions).toHaveLength(1);
    expect(parsed.suggestions[0]?.template_id).toBe("bean_lentil_oats");
    expect(parse(payload({ suggestions: [] })).suggestions).toEqual([]);
  });

  it("accepts six suggestions and a negative pending refund", () => {
    const suggestions = Array.from({ length: 6 }, (_, index) =>
      suggestion({ template_id: `template-${index}`, recipe_ids: ["bean_tacos"] }),
    );
    const parsed = parse(payload({ budget: budget({ pending_cents: -25 }), suggestions }));
    expect(parsed.budget.pending_cents).toBe(-25);
    expect(parsed.suggestions).toHaveLength(6);
  });

  it("does not bound available_cents by monthly_limit_cents when the cap is null", () => {
    const parsed = parse(
      payload({ budget: budget({ available_cents: 9000 }) }),
      groceryConfig(),
      templateRequest({ monthly_limit_cents: 100, plan_cap_cents: null }),
    );
    expect(parsed.budget.available_cents).toBe(9000);
  });

  it("accepts available_cents equal to a non-null cap", () => {
    const parsed = parse(
      payload({ budget: budget({ available_cents: 8000 }), suggestions: [] }),
      groceryConfig(),
      templateRequest({ plan_cap_cents: 8000 }),
    );
    expect(parsed.budget.available_cents).toBe(8000);
  });

  it("returns copied budget warnings, suggestions, and recipe_ids", () => {
    const warnings = ["keep"];
    const recipeIds = ["bean_tacos"];
    const suggestions = [suggestion({ recipe_ids: recipeIds })];
    const input = payload({ budget: budget({ warnings }), suggestions });
    const parsed = parse(input);
    const first = parsed.suggestions[0];
    if (first === undefined) {
      throw new Error("expected cloned suggestion");
    }
    parsed.budget.warnings.push("mutated");
    parsed.suggestions.push(first);
    first.recipe_ids.push("mutated");
    warnings.push("input");
    recipeIds.push("input");
    suggestions.pop();
    expect((input.budget as { warnings: string[] }).warnings).toEqual(["keep", "input"]);
    expect((input.suggestions as unknown[]).length).toBe(0);
    expect(parsed.budget.warnings).toEqual(["keep", "mutated"]);
    expect(parsed.suggestions).toHaveLength(2);
    expect(first.recipe_ids).toEqual(["bean_tacos", "mutated"]);
  });

  it("rejects malformed period, source, catalog, version, and notice", () => {
    expectShapeError(() => parse(payload({ budget_period: "2026-08-01" })));
    expectShapeError(() =>
      parse(payload({ budget_period: PERIOD }), groceryConfig({ budget_period: "2026-08-01" })),
    );
    expectShapeError(() =>
      parse(payload(), groceryConfig(), templateRequest({ budget_period: "2026-08-01" })),
    );
    expectShapeError(() => parse(payload({ spending_source: "manual" })));
    expectShapeError(() => parse(payload({ spending_source: "bedrock" })));
    expectShapeError(() => parse(payload({ catalog_version: "other" })));
    expectShapeError(() => parse(payload({ notice: "store price" })));
    expectShapeError(() =>
      parse(payload({ suggestions: [suggestion({ catalog_version: "other" })] })),
    );
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ notice: RAW })] })));
    expectShapeError(() => parse({ detail: RAW }));
  });

  it("rejects malformed budget, cap, count, id, recipe, servings, and amount", () => {
    expectShapeError(() => parse(payload({ budget: budget({ available_cents: 1.5 }) })));
    expectShapeError(() => parse(payload({ budget: budget({ available_cents: -1 }) })));
    expectShapeError(() =>
      parse(
        payload({ budget: budget({ available_cents: 8001 }) }),
        groceryConfig(),
        templateRequest({ plan_cap_cents: 8000 }),
      ),
    );
    const seven = Array.from({ length: 7 }, (_, index) => suggestion({ template_id: `t${index}` }));
    expectShapeError(() => parse(payload({ suggestions: seven })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ template_id: "" })] })));
    expectShapeError(() =>
      parse(
        payload({
          suggestions: [
            suggestion({ template_id: "dup" }),
            suggestion({ template_id: "dup", recipe_ids: ["bean_tacos"] }),
          ],
        }),
      ),
    );
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ recipe_ids: [] })] })));
    expectShapeError(() =>
      parse(
        payload({
          suggestions: [
            suggestion({
              recipe_ids: ["bean_tacos", "lentil_soup", "overnight_oats", "bean_tacos"],
            }),
          ],
        }),
      ),
    );
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ recipe_ids: ["unknown_meal"] })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ recipe_ids: [""] })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ servings: 0 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ servings: 9 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ servings: 1.5 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ servings: 1 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ total_cents: -1 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ total_cents: 5001 })] })));
    expectShapeError(() => parse(payload({ suggestions: [suggestion({ total_cents: 1.5 })] })));
    expectShapeError(() =>
      parse(payload({ suggestions: [suggestion({ total_cents: Number.MAX_SAFE_INTEGER + 1 })] })),
    );
  });
});

describe("fetchTemplates", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts JSON to /api/grocery/templates with Content-Type and the abort signal", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(payload()));
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const request = templateRequest();
    const config = groceryConfig();
    await expect(fetchTemplates(request, config, signal)).resolves.toEqual(parse(payload(), config, request));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/grocery/templates");
    const init = lastInit(fetchMock);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify(request));
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.signal).toBe(signal);
  });

  it("throws HTTP_ERROR for failed and network fetches and hides raw payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: RAW }, false)));
    await expectStaticError(() => fetchTemplates(templateRequest(), groceryConfig()), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(RAW);
      }),
    );
    await expectStaticError(() => fetchTemplates(templateRequest(), groceryConfig()), HTTP_ERROR);
  });

  it("throws SHAPE_ERROR for invalid JSON and invalid bodies and hides raw text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => Promise.reject(new SyntaxError(RAW)),
      })),
    );
    await expectStaticError(() => fetchTemplates(templateRequest(), groceryConfig()), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: RAW })));
    await expectStaticError(() => fetchTemplates(templateRequest(), groceryConfig()), SHAPE_ERROR);
  });

  it("aborts a hung JSON body when the caller signal aborts", async () => {
    let markJsonStart: (() => void) | undefined;
    const jsonStarted = new Promise<void>((resolve) => {
      markJsonStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => {
          if (markJsonStart === undefined) {
            throw new Error("JSON start is not armed");
          }
          markJsonStart();
          return new Promise(() => undefined);
        },
      })),
    );
    const controller = new AbortController();
    const pending = fetchTemplates(templateRequest(), groceryConfig(), controller.signal);
    await jsonStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
