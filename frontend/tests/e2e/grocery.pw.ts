import type { Locator, Page } from "@playwright/test";
import { expect, test } from "./fakes";

const SAMPLE_NOTICE =
  "Estimated from the demo price catalog. Instacart prices, availability, taxes, delivery fees, and tips are not verified.";
const WITHIN_BUDGET = "This estimate is within the plan budget.";
const DIRTY_SENTENCE = "Rebuild the request to apply request changes.";
const REBUILD_GUIDANCE = "Rebuild your estimate to use these changes in chat";

test.describe.configure({ timeout: 60_000 });

async function open(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByLabel("Recipe 1", { exact: true })).toBeVisible();
}

function estimatePanel(page: Page): Locator {
  return page.locator("section.estimate-panel");
}

async function expectEstimate(page: Page, total: string): Promise<void> {
  await expect(page.locator(".estimate-total")).toHaveText(total);
  await expect(page.locator("#estimate-heading")).toBeFocused();
}

test("smoke: page loads with default budget, catalog, and chat unavailable", async ({ page }) => {
  await open(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Meals that fit your budget" }),
  ).toBeVisible();
  await expect(page.getByLabel("Monthly limit")).toHaveValue("100");
  await expect(page.getByLabel("Plan cap (optional)")).toHaveValue("40");
  await expect(page.getByLabel("Recipe 1", { exact: true }).locator("option")).toHaveCount(40);
  await expect(page.getByLabel("Servings 1", { exact: true }).locator("option")).toHaveCount(8);
  const chat = page.getByRole("region", { name: "Meal chat" });
  await expect(chat.getByText("Meal chat is unavailable.")).toBeVisible();
});

test("example: Bean tacos for two builds a labeled estimate", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Bean tacos for two" }).click();
  await expectEstimate(page, "$17.03");
  const estimate = estimatePanel(page);
  await expect(estimate.locator(".estimate-source")).toHaveText("Source Your entered budget");
  const notice = estimate.getByText(SAMPLE_NOTICE, { exact: true });
  await expect(notice).toBeVisible();
  const totalBox = await estimate.locator(".estimate-total").boundingBox();
  const noticeBox = await notice.boundingBox();
  expect(totalBox, "estimate total box").not.toBeNull();
  expect(noticeBox, "notice box").not.toBeNull();
  expect(noticeBox?.y ?? 0, "notice sits below the total").toBeGreaterThan(totalBox?.y ?? 0);
  const nutrition = estimate.getByRole("region", { name: "Estimated nutrition" });
  await expect(nutrition.getByText("Plan total 758 kcal", { exact: false })).toBeVisible();
});

test("live regions: one estimate status and no conversation status role", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Bean tacos for two" }).click();
  await expectEstimate(page, "$17.03");
  const status = estimatePanel(page).getByRole("status");
  await expect(status).toHaveCount(1);
  await expect(status).toHaveText(WITHIN_BUDGET);
  const conversation = page.getByRole("region", { name: "Your conversation" });
  const conversationStatus = conversation.locator(".conversation-status");
  await expect(conversationStatus).toHaveCount(1);
  await expect(conversationStatus).not.toHaveAttribute("role", "status");
  await expect(conversation.getByRole("status")).toHaveCount(0);
});

test("pantry change marks the estimate stale until rebuilt", async ({ page }) => {
  await open(page);
  await page.getByRole("button", { name: "Bean tacos for two" }).click();
  await expectEstimate(page, "$17.03");
  const pantry = page.getByLabel("I have olive oil");
  await pantry.check();
  const estimate = estimatePanel(page);
  await expect(estimate.getByRole("heading", { name: "Previous estimate" })).toBeVisible();
  await expect(estimate.getByRole("status")).toHaveText(`${DIRTY_SENTENCE} ${WITHIN_BUDGET}`);
  await expect(page.locator(".chat-workspace").getByText(REBUILD_GUIDANCE)).toBeVisible();
  await page.getByRole("button", { name: "Rebuild estimate" }).click();
  await expect(estimate.getByRole("heading", { name: "Grocery estimate" })).toBeVisible();
  await expectEstimate(page, "$11.04");
  await expect(page.getByLabel("I have olive oil")).toBeChecked();
});

test("manual form: meal limits, then a submitted estimate", async ({ page }) => {
  await open(page);
  const add = page.getByRole("button", { name: "Add meal", exact: true });
  await add.click();
  await add.click();
  await expect(page.getByLabel("Recipe 3", { exact: true })).toBeVisible();
  await expect(add).toBeDisabled();
  await page.getByRole("button", { name: "Remove meal 3", exact: true }).click();
  await page.getByRole("button", { name: "Remove meal 2", exact: true }).click();
  await expect(page.getByLabel("Recipe 2", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Remove meal 1", exact: true })).toBeDisabled();
  await expect(add).toBeEnabled();
  await page.getByLabel("Recipe 1", { exact: true }).selectOption("lentil_soup");
  await page.getByLabel("Servings 1", { exact: true }).selectOption("3");
  await page.getByRole("button", { name: "Build my estimate" }).click();
  await expectEstimate(page, "$14.73");
  const nutrition = estimatePanel(page).getByRole("region", { name: "Estimated nutrition" });
  await expect(nutrition.getByText("Plan total 1230 kcal", { exact: false })).toBeVisible();
});
