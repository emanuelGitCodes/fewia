import type { Locator, Page } from "@playwright/test";
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

async function expectEstimate(page: Page, total: string): Promise<void> {
  await expect(page.locator(".estimate-total")).toHaveText(total);
  await expect(page.locator("#estimate-heading")).toBeFocused();
}

async function buildBeanTacos(page: Page): Promise<void> {
  await open(page);
  await page.getByRole("button", { name: "Bean tacos for two" }).click();
  await expectEstimate(page, "$17.03");
}

test("sample catalog: the estimate keeps the sample total and notice", async ({ page, groceryTap }) => {
  await buildBeanTacos(page);
  const estimate = estimatePanel(page);
  const job = groceryTap.latest();
  await expect(estimate.getByText(SAMPLE_NOTICE, { exact: true })).toBeVisible();
  await expect(estimate.locator(".estimate-line")).toHaveCount(job.result.plan.lines.length);

  const pantry = page.getByLabel("I have olive oil");
  await pantry.check();
  await page.getByRole("button", { name: "Rebuild estimate" }).click();
  await expectEstimate(page, "$11.04");
  await expect(estimate.getByText(SAMPLE_NOTICE, { exact: true })).toBeVisible();
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
