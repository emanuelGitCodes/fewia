import { expect, test as base, type Page } from "@playwright/test";
import {
  SPOONACULAR_COST_NOTICE,
  type GroceryJobResult,
  type GroceryRequest,
  type SpendingSource,
} from "../../src/apiTypes";
import type { ChatJobCreate, ChatResult } from "../../src/chatTypes";

export { expect };

// The base Compose stack turns off Bedrock chat and the Spoonacular overlay.
// These helpers fake only those three surfaces with `page.route`: the providers
// flag, the chat endpoints, and the overlay field. Every grocery request stays
// live, and the chat and overlay fakes read the real grocery responses.

export const CHAT_ANSWER = "Here is a plan that fits your budget.";

const OVERLAY_MARKUP_CENTS = 37;
// Used only when the live job result carries no evidence revision. The UI
// requires 64 lowercase hex characters for a chat plan.
const PLACEHOLDER_REVISION = "0".repeat(64);
const CHAT_JOBS_PATH = "/api/grocery/chat/jobs";
const CHAT_JOB_PATH = /^\/api\/grocery\/chat\/jobs\/([^/]+)$/;

type CapturedResult = GroceryJobResult & {
  request?: GroceryRequest;
  evidence_id?: string | null;
  evidence_revision_id?: string;
};

type GroceryJobWire = {
  id: string;
  status: string;
  result: CapturedResult | null;
};

export type GroceryCapture = {
  id: string;
  result: CapturedResult;
  request: GroceryRequest | null;
};

export type AppliedOverlay = {
  total_cents: number;
  notice: string;
  lines: { ingredient_id: string; cents: number }[];
};

export type GroceryTap = {
  overlay: boolean;
  latest: () => GroceryCapture;
  latestOverlay: () => AppliedOverlay;
};

export type ChatOutcome = "failed" | "succeeded";

export type ChatPost = {
  body: ChatJobCreate;
  key: string | null;
};

export type ChatFake = {
  posts: ChatPost[];
  unexpected: string[];
  polls: () => number;
  finish: (outcome: ChatOutcome) => void;
};

type ChatJobWire = {
  id: string;
  status: "queued" | "failed" | "succeeded";
  result: ChatResult | null;
  error_code: string | null;
};

async function horizontalOverflow(page: Page): Promise<number> {
  const viewport = page.viewportSize();
  if (viewport === null) {
    throw new Error("The test project MUST set a viewport.");
  }
  const width = await page.evaluate(() =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  );
  return width - viewport.width;
}

function overlayFor(result: CapturedResult): AppliedOverlay {
  const lines = result.plan.lines
    .filter((line) => !line.from_pantry)
    .map((line) => ({
      ingredient_id: line.ingredient_id,
      cents: (line.cost_cents ?? 0) + OVERLAY_MARKUP_CENTS,
    }));
  return {
    total_cents: lines.reduce((sum, line) => sum + line.cents, 0),
    notice: SPOONACULAR_COST_NOTICE,
    lines,
  };
}

async function installProviders(page: Page): Promise<void> {
  await page.route(/\/api\/grocery\/providers$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    const providers = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...providers, chat_configured: true } });
  });
}

async function installGroceryTap(page: Page): Promise<GroceryTap> {
  let posted: GroceryRequest | null = null;
  let captured: GroceryCapture | null = null;
  let applied: AppliedOverlay | null = null;
  const tap: GroceryTap = {
    overlay: false,
    latest: () => {
      if (captured === null) {
        throw new Error("No succeeded grocery job reached the page yet.");
      }
      return captured;
    },
    latestOverlay: () => {
      if (applied === null) {
        throw new Error("No overlay was added to a grocery job yet.");
      }
      return applied;
    },
  };
  await page.route(/\/api\/grocery\/jobs$/, async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      posted = (request.postDataJSON() as { request: GroceryRequest }).request;
    }
    await route.fallback();
  });
  await page.route(/\/api\/grocery\/jobs\/[^/?]+$/, async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    if (!response.ok()) {
      await route.fulfill({ response });
      return;
    }
    const job = (await response.json()) as GroceryJobWire;
    if (job.status !== "succeeded" || job.result === null) {
      await route.fulfill({ response, json: job });
      return;
    }
    captured = { id: job.id, result: structuredClone(job.result), request: posted };
    if (tap.overlay) {
      applied = overlayFor(job.result);
      job.result.supermarket_estimate = applied;
    }
    await route.fulfill({ response, json: job });
  });
  return tap;
}

