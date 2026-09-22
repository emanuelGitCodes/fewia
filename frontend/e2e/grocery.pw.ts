import { expect, test, type Page, type Request, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";

const SAMPLE_NOTICE =
  "Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";
const SPOONACULAR_NOTICE =
  "Average supermarket estimate from Spoonacular. Not a store price. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";
const CHAT_MESSAGE = "Plan bean tacos for four servings. I have olive oil.";
const CHAT_ANSWER = "Mock chat plan for four bean-taco servings with pantry oil.";
const CHAT_FAIL = "The chat request failed. Retry checks the same request.";
const CHAT_HTTP = "The chat request failed. Check the message and budget, then retry.";
const GROCERY_HTTP =
  "The grocery request failed. Check meals, servings, and budget, then retry.";
const QUEUED = "Your grocery request is queued.";
const CONVERSATION_WITHIN = "The estimate is within the plan budget.";
const ESTIMATE_WITHIN = "This estimate is within the plan budget.";
const DIRTY_STATUS = "Rebuild the request to apply request changes.";
const HEX64 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

type MealRow = { recipe_id: string; servings: number };
type GroceryRequest = {
  meals: MealRow[];
  budget_period: string;
  plan_cap_cents: number | null;
  pantry_ingredients: string[];
  ingredient_exclusions: string[];
  diet: string;
};
type PlanCase = {
  request: GroceryRequest;
  plan: Record<string, unknown> & { total_cents: number; notice: string };
  budget: Record<string, unknown>;
  meal_nutrition: Record<string, unknown> & { total: { energy_kcal: number } };
  spending_source: string;
  evidence_id: string;
  evidence_revision_id: string;
};
type PlansFile = {
  evidence_class: string;
  config: {
    recipes: Array<{ id: string; name: string }>;
    ingredients: Array<{ id: string; name: string }>;
    notice: string;
  };
  beans2: PlanCase;
  beans4: PlanCase;
  beans2PantryOil: PlanCase;
  beans4PantryOil: PlanCase;
};
type GroceryPost = {
  monthly_limit_cents: number;
  request: GroceryRequest;
};
type ChatPost = {
  message: string;
  monthly_limit_cents: number;
  plan_cap_cents: number | null;
  previous_job_id: string | null;
};
type ChatOutcome = "success" | "fail" | "malformed";
type StoredJob = {
  polls: number;
  kind: "grocery" | "chat";
  plan: PlanCase | null;
  chatOutcome: ChatOutcome;
};

const plans = JSON.parse(
  readFileSync(new URL("./fixtures/plans.json", import.meta.url), "utf8"),
) as PlansFile;

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function groceryResult(plan: PlanCase): Record<string, unknown> {
  return {
    plan: plan.plan,
    budget: plan.budget,
    spending_source: plan.spending_source,
    meal_nutrition: plan.meal_nutrition,
  };
}

function chatResult(plan: PlanCase): Record<string, unknown> {
  return {
    status: "planned",
    answer: CHAT_ANSWER,
    plan: plan.plan,
    budget: plan.budget,
    request: plan.request,
    meal_nutrition: plan.meal_nutrition,
    evidence_id: plan.evidence_id,
    evidence_revision_id: plan.evidence_revision_id,
    spending_source: plan.spending_source,
    tool_trace: [
      {
        tool: "select_meals",
        outcome: "success",
        tool_use_id: "tool-select-meals",
        sequence: 1,
        revision_index: 1,
        evidence_id: plan.evidence_id,
        evidence_revision_id: plan.evidence_revision_id,
      },
    ],
    model_turns: 2,
    planner_revisions: 1,
    usage: { inputTokens: 10, outputTokens: 8 },
  };
}

function fixtureForGrocery(body: GroceryPost): PlanCase | null {
  const matches = [plans.beans2, plans.beans4, plans.beans2PantryOil, plans.beans4PantryOil];
  for (const item of matches) {
    if (isDeepStrictEqual(body.request, item.request)) {
      return item;
    }
  }
  return null;
}

class ApiHarness {
  readonly groceryPosts: Array<{ id: string; key: string; body: GroceryPost }> = [];
  readonly chatPosts: Array<{ id: string; key: string; body: ChatPost }> = [];
  readonly unknown: string[] = [];
  supermarketGets = 0;
  chatOutcome: ChatOutcome = "success";
  private seq = 0;
  private readonly jobs = new Map<string, StoredJob>();

  nextId(): string {
    this.seq += 1;
    return `00000000-0000-4000-8000-${this.seq.toString(16).padStart(12, "0")}`;
  }

  private markUnknown(request: Request): void {
    this.unknown.push(`${request.method()} ${new URL(request.url()).pathname}`);
  }

  async handle(route: Route): Promise<void> {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method === "GET" && path === "/api/grocery/config") {
      await json(route, plans.config);
      return;
    }
    if (method === "GET" && path === "/api/grocery/providers") {
      await json(route, {
        chat_configured: true,
        plaid_configured: false,
        instacart_configured: false,
        spending_source: "fixture",
      });
      return;
    }
    if (method === "POST" && path === "/api/grocery/jobs") {
      await this.postGrocery(route, request);
      return;
    }
    if (method === "POST" && path === "/api/grocery/chat/jobs") {
      await this.postChat(route, request);
      return;
    }
    const supermarket = /^\/api\/grocery\/jobs\/([^/]+)\/supermarket-estimate$/.exec(path);
    if (method === "GET" && supermarket !== null) {
      await this.getSupermarket(route, supermarket[1] ?? "");
      return;
    }
    const groceryJob = /^\/api\/grocery\/jobs\/([^/]+)$/.exec(path);
    if (method === "GET" && groceryJob !== null) {
      await this.getJob(route, groceryJob[1] ?? "", "grocery");
      return;
    }
    const chatJob = /^\/api\/grocery\/chat\/jobs\/([^/]+)$/.exec(path);
    if (method === "GET" && chatJob !== null) {
      await this.getJob(route, chatJob[1] ?? "", "chat");
      return;
    }
    this.markUnknown(request);
    await json(route, { error: "unmocked_api" }, 418);
  }

  private async postGrocery(route: Route, request: Request): Promise<void> {
    const body = request.postDataJSON() as GroceryPost;
    const plan = fixtureForGrocery(body);
    if (plan === null) {
      this.markUnknown(request);
      await json(route, { error: "unmocked_grocery_request" }, 418);
      return;
    }
    const id = this.nextId();
    this.jobs.set(id, { polls: 0, kind: "grocery", plan, chatOutcome: "success" });
    this.groceryPosts.push({
      id,
      key: request.headers()["idempotency-key"] ?? "",
      body,
    });
    await json(route, { job_id: id, status: "queued" });
  }

  private async postChat(route: Route, request: Request): Promise<void> {
    const body = request.postDataJSON() as ChatPost;
    const id = this.nextId();
    this.jobs.set(id, {
      polls: 0,
      kind: "chat",
      plan: plans.beans4PantryOil,
      chatOutcome: this.chatOutcome,
    });
    this.chatPosts.push({
      id,
      key: request.headers()["idempotency-key"] ?? "",
      body,
    });
    await json(route, { job_id: id, status: "queued" });
  }

  private async getSupermarket(route: Route, jobId: string): Promise<void> {
    if (!this.jobs.has(jobId)) {
      this.markUnknown(route.request());
      await json(route, { error: "unmocked_api" }, 418);
      return;
    }
    this.supermarketGets += 1;
    await json(route, { total_cents: 1299, notice: SPOONACULAR_NOTICE });
  }

  private async getJob(route: Route, jobId: string, kind: "grocery" | "chat"): Promise<void> {
    const job = this.jobs.get(jobId);
    if (job === undefined || job.kind !== kind) {
      this.markUnknown(route.request());
      await json(route, { error: "unmocked_api" }, 418);
      return;
    }
    job.polls += 1;
    if (job.polls === 1) {
      await json(route, { id: jobId, status: "queued", result: null, error_code: null });
      return;
    }
    if (kind === "chat" && job.chatOutcome === "malformed") {
      await json(route, { job_id: jobId, unexpected: true });
      return;
    }
    if (kind === "chat" && job.chatOutcome === "fail") {
      await json(route, { id: jobId, status: "failed", result: null, error_code: "chat_failed" });
      return;
    }
    if (kind === "grocery" && job.plan !== null) {
      await json(route, {
        id: jobId,
        status: "succeeded",
        error_code: null,
        result: groceryResult(job.plan),
      });
      return;
    }
    if (kind === "chat" && job.plan !== null) {
      await json(route, {
        id: jobId,
        status: "succeeded",
        error_code: null,
        result: chatResult(job.plan),
      });
      return;
    }
    this.markUnknown(route.request());
    await json(route, { error: "unmocked_api" }, 418);
  }
}

