import type { Locator, Page } from "@playwright/test";
import { SPOONACULAR_COST_NOTICE } from "../../src/apiTypes";
import { CHAT_ANSWER, expect, test } from "./fakes";

const SAMPLE_NOTICE =
  "Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";
const CHAT_PENDING = "Your request is in progress.";
const CHAT_FAILED = "The chat request failed. Retry checks the same request.";
const CHAT_MESSAGE = "Make the tacos cheaper.";

test.describe.configure({ timeout: 60_000 });

async function open(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByLabel("Recipe 1", { exact: true })).toBeVisible();
}

function estimatePanel(page: Page): Locator {
  return page.locator("section.estimate-panel");
}

function chatPanel(page: Page): Locator {
  return page.getByRole("region", { name: "Meal chat" });
}

function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

async function expectEstimate(page: Page, total: string): Promise<void> {
  await expect(page.locator(".estimate-total")).toHaveText(total);
  await expect(page.locator("#estimate-heading")).toBeFocused();
}

async function buildBeanTacos(page: Page): Promise<void> {
  await open(page);
  await page.getByRole("button", { name: "Bean tacos for two" }).click();
  await expectEstimate(page, "$17.03");
}

test("overlay: Spoonacular averages sit beside the sample-catalog total", async ({
  page,
  groceryTap,
}) => {
  groceryTap.overlay = true;
  await buildBeanTacos(page);
  const estimate = estimatePanel(page);
  const job = groceryTap.latest();
  const overlay = groceryTap.latestOverlay();
  expect(overlay.lines.length, "purchased lines").toBeGreaterThan(0);
  expect(overlay.total_cents, "fake total differs from the sample total").not.toBe(
    job.result.plan.total_cents,
  );
  await expect(estimate.getByText("Average supermarket estimate", { exact: true })).toBeVisible();
  await expect(estimate.locator(".estimate-overlay-total")).toHaveText(
    dollars(overlay.total_cents),
  );
  await expect(estimate.getByText(SPOONACULAR_COST_NOTICE, { exact: true })).toBeVisible();
  await expect(estimate.getByText(SAMPLE_NOTICE, { exact: true })).toBeVisible();
  const rows = estimate.locator(".estimate-line");
  await expect(rows).toHaveCount(job.result.plan.lines.length);
  for (const [index, line] of job.result.plan.lines.entries()) {
    const spoonacular = rows.nth(index).locator(".estimate-line-spoonacular");
    const item = overlay.lines.find((entry) => entry.ingredient_id === line.ingredient_id);
    if (line.from_pantry) {
      expect(item, `${line.ingredient_id} is a pantry line`).toBeUndefined();
      await expect(spoonacular).toHaveCount(0);
    } else {
      expect(item, `${line.ingredient_id} has an overlay line`).toBeDefined();
      await expect(spoonacular).toHaveText(
        `Spoonacular avg ${dollars(item?.cents ?? 0)} for ${line.quantity} ${line.unit}`,
      );
    }
  }

  const pantry = page.getByLabel("I have olive oil");
  const pantryId = (await pantry.getAttribute("id"))?.replace(/^pantry-/, "");
  expect(pantryId, "olive oil ingredient id").toBeTruthy();
  await pantry.check();
  // The fake overlay lists the olive-oil pantry line on purpose, so the page
  // must hide it. The overlay total still skips it, as the backend does.
  groceryTap.pantryLine = pantryId ?? null;
  await page.getByRole("button", { name: "Rebuild estimate" }).click();
  await expectEstimate(page, "$11.04");
  const rebuilt = groceryTap.latest();
  const rebuiltOverlay = groceryTap.latestOverlay();
  const oliveOil = rebuilt.result.plan.lines.find((line) => line.ingredient_id === pantryId);
  expect(oliveOil?.from_pantry, "olive oil is now a pantry line").toBe(true);
  expect(
    rebuiltOverlay.lines.map((entry) => entry.ingredient_id),
    "the fake overlay lists the pantry line",
  ).toContain(pantryId);
  const purchased = rebuiltOverlay.lines.filter((entry) => entry.ingredient_id !== pantryId);
  expect(purchased.length, "purchased lines after the rebuild").toBeGreaterThan(0);
  expect(rebuiltOverlay.total_cents, "overlay total skips the pantry line").toBe(
    purchased.reduce((sum, entry) => sum + entry.cents, 0),
  );
  const oliveOilRow = estimate.locator(".estimate-line").filter({ has: pantry });
  await expect(oliveOilRow).toHaveCount(1);
  await expect(oliveOilRow.locator(".estimate-line-spoonacular")).toHaveCount(0);
  await expect(estimate.locator(".estimate-line-spoonacular")).toHaveCount(purchased.length);
  await expect(estimate.locator(".estimate-overlay-total")).toHaveText(
    dollars(rebuiltOverlay.total_cents),
  );
});

