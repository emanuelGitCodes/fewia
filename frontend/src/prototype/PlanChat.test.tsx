/** @vitest-environment jsdom */

import type { ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_ESTIMATE_NOTICE } from "../apiTypes";
import { MAX_MESSAGE_LENGTH } from "../chatConversationModel";
import type { ChatJob, ChatJobCreate, ChatResult } from "../chatTypes";
import { useChatJob } from "../useChatJob";
import { useProviderCapabilities } from "../useProviderCapabilities";
import { FAILED_LINE, OFF_LINE, PlanChat } from "./PlanChat";
import { planChatPrefix } from "./planChatModel";
import * as planModel from "./planModel";
import { initialPlanState, withPlanBudgetInput, type PlanState } from "./planModel";
import { planRevisionBody, savePlanRevision } from "./planRevisionApi";

vi.mock("../useChatJob", () => ({ useChatJob: vi.fn() }));
vi.mock("../useProviderCapabilities", () => ({ useProviderCapabilities: vi.fn() }));
vi.mock("./planRevisionApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./planRevisionApi")>()),
  savePlanRevision: vi.fn(),
}));

type JobMocks = {
  job: ChatJob | null;
  error: string | null;
  pending: boolean;
  submit: ReturnType<typeof vi.fn<(body: ChatJobCreate) => Promise<void>>>;
  clear: ReturnType<typeof vi.fn<() => void>>;
};

let jobState: JobMocks;

function chatJob(
  id: string,
  status: ChatResult["status"],
  answer: string,
  meals: Array<{ recipe_id: string; servings: number }> = [],
): ChatJob {
  const result = {
    status,
    answer,
    plan: null,
    budget: null,
    request:
      status === "clarification"
        ? null
        : {
            meals,
            budget_period: "2026-09-01",
            plan_cap_cents: null,
            pantry_ingredients: [],
            ingredient_exclusions: [],
            diet: "omnivore",
          },
    meal_nutrition: null,
    evidence_id: null,
    evidence_revision_id: null,
    spending_source: "fixture",
    tool_trace: [],
    model_turns: 1,
    planner_revisions: 0,
    usage: null,
  } as ChatResult;
  return { id, status: "succeeded", result, error_code: null };
}

function setProviders(configured: boolean, failed = false): void {
  vi.mocked(useProviderCapabilities).mockReturnValue({
    capabilities: failed
      ? null
      : {
          chat_configured: configured,
          plaid_configured: false,
          instacart_configured: false,
          spending_source: "manual",
        },
    pending: false,
    error: failed ? "unavailable" : null,
    retry: vi.fn(),
  });
}

function mount(
  state: PlanState = initialPlanState(),
  extra: Partial<ComponentProps<typeof PlanChat>> = {},
) {
  const onToggleIdea = vi.fn();
  const view = render(<PlanChat state={state} onToggleIdea={onToggleIdea} {...extra} />);
  return { ...view, onToggleIdea };
}

function box(): HTMLTextAreaElement {
  return screen.getByLabelText("Ask for a meal") as HTMLTextAreaElement;
}

function type(text: string): void {
  fireEvent.change(box(), { target: { value: text } });
}

async function submitText(text: string): Promise<void> {
  type(text);
  await act(async () => {
    fireEvent.keyDown(box(), { key: "Enter" });
  });
}

function submitted(index: number): ChatJobCreate {
  const body = jobState.submit.mock.calls[index]?.[0];
  if (body === undefined) {
    throw new Error("missing submit body");
  }
  return body;
}