// The chat result reuses the plan, budget, nutrition, and spending source that
// the live grocery job returned, so no plan fixture is written by hand.
function chatResultFrom(capture: GroceryCapture): ChatResult {
  const { result } = capture;
  const request = result.request ?? capture.request;
  if (request === null || request === undefined) {
    throw new Error("The grocery request was not captured.");
  }
  return {
    status: result.plan.accepted ? "planned" : "needs_revision",
    answer: CHAT_ANSWER,
    plan: result.plan,
    budget: result.budget,
    request,
    meal_nutrition: result.meal_nutrition ?? null,
    evidence_id: result.evidence_id ?? null,
    evidence_revision_id: result.evidence_revision_id ?? PLACEHOLDER_REVISION,
    spending_source: result.spending_source as SpendingSource,
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 1,
    usage: null,
  };
}

async function installChatFake(page: Page, grocery: GroceryTap): Promise<ChatFake> {
  const finished = new Map<string, ChatJobWire>();
  const ids: string[] = [];
  let polls = 0;
  const fake: ChatFake = {
    posts: [],
    unexpected: [],
    polls: () => polls,
    finish: (outcome) => {
      const id = ids.at(-1);
      if (id === undefined) {
        throw new Error("No chat job is waiting to finish.");
      }
      finished.set(
        id,
        outcome === "failed"
          ? { id, status: "failed", result: null, error_code: "fake_chat_failure" }
          : { id, status: "succeeded", result: chatResultFrom(grocery.latest()), error_code: null },
      );
    },
  };
  await page.route(/\/api\/grocery\/chat(\/|$)/, async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    if (method === "POST" && path === CHAT_JOBS_PATH) {
      fake.posts.push({
        body: request.postDataJSON() as ChatJobCreate,
        key: request.headers()["idempotency-key"] ?? null,
      });
      const id = `fake-chat-${fake.posts.length}`;
      ids.push(id);
      await route.fulfill({ json: { job_id: id, status: "queued" } });
      return;
    }
    const id = method === "GET" ? CHAT_JOB_PATH.exec(path)?.[1] : undefined;
    if (id !== undefined && ids.includes(decodeURIComponent(id))) {
      polls += 1;
      const key = decodeURIComponent(id);
      const body: ChatJobWire = finished.get(key) ?? {
        id: key,
        status: "queued",
        result: null,
        error_code: null,
      };
      await route.fulfill({ json: body });
      return;
    }
    fake.unexpected.push(`${method} ${path}`);
    await route.abort();
  });
  return fake;
}

type Fixtures = {
  guard: undefined;
  groceryTap: GroceryTap;
  chat: ChatFake;
};

// Every test records console errors and uncaught page errors, and checks for
// horizontal overflow in the final page state. The `chat` fixture turns on the
// fake chat provider; its teardown fails the test on any unplanned chat call.
export const test = base.extend<Fixtures>({
  guard: [
    async ({ page }, provide) => {
      const errors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") {
          errors.push(`console: ${message.text()}`);
        }
      });
      page.on("pageerror", (error) => {
        errors.push(`pageerror: ${error.message}`);
      });
      await provide(undefined);
      expect(errors, "console and page errors").toEqual([]);
      expect(await horizontalOverflow(page), "horizontal overflow in px").toBeLessThanOrEqual(0);
    },
    { auto: true },
  ],
  groceryTap: async ({ page }, provide) => {
    await provide(await installGroceryTap(page));
  },
  chat: async ({ page, groceryTap }, provide) => {
    await installProviders(page);
    const fake = await installChatFake(page, groceryTap);
    await provide(fake);
    expect(fake.unexpected, "unexpected chat requests").toEqual([]);
  },
});