test("chat: a held request shows progress, then the answer", async ({
  page,
  groceryTap,
  chat,
}) => {
  await buildBeanTacos(page);
  const parentId = groceryTap.latest().id;
  const panel = chatPanel(page);
  const message = panel.getByLabel("Message", { exact: true });
  await expect(message).toBeEnabled();
  await message.fill(CHAT_MESSAGE);
  await panel.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => chat.posts.length).toBe(1);

  const status = panel.getByRole("status");
  await expect(status).toHaveCount(1);
  await expect(status).toHaveText(CHAT_PENDING);
  await expect(message).toBeFocused();
  await expect(message).toBeEnabled();
  await expect(message).toHaveAttribute("readonly", "");
  await expect(message).not.toBeEditable();
  await expect.poll(() => chat.polls(), { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
  await expect(status).toHaveText(CHAT_PENDING);

  chat.finish("succeeded");
  await expect(panel.getByRole("list", { name: "Messages" })).toContainText(CHAT_ANSWER);
  await expect(status).toHaveText("");
  await expect(panel.locator(".conversation-error")).toHaveCount(0);
  const [post] = chat.posts;
  expect(post?.key, "Idempotency-Key header").toBeTruthy();
  expect(post?.body).toEqual({
    message: CHAT_MESSAGE,
    monthly_limit_cents: 10000,
    plan_cap_cents: 4000,
    previous_job_id: parentId,
  });
});

test("chat: a retry with the same key returns the same failed job", async ({ page, chat }) => {
  await buildBeanTacos(page);
  const panel = chatPanel(page);
  const message = panel.getByLabel("Message", { exact: true });
  await expect(message).toBeEnabled();
  await message.fill(CHAT_MESSAGE);
  await panel.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => chat.posts.length).toBe(1);
  chat.finish("failed");

  const status = panel.getByRole("status");
  await expect(status).toHaveCount(1);
  await expect(status).toHaveText(CHAT_FAILED);
  await expect(panel.locator(".conversation-error")).toHaveText(CHAT_FAILED);
  const retry = panel.getByRole("button", { name: "Retry the same request", exact: true });
  await expect(retry).toBeEnabled();
  const pollsBeforeRetry = chat.polls();
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => chat.posts.length).toBe(2);
  await expect.poll(() => chat.polls()).toBeGreaterThan(pollsBeforeRetry);

  const [first, second] = chat.posts;
  expect(first?.key, "Idempotency-Key header").toBeTruthy();
  expect(second?.key, "retry reuses the Idempotency-Key").toBe(first?.key);
  expect(second?.body, "retry sends an equal body").toEqual(first?.body);
  expect(first?.jobId, "first POST job ID").toBeTruthy();
  expect(second?.jobId, "retry returns the same job").toBe(first?.jobId);

  await expect(status).toHaveText(CHAT_FAILED);
  await expect(panel.locator(".conversation-error")).toHaveText(CHAT_FAILED);
  await expect(panel.getByRole("list", { name: "Messages" })).not.toContainText(CHAT_ANSWER);
});