beforeEach(() => {
  jobState = {
    job: null,
    error: null,
    pending: false,
    submit: vi.fn(async (_body: ChatJobCreate) => undefined),
    clear: vi.fn((): void => {
      jobState.job = null;
      jobState.error = null;
      jobState.pending = false;
    }),
  };
  vi.mocked(useChatJob).mockImplementation(() => ({
    job: jobState.job,
    error: jobState.error,
    pending: jobState.pending,
    submit: jobState.submit,
    clear: jobState.clear,
  }));
  setProviders(true);
  // Most tests run the fallback path; the plan revision tests override this.
  vi.mocked(savePlanRevision).mockReset();
  vi.mocked(savePlanRevision).mockRejectedValue(new Error("save failed"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("PlanChat", () => {
  it("keeps current cards and hidden failed turns after transcript eviction", async () => {
    let count = 0;
    jobState.submit.mockImplementation(async () => {
      count += 1;
      jobState.job = chatJob(
        `job-${count}`,
        count % 2 === 0 ? "incomplete" : "planned",
        `Answer ${count}`,
        [{ recipe_id: "chickpea_curry", servings: 2 }],
      );
    });
    mount();
    for (let index = 1; index <= 21; index += 1) {
      await submitText(`Question ${index}`);
    }
    expect(screen.queryByText("Answer 1")).toBeNull();
    expect(screen.queryByText("Question 20")).toBeNull();
    expect(screen.queryByText("Answer 20")).toBeNull();
    expect(screen.getByText("Answer 21")).toBeTruthy();
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("skips price recomputation while typing and polling", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "planned", "Try curry.", [
        { recipe_id: "chickpea_curry", servings: 2 },
      ]);
    });
    const state = initialPlanState();
    const onToggleIdea = vi.fn();
    const price = vi.spyOn(planModel, "previewAdd");
    const view = render(<PlanChat state={state} onToggleIdea={onToggleIdea} />);
    await submitText("Dinner");
    const calls = price.mock.calls.length;
    expect(calls).toBeGreaterThan(0);
    type("Another dinner");
    expect(price).toHaveBeenCalledTimes(calls);
    for (const status of ["queued", "running", "running"] as const) {
      jobState.job = { id: "job-2", status, result: null, error_code: null };
      jobState.pending = true;
      view.rerender(<PlanChat state={state} onToggleIdea={onToggleIdea} />);
      expect(price).toHaveBeenCalledTimes(calls);
    }
  });

  it("ignores a late completion after New chat", async () => {
    const state = initialPlanState();
    const onToggleIdea = vi.fn();
    const onReply = vi.fn();
    const view = render(<PlanChat state={state} onToggleIdea={onToggleIdea} onReply={onReply} />);
    await submitText("Old question");
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    jobState.job = chatJob("old-job", "planned", "Old answer", [
      { recipe_id: "chickpea_curry", servings: 2 },
    ]);
    view.rerender(<PlanChat state={state} onToggleIdea={onToggleIdea} onReply={onReply} />);
    expect(screen.queryByText("Old answer")).toBeNull();
    expect(screen.queryByRole("article")).toBeNull();
    expect(onReply).not.toHaveBeenCalled();
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("new-job", "clarification", "New answer");
    });
    await submitText("New question");
    expect(screen.getByText("New answer")).toBeTruthy();
    expect(screen.queryByText("Old answer")).toBeNull();
  });

  it("is an aside labelled by its Ask FEWIA heading with one status region", () => {
    mount();
    const aside = screen.getByRole("complementary", { name: "Ask FEWIA" });
    expect(aside.querySelector("h2")?.textContent).toBe("Ask FEWIA");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(
      screen.getByText("Replies come from a real model call. Prices are sample estimates."),
    ).toBeTruthy();
  });

  it("shows one line and no composer when chat is not configured", () => {
    setProviders(false);
    mount();
    expect(screen.getByText(OFF_LINE)).toBeTruthy();
    expect(screen.queryByLabelText("Ask for a meal")).toBeNull();
    expect(screen.queryByRole("button", { name: "New chat" })).toBeNull();
  });

  it("shows the off line when the capabilities request failed", () => {
    setProviders(false, true);
    mount();
    expect(screen.getByText(OFF_LINE)).toBeTruthy();
    expect(screen.queryByLabelText("Ask for a meal")).toBeNull();
  });

  it("shows the empty state with three starters that fill the textarea", () => {
    mount();
    expect(screen.getByText("Ask for a meal idea")).toBeTruthy();
    const names = ["Cheap vegetarian dinner for 2", "More protein for under $10", "Use what is in my pantry"];
    for (const name of names) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("button", { name: names[1] }));
    expect(box().value).toBe(names[1]);
    expect(document.activeElement).toBe(box());
  });

  it("shows Queued with a read-only textarea and a Sending button", () => {
    jobState.pending = true;
    jobState.job = { id: "job-1", status: "queued", result: null, error_code: null };
    mount();
    expect(screen.getByRole("status").textContent).toBe("Queued");
    expect(box().readOnly).toBe(true);
    const send = screen.getByRole("button", { name: "Sending" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    expect(screen.queryByText("Ask for a meal idea")).toBeNull();
  });

  it("shows the running text", () => {
    jobState.pending = true;
    jobState.job = { id: "job-1", status: "running", result: null, error_code: null };
    mount();
    expect(screen.getByRole("status").textContent).toBe("Running. FEWIA is finding meals.");
  });

  it("sends on Enter with the plan prefix and keeps the typed text in the transcript", async () => {
    const state = initialPlanState();
    mount(state);
    box().focus();
    await submitText("  Cheap dinner  ");
    expect(jobState.submit).toHaveBeenCalledTimes(1);
    expect(submitted(0).message).toBe(`${planChatPrefix(state)}Cheap dinner`);
    expect(submitted(0).monthly_limit_cents).toBe(4000);
    expect(submitted(0).plan_cap_cents).toBe(4000);
    const log = screen.getByRole("list", { name: "Messages" });
    expect(log.tagName).toBe("OL");
    expect(log.textContent).toContain("Cheap dinner");
    expect(log.textContent).not.toContain("My current plan");
    expect(document.activeElement).toBe(box());
  });

  it("adds a line on Shift+Enter without sending", async () => {
    mount();
    type("Cheap dinner");
    let notPrevented = false;
    await act(async () => {
      notPrevented = fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
    });
    // fireEvent returns false when a handler called preventDefault.
    expect(notPrevented).toBe(true);
    expect(jobState.submit).not.toHaveBeenCalled();
  });

  it("allows MAX_MESSAGE_LENGTH characters in the textarea", () => {
    mount(initialPlanState());
    expect(box().maxLength).toBe(MAX_MESSAGE_LENGTH);
  });

  it("does not send an empty message", async () => {
    mount();
    await act(async () => {
      fireEvent.keyDown(box(), { key: "Enter" });
    });
    expect(jobState.submit).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("blocks sending and says why while the plan cap is invalid", () => {
    mount(withPlanBudgetInput(initialPlanState(), "12.345"));
    type("Cheap dinner");
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Fix the plan cap to send a message.")).toBeTruthy();
  });

  it("shows an idea card for a planned reply and adds it in one tap", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "planned", "Chickpea curry fits.", [
        { recipe_id: "chickpea_curry", servings: 2 },
        { recipe_id: "bean_tacos", servings: 2 },
        { recipe_id: "nope", servings: 2 },
      ]);
    });
    const { onToggleIdea } = mount();
    await submitText("Something with chickpeas");
    expect(screen.getByText("Chickpea curry fits.")).toBeTruthy();
    expect(screen.getAllByRole("article")).toHaveLength(1);
    const notice = screen.getByText(SAMPLE_ESTIMATE_NOTICE);
    expect(notice.textContent).toBe(SAMPLE_ESTIMATE_NOTICE);
    expect(notice.closest("aside")).not.toBeNull();
    expect(screen.queryByText("Price changes are sample estimates.")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("FEWIA replied with 1 meal idea.");
    fireEvent.click(screen.getByRole("button", { name: /^Add Chickpea curry, 2 servings/ }));
    expect(onToggleIdea).toHaveBeenCalledWith("chickpea_curry", 2, false);
  });

  it("shows the Kroger quote under the reply and passes the store id to the job", async () => {
    const quote = {
      kind: "store_live", ingredient_id: "rice", product_label: "Long grain rice", brand: null,
      size: "2 lb", regular_cents: 249, promo_cents: null, stock_level: "HIGH",
      location_id: "01400943", retrieved_at: "2026-09-01T12:00:00Z",
    } as const;
    jobState.submit.mockImplementation(async () => {
      const job = chatJob("job-1", "planned", "Rice fits.", [{ recipe_id: "chickpea_curry", servings: 2 }]);
      jobState.job = { ...job, result: { ...job.result, kroger_quote: quote } as ChatResult };
    });
    mount(initialPlanState(), { krogerStore: { locationId: "01400943", name: "Main Street" } });
    await submitText("Rice please");
    expect(vi.mocked(useChatJob)).toHaveBeenCalledWith("01400943");
    const line = screen.getByText(/^Live price from Kroger Main Street as of /);
    expect(line.textContent).toContain(": Long grain rice, 2 lb, regular $2.49, stock high. ");
    expect(screen.getByText(SAMPLE_ESTIMATE_NOTICE)).toBeTruthy();
  });

  it("shows the picked store in the panel above the form and passes the handlers through", () => {
    const onKrogerChoose = vi.fn();
    const onKrogerClear = vi.fn();
    mount(initialPlanState(), {
      krogerStore: { locationId: "01400943", name: "Main Street" },
      onKrogerChoose,
      onKrogerClear,
    });
    const picker = screen.getByText("Kroger store: Main Street");
    expect(picker.compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(onKrogerClear).toHaveBeenCalledTimes(1);
  });

  it("hides the store picker when chat is off", () => {
    setProviders(false);
    mount(initialPlanState(), { onKrogerChoose: vi.fn(), onKrogerClear: vi.fn() });
    expect(screen.queryByRole("button", { name: "Choose a Kroger store for live prices" })).toBeNull();
  });

  it("shows the fixed sentence when Kroger is degraded and nothing without a quote", async () => {
    jobState.submit.mockImplementation(async () => {
      const job = chatJob("job-1", "clarification", "Which meals?");
      jobState.job = { ...job, result: { ...job.result, kroger_degraded: true } as ChatResult };
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.getByText("Kroger did not answer, so no live price is shown.")).toBeTruthy();
    cleanup();
    jobState.job = null;
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-2", "clarification", "Which meals?");
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.queryByText(/Kroger/)).toBeNull();
    expect(vi.mocked(useChatJob)).toHaveBeenLastCalledWith(null);
  });

  it("shows only the answer text for a clarification", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.getByText("Which meals should I plan?")).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
    expect(screen.queryByText(SAMPLE_ESTIMATE_NOTICE)).toBeNull();
  });

  it("shows the failure line and Retry for a failed request, and retries the same body", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = { id: "job-1", status: "failed", result: null, error_code: "tool" };
      jobState.error = "The chat request failed. Retry checks the same request.";
    });
    mount();
    await submitText("Cheap dinner");
    expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
    expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
    const retry = screen.getByRole("button", { name: "Retry" });
    retry.focus();
    await act(async () => {
      fireEvent.click(retry);
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(1)).toEqual(submitted(0));
    expect(document.activeElement).toBe(box());
  });

  it.each(["limit", "incomplete"] as const)(
    "shows the failure line and Ask again for a %s result and hides its answer",
    async (status) => {
      jobState.submit.mockImplementation(async () => {
        jobState.job = chatJob("job-1", status, "Internal turn limit text.");
      });
      mount();
      await submitText("Cheap dinner");
      expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
      expect(screen.queryByText("Internal turn limit text.")).toBeNull();
      expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    },
  );

  it("sends the last user text as a fresh request on Ask again and focuses the textarea", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "limit", "Internal turn limit text.");
    });
    mount();
    await submitText("Cheap dinner");
    expect(jobState.clear).toHaveBeenCalledTimes(1);
    const again = screen.getByRole("button", { name: "Ask again" });
    again.focus();
    await act(async () => {
      fireEvent.click(again);
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    expect(submitted(1).message).toBe(submitted(0).message);
    expect(submitted(1).message.endsWith("Cheap dinner")).toBe(true);
    // A fresh request clears the finished job; retry() would not.
    expect(jobState.clear).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(box());
  });

  it("shows the question once after Ask again gets a planned answer", async () => {
    let calls = 0;
    jobState.submit.mockImplementation(async () => {
      calls += 1;
      jobState.job =
        calls === 1
          ? chatJob("job-1", "limit", "Internal turn limit text.")
          : chatJob("job-2", "planned", "Try tacos.");
    });
    mount();
    await submitText("Cheap dinner");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Ask again" }));
    });
    expect(jobState.submit).toHaveBeenCalledTimes(2);
    const log = screen.getByRole("list", { name: "Messages" });
    const asked = Array.from(log.querySelectorAll(".is-user")).filter((turn) =>
      (turn.textContent ?? "").includes("Cheap dinner"),
    );
    expect(asked).toHaveLength(1);
    expect(screen.getByText("Try tacos.")).toBeTruthy();
  });

  it("keeps Ask again when the draft differs only by a trailing space", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "limit", "Internal turn limit text.");
    });
    mount();
    await submitText("Cheap dinner");
    type("Cheap dinner ");
    expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
  });

  it("hides Ask again while the draft is not empty and keeps the failure line", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "limit", "Internal turn limit text.");
    });
    mount();
    await submitText("Cheap dinner");
    expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
    type("Something else");
    expect(screen.queryByRole("button", { name: "Ask again" })).toBeNull();
    expect(screen.getByRole("status").textContent).toBe(FAILED_LINE);
    expect(box().value).toBe("Something else");
    type("");
    expect(screen.getByRole("button", { name: "Ask again" })).toBeTruthy();
  });

  it.each(["limit", "incomplete"] as const)(
    "does not tell the shell about a %s result",
    async (status) => {
      jobState.submit.mockImplementation(async () => {
        jobState.job = chatJob("job-1", status, "Internal turn limit text.");
      });
      const onReply = vi.fn();
      mount(initialPlanState(), { onReply });
      await submitText("Cheap dinner");
      expect(onReply).not.toHaveBeenCalled();
    },
  );

  it("shows the Hide chat button only when a sheet can be closed", () => {
    const onHide = vi.fn();
    const view = mount();
    expect(screen.queryByRole("button", { name: "Hide chat" })).toBeNull();
    view.unmount();
    mount(initialPlanState(), { onHide });
    fireEvent.click(screen.getByRole("button", { name: "Hide chat" }));
    expect(onHide).toHaveBeenCalledTimes(1);
  });

  it("focuses the textarea when the sheet opens and takes the given id", () => {
    const state = initialPlanState();
    const view = render(<PlanChat state={state} onToggleIdea={vi.fn()} id="ask-panel" open={false} />);
    expect(document.activeElement).not.toBe(box());
    view.rerender(<PlanChat state={state} onToggleIdea={vi.fn()} id="ask-panel" open />);
    expect(document.activeElement).toBe(box());
    expect(screen.getByRole("complementary", { name: "Ask FEWIA" }).id).toBe("ask-panel");
  });

  it("tells the shell once when a reply arrives", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    const onReply = vi.fn();
    mount(initialPlanState(), { onReply });
    expect(onReply).not.toHaveBeenCalled();
    await submitText("Plan dinner");
    expect(onReply).toHaveBeenCalledTimes(1);
  });

  describe("plan revision", () => {
    it("sends the saved revision ID and the unprefixed text", async () => {
      vi.mocked(savePlanRevision).mockResolvedValue("rev-1");
      const state = initialPlanState();
      mount(state);
      await submitText("  Cheap dinner  ");
      expect(savePlanRevision).toHaveBeenCalledWith(planRevisionBody(state), expect.any(AbortSignal));
      expect(submitted(0).plan_revision_id).toBe("rev-1");
      expect(submitted(0).message).toBe("Cheap dinner");
    });

    it("saves once for two sends with an unchanged plan", async () => {
      vi.mocked(savePlanRevision).mockResolvedValue("rev-1");
      mount();
      await submitText("First");
      await submitText("Second");
      expect(jobState.submit).toHaveBeenCalledTimes(2);
      expect(savePlanRevision).toHaveBeenCalledTimes(1);
      expect(submitted(1).plan_revision_id).toBe("rev-1");
    });

    it("saves again after a plan change between sends", async () => {
      vi.mocked(savePlanRevision).mockResolvedValueOnce("rev-1").mockResolvedValueOnce("rev-2");
      const onToggleIdea = vi.fn();
      const view = render(<PlanChat state={initialPlanState()} onToggleIdea={onToggleIdea} />);
      await submitText("First");
      view.rerender(
        <PlanChat state={withPlanBudgetInput(initialPlanState(), "55")} onToggleIdea={onToggleIdea} />,
      );
      await submitText("Second");
      expect(savePlanRevision).toHaveBeenCalledTimes(2);
      expect(submitted(0).plan_revision_id).toBe("rev-1");
      expect(submitted(1).plan_revision_id).toBe("rev-2");
    });

    it("falls back to the prefixed text with no revision ID when the save fails", async () => {
      const state = initialPlanState();
      mount(state);
      await submitText("Cheap dinner");
      expect(submitted(0).plan_revision_id).toBeNull();
      expect(submitted(0).message).toBe(`${planChatPrefix(state)}Cheap dinner`);
    });

    it("falls back to the prefix when a hung save is aborted", async () => {
      vi.mocked(savePlanRevision).mockRejectedValue(new DOMException("timed out", "TimeoutError"));
      const state = initialPlanState();
      mount(state);
      await submitText("Cheap dinner");
      expect(vi.mocked(savePlanRevision).mock.calls[0]?.[1]).toBeInstanceOf(AbortSignal);
      expect(submitted(0).plan_revision_id).toBeNull();
      expect(submitted(0).message).toBe(`${planChatPrefix(state)}Cheap dinner`);
    });

    it("sends the text alone when the fallback prefix would exceed the limit", async () => {
      const text = "a".repeat(MAX_MESSAGE_LENGTH);
      mount();
      await submitText(text);
      expect(submitted(0).plan_revision_id).toBeNull();
      expect(submitted(0).message).toBe(text);
    });
  });

  it("clears the transcript on New chat", async () => {
    jobState.submit.mockImplementation(async () => {
      jobState.job = chatJob("job-1", "clarification", "Which meals should I plan?");
    });
    mount();
    await submitText("Plan dinner");
    expect(screen.getByRole("list", { name: "Messages" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByRole("list", { name: "Messages" })).toBeNull();
    expect(screen.getByText("Ask for a meal idea")).toBeTruthy();
    expect(box().value).toBe("");
  });
});