async function attachApi(page: Page, harness: ApiHarness): Promise<void> {
  await page.route("**/api/**", (route) => harness.handle(route));
}

function attachConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push(msg.text());
    }
  });
  page.on("pageerror", (error) => {
    errors.push(error.message);
  });
  return errors;
}

function statusText(page: Page, text: string) {
  return page.getByRole("status").filter({ hasText: text });
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflowed = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });
  expect(overflowed).toBe(false);
}

async function openApp(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByLabel("Monthly limit")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEnabled();
}

async function pressControl(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name }).press("Enter");
}

async function openPantry(page: Page): Promise<void> {
  const summary = page
    .getByRole("group", { name: "Budget and meals" })
    .locator("summary")
    .filter({ hasText: /^Pantry$/ });
  await summary.click();
  await expect(page.getByLabel("Pantry olive oil")).toBeVisible();
}

test.describe("grocery browser journeys", () => {
  test("manual beans then chat pantry oil then rebuild", async ({ page }) => {
    const harness = new ApiHarness();
    const consoleErrors = attachConsole(page);
    await attachApi(page, harness);
    await openApp(page);

    const recipe = page.getByLabel("Recipe 1");
    expect(plans.config.recipes).toHaveLength(10);
    for (const item of plans.config.recipes) {
      await expect(recipe.getByRole("option", { name: item.name, exact: true })).toHaveCount(1);
    }
    const servings = page.getByLabel("Servings 1");
    for (const count of [1, 2, 3, 4, 5, 6, 7, 8]) {
      await expect(servings.getByRole("option", { name: String(count), exact: true })).toHaveCount(1);
    }
    await expect(page.getByRole("button", { name: "Add meal" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Remove meal 1" })).toBeDisabled();
    await pressControl(page, "Add meal");
    await expect(page.getByLabel("Recipe 2")).toBeVisible();
    await pressControl(page, "Add meal");
    await expect(page.getByLabel("Recipe 3")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add meal" })).toBeDisabled();
    await pressControl(page, "Remove meal 3");
    await pressControl(page, "Remove meal 2");
    await expect(page.getByText(SAMPLE_NOTICE, { exact: true })).toBeVisible();
    expect(plans.beans4PantryOil.evidence_revision_id).toBe(HEX64);
    expect(plans.beans4PantryOil.evidence_id.length).toBeGreaterThan(0);

    await pressControl(page, "Bean tacos for two");
    await expect(statusText(page, QUEUED)).toBeVisible();
    await expect(statusText(page, CONVERSATION_WITHIN)).toBeVisible();
    await expect(statusText(page, ESTIMATE_WITHIN)).toBeVisible();
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    await expect(page.getByText("Source Demo spending", { exact: true })).toBeVisible();

    await page.getByRole("textbox", { name: "Message", exact: true }).fill(CHAT_MESSAGE);
    await pressControl(page, "Send");
    await expect(statusText(page, "Your request is in progress.")).toBeVisible();
    await expect(page.getByText(CHAT_ANSWER, { exact: true })).toBeVisible();
    await expect(page.getByLabel("Servings 1")).toHaveValue("4");
    await expect(page.getByLabel("Plan cap (optional)")).toHaveValue("40");
    await expect(page.getByLabel("Diet")).toHaveValue("omnivore");
    await openPantry(page);
    const pantryOil = page.getByLabel("Pantry olive oil");
    await expect(pantryOil).toBeChecked();
    await expect(page.getByLabel("I have olive oil")).toBeChecked();
    await expect(page.getByText("$12.33", { exact: true })).toBeVisible();
    const nutrition = page.getByRole("region", { name: "Estimated nutrition" });
    await expect(nutrition.getByText("1,515 kcal")).toHaveCount(2);
    await expect(page.getByRole("link", { name: "USDA FoodData Central" })).toHaveAttribute(
      "href",
      "https://fdc.nal.usda.gov/",
    );
    await expect(page.getByText(SAMPLE_NOTICE, { exact: true })).toBeVisible();
    expect(harness.supermarketGets).toBe(0);

    await pantryOil.focus();
    await page.keyboard.press("Space");
    await expect(pantryOil).not.toBeChecked();
    await expect(page.getByLabel("I have olive oil")).not.toBeChecked();
    await expect(page.getByRole("heading", { name: "Previous estimate" })).toBeVisible();
    await expect(statusText(page, DIRTY_STATUS)).toBeVisible();

    await pressControl(page, "Rebuild estimate");
    await expect(statusText(page, QUEUED)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Grocery estimate" })).toBeVisible();
    await expect(page.getByLabel("Servings 1")).toHaveValue("4");
    await expect(page.getByLabel("Plan cap (optional)")).toHaveValue("40");
    await expect(page.getByLabel("Diet")).toHaveValue("omnivore");
    await expect(page.getByLabel("Pantry olive oil")).not.toBeChecked();
    await expect(page.getByLabel("I have olive oil")).not.toBeChecked();
    await expect(page.getByText("$18.32", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "USDA FoodData Central" })).toHaveAttribute(
      "target",
      "_blank",
    );

    expect(harness.unknown).toEqual([]);
    expect(harness.groceryPosts).toHaveLength(2);
    expect(harness.chatPosts).toHaveLength(1);
    expect(harness.groceryPosts[0]?.body).toEqual({
      monthly_limit_cents: 30000,
      request: plans.beans2.request,
    });
    expect(harness.groceryPosts[1]?.body).toEqual({
      monthly_limit_cents: 30000,
      request: plans.beans4.request,
    });
    expect(harness.chatPosts[0]?.body).toEqual({
      message: CHAT_MESSAGE,
      monthly_limit_cents: 30000,
      plan_cap_cents: 4000,
      previous_job_id: harness.groceryPosts[0]?.id ?? null,
    });
    expect(harness.supermarketGets).toBe(0);
    expect(consoleErrors).toEqual([]);
    await assertNoHorizontalOverflow(page);
  });

  test("failed chat then retry keeps the idempotency key", async ({ page }) => {
    const harness = new ApiHarness();
    const consoleErrors = attachConsole(page);
    harness.chatOutcome = "fail";
    await attachApi(page, harness);
    await openApp(page);

    await pressControl(page, "Bean tacos for two");
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    expect(harness.groceryPosts[0]?.body).toEqual({
      monthly_limit_cents: 30000,
      request: plans.beans2.request,
    });

    await page.getByRole("textbox", { name: "Message", exact: true }).fill(CHAT_MESSAGE);
    await pressControl(page, "Send");
    await expect(statusText(page, CHAT_FAIL)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Previous estimate" })).toBeVisible();
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Check supermarket estimate" })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
    expect(harness.chatPosts).toHaveLength(1);
    expect(harness.chatPosts[0]?.id).toBeTruthy();

    harness.chatOutcome = "malformed";
    await pressControl(page, "Retry the same request");
    await expect(statusText(page, CHAT_HTTP)).toBeVisible();
    await expect(page.getByText(GROCERY_HTTP, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Previous estimate" })).toBeVisible();
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Check supermarket estimate" })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();

    expect(harness.unknown).toEqual([]);
    expect(harness.chatPosts).toHaveLength(2);
    expect(harness.chatPosts[0]?.key.length).toBeGreaterThan(0);
    expect(harness.chatPosts[1]?.key).toBe(harness.chatPosts[0]?.key);
    expect(harness.chatPosts[0]?.body).toEqual(harness.chatPosts[1]?.body);
    expect(harness.chatPosts[0]?.body.previous_job_id).toBe(harness.groceryPosts[0]?.id);
    expect(harness.chatPosts[1]?.id).not.toBe(harness.chatPosts[0]?.id);
    expect(consoleErrors).toEqual([]);
    await assertNoHorizontalOverflow(page);
  });

  test("Spoonacular overlay stays opt-in and does not replace the sample total", async ({
    page,
  }) => {
    const harness = new ApiHarness();
    const consoleErrors = attachConsole(page);
    await attachApi(page, harness);
    await openApp(page);

    await pressControl(page, "Bean tacos for two");
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    expect(harness.supermarketGets).toBe(0);

    await pressControl(page, "Check supermarket estimate");
    const overlay = page.getByRole("region", { name: "Spoonacular estimate" });
    await expect(overlay.getByRole("status").filter({ hasText: "$12.99" })).toBeVisible();
    await expect(overlay.getByText(SPOONACULAR_NOTICE, { exact: true })).toBeVisible();
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    expect(harness.supermarketGets).toBe(1);

    await openPantry(page);
    const pantryOil = page.getByLabel("Pantry olive oil");
    await expect(pantryOil).not.toBeChecked();
    await pantryOil.focus();
    await page.keyboard.press("Space");
    await expect(pantryOil).toBeChecked();
    await expect(page.getByRole("heading", { name: "Previous estimate" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "$12.99" })).toHaveCount(0);
    await expect(page.getByText(SPOONACULAR_NOTICE, { exact: true })).toHaveCount(0);
    await expect(page.getByText("$17.03", { exact: true })).toBeVisible();
    expect(harness.supermarketGets).toBe(1);

    await pressControl(page, "Rebuild estimate");
    await expect(page.getByRole("heading", { name: "Grocery estimate" })).toBeVisible();
    await expect(page.getByText("$11.04", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Spoonacular estimate" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "$12.99" })).toHaveCount(0);
    expect(harness.supermarketGets).toBe(1);
    expect(harness.unknown).toEqual([]);
    expect(harness.groceryPosts[1]?.body).toEqual({
      monthly_limit_cents: 30000,
      request: plans.beans2PantryOil.request,
    });
    expect(consoleErrors).toEqual([]);
    await assertNoHorizontalOverflow(page);
  });
});
